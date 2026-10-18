from datetime import timedelta

from app.engine import utcnow
from tests.test_api import login


def make_opportunity(client, headers):
    return client.post(
        "/api/opportunities",
        headers=headers,
        json={
            "title": "Synthetic form retrieval test",
            "official_url": "https://notice.example/claim",
            "official_notice_url": "https://notice.example/notice",
            "deadline": (utcnow() + timedelta(days=5)).isoformat(),
        },
    ).json()["opportunity"]


def test_official_form_retrieval_requires_authentication(client, monkeypatch):
    monkeypatch.setattr(
        "app.main.find_form_candidates",
        lambda url: [{"title": "Claim Form", "url": "https://notice.example/form.pdf", "kind": "pdf"}],
    )
    assert client.get("/api/opportunities/unknown/form-candidates").status_code == 401


def test_official_form_search_and_retrieval_are_tied_to_notice_source(client, monkeypatch):
    headers = login(client)
    opportunity = make_opportunity(client, headers)
    source = opportunity["official_notice_url"]
    candidate = {"title": "Claim Form", "url": "https://notice.example/form.pdf", "kind": "pdf"}
    monkeypatch.setattr("app.main.find_form_candidates", lambda url: [candidate] if url == source else [])
    monkeypatch.setattr(
        "app.main.retrieve_form_pdf",
        lambda notice, selected: (
            {
                "title": "Claim Form",
                "url": selected,
                "pdf_base64": "JVBERi0xLjQ=",
                "sha256": "a" * 64,
            }
            if notice == source and selected == candidate["url"]
            else (_ for _ in ()).throw(
                ValueError("Choose a PDF claim form found on the current official notice page.")
            )
        ),
    )

    path = f"/api/opportunities/{opportunity['id']}"
    found = client.get(path + "/form-candidates")
    assert found.status_code == 200
    assert found.json()["candidates"] == [candidate]

    retrieved = client.post(path + "/official-form", headers=headers, json={"url": candidate["url"]})
    assert retrieved.status_code == 200
    assert retrieved.json()["sha256"] == "a" * 64

    rejected = client.post(
        path + "/official-form", headers=headers, json={"url": "https://other.example/form.pdf"}
    )
    assert rejected.status_code == 422
