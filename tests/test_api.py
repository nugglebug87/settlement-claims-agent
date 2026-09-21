import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from app.main import app
from app.db import get_db
from app.models import Base
from app.config import settings


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(settings, "app_password", "test-password-123456")
    monkeypatch.setattr(settings, "session_secret", "test-secret-" * 5)
    monkeypatch.setattr(settings, "worker_enabled", False)
    monkeypatch.setattr(settings, "redis_url", "")
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()


def login(client):
    result = client.post(
        "/api/login", json={"password": "test-password-123456"}, headers={"Origin": settings.app_url}
    )
    assert result.status_code == 200
    return {"X-CSRF-Token": result.json()["csrf_token"], "Origin": settings.app_url}


def test_api_requires_login(client):
    assert client.get("/api/dashboard").status_code == 401


def test_profile_write_requires_csrf(client):
    login(client)
    assert client.put("/api/profile", json={"name": "Test", "facts": {}}).status_code == 403


def test_profile_roundtrip_and_empty_dashboard(client):
    headers = login(client)
    response = client.put(
        "/api/profile", headers=headers, json={"name": "Test", "facts": {"state": "CA", "purchased": False}}
    )
    assert response.status_code == 200
    assert client.get("/api/profile").json()["facts"]["purchased"] is False
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    assert response.json()["opportunities"] == []


def test_invalid_deadline_and_money_are_rejected(client):
    headers = login(client)
    response = client.post(
        "/api/opportunities",
        headers=headers,
        json={
            "title": "Test fixture",
            "official_url": "https://example.com",
            "deadline": "2030-01-01T12:00:00",
            "expected_payout": -1,
        },
    )
    assert response.status_code == 422


def test_all_sources_can_be_enabled_and_disabled_together(client):
    headers = login(client)
    imported = client.post("/api/source-catalog", headers=headers)
    assert imported.status_code == 200
    assert imported.json()["added"] > 0

    enabled = client.post("/api/sources/enable-all", headers=headers)
    assert enabled.status_code == 200
    assert enabled.json() == {
        "enabled": imported.json()["added"],
        "changed": imported.json()["added"],
    }
    assert all(source["enabled"] for source in client.get("/api/sources").json()["sources"])

    enabled_again = client.post("/api/sources/enable-all", headers=headers)
    assert enabled_again.json()["changed"] == 0

    disabled = client.post("/api/sources/disable-all", headers=headers)
    assert disabled.status_code == 200
    assert disabled.json()["disabled"] == imported.json()["added"]
    assert disabled.json()["changed"] == imported.json()["added"]
    assert not any(source["enabled"] for source in client.get("/api/sources").json()["sources"])


def test_catalog_import_refreshes_an_existing_redirect_url(client, monkeypatch):
    monkeypatch.setattr(settings, "source_allowed_hosts", "claimdepot.com")
    monkeypatch.setattr("app.main.validate_source_url", lambda url: None)
    headers = login(client)
    created = client.post(
        "/api/sources",
        headers=headers,
        json={
            "name": "Claim Depot",
            "url": "https://claimdepot.com/",
            "kind": "html_links",
            "stream": "settlements",
            "source_role": "directory",
            "enabled": False,
        },
    )
    assert created.status_code == 200

    imported = client.post("/api/source-catalog", headers=headers)
    assert imported.status_code == 200
    assert imported.json()["updated"] == 1
    claim_depot = next(
        source for source in client.get("/api/sources").json()["sources"] if source["name"] == "Claim Depot"
    )
    assert claim_depot["url"] == "https://www.claimdepot.com/"
