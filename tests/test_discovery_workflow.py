from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.engine import utcnow
from app.models import Source
from app.schemas import OpportunityInput
from app.services import ingest, prepare
from app.monitor import due_sources
from tests.test_workflow import setup_claim


@pytest.mark.parametrize(
    "classification",
    [
        "unknown",
        "breach_announcement",
        "investigation",
        "proposed_settlement",
        "automatic_payment",
        "expired",
        "closed",
    ],
)
def test_non_open_records_cannot_be_prepared(db, classification):
    person, opportunity = setup_claim(db)
    opportunity.record_type = classification
    with pytest.raises(HTTPException):
        prepare(db, person, opportunity)


def test_future_claim_window_cannot_be_prepared(db):
    person, opportunity = setup_claim(db)
    opportunity.claim_opens_at = utcnow() + timedelta(days=1)
    with pytest.raises(HTTPException):
        prepare(db, person, opportunity)


def test_defendant_administrator_matches_need_review_not_automatic_merge(db):
    common = {"title": "Synthetic candidate", "defendant": "Example, Inc.", "administrator": "Test ADMIN"}
    first, _ = ingest(db, OpportunityInput(**common, official_url="https://example.com/one"))
    second, duplicate = ingest(db, OpportunityInput(**common, official_url="https://example.com/two"))
    assert not duplicate and first.id != second.id
    assert first.id in second.possible_duplicate_ids


def test_daily_schedule_keeps_discovery_streams_separate(db):
    now = utcnow()
    for stream in ["settlements", "government_refunds", "breach_announcements"]:
        for n in range(4):
            db.add(
                Source(
                    name=f"{stream}-{n}", url=f"https://example.com/{stream}/{n}", stream=stream, enabled=True
                )
            )
    db.flush()
    due = due_sources(db, now)
    assert len(due) == 3
    assert {s.stream for s in due} == {"settlements", "government_refunds", "breach_announcements"}


def test_rediscovery_retains_evidence_and_invalidates_changed_terms(db):
    person, opportunity = setup_claim(db)
    data = OpportunityInput(
        title=opportunity.title,
        official_url=opportunity.official_url,
        deadline=utcnow() - timedelta(days=1),
        record_type="expired",
    )
    existing, duplicate = ingest(db, data)
    assert duplicate and existing.id == opportunity.id
    assert not existing.verified
    assert "source_change_requires_review" in existing.quality_flags


def test_breach_announcement_is_retained_without_claim_terms(db, monkeypatch):
    from sqlalchemy import select
    from app.discovery import run_source
    from app.models import Opportunity, DiscoveryObservation

    source = Source(
        name="Synthetic breach listing",
        url="https://example.com/news",
        kind="html_links",
        stream="breach_announcements",
    )
    db.add(source)
    db.flush()
    monkeypatch.setattr(
        "app.discovery.fetch_source",
        lambda url: (
            '<main><a href="/incident">Synthetic company announces data breach</a></main>',
            "text/html",
        ),
    )
    first = run_source(db, source)
    second = run_source(db, source)
    assert first.imported == 1 and second.duplicates == 1
    item = db.scalar(select(Opportunity))
    assert item.record_type == "breach_announcement"
    assert item.program_type == "breach_announcements"
    assert item.deadline is None and item.expected_payout is None
    assert not item.verified and item.rules == [] and item.attestation_text is None
    db.flush()
    assert len(list(db.scalars(select(DiscoveryObservation)))) == 2


def test_catalog_preserves_breach_sources_and_is_idempotent(client):
    from tests.test_api import login

    headers = login(client)
    assert client.post("/api/source-catalog", headers=headers).json()["added"] == 28
    assert client.post("/api/source-catalog", headers=headers).json()["added"] == 0
    sources = client.get("/api/sources").json()["sources"]
    breaches = [s for s in sources if s["stream"] == "breach_announcements"]
    assert len(breaches) == 6
    assert all(not s["enabled"] for s in sources)
