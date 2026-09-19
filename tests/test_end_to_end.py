from datetime import timedelta

from app.engine import utcnow
from tests.test_api import login


def test_entire_api_claim_lifecycle_with_evidence(client):
    headers = login(client)

    def request(path, body=None):
        return client.post("/api" + path, json=body, headers=headers)

    client.put(
        "/api/profile", headers=headers, json={"name": "Synthetic test person", "facts": {"purchased": True}}
    )
    payload = {
        "title": "SYNTHETIC TEST - not a real settlement",
        "official_url": "https://example.com/test-only",
        "case_number": "TEST COURT / TEST 1",
        "administrator": "Synthetic test administrator",
        "deadline": (utcnow() + timedelta(days=5)).isoformat(),
        "expected_payout": 250,
        "proof_required": True,
        "rules": [{"field": "purchased", "op": "eq", "value": True}],
        "attestation_text": "SYNTHETIC TEST ONLY: this is not a legal declaration.",
        "source_excerpt": "SYNTHETIC test document.",
    }
    result = request("/opportunities", payload)
    assert result.status_code == 200
    opportunity = result.json()["opportunity"]
    id = opportunity["id"]
    assert request(f"/opportunities/{id}/prepare").status_code == 409
    assert (
        request(
            f"/opportunities/{id}/verify",
            {
                "administrator_verified": True,
                "official_form_verified": True,
                "criteria_and_deadline_verified": True,
                "notes": "Synthetic test review notes only.",
            },
        ).status_code
        == 200
    )
    assert request(f"/opportunities/{id}/prepare").status_code == 409
    assert (
        request(
            f"/opportunities/{id}/evidence",
            {
                "reference": "TEST-RECEIPT",
                "description": "Synthetic receipt for automated testing only.",
                "personally_verified": True,
            },
        ).status_code
        == 200
    )
    claim = request(f"/opportunities/{id}/prepare").json()
    cid = claim["id"]
    assert claim["packet"]["evidence"][0]["reference"] == "TEST-RECEIPT"
    assert request(f"/claims/{cid}/handoff").status_code == 409
    approval = {
        "packet_hash": claim["packet_hash"],
        "facts_confirmed": True,
        "legal_attestation_accepted": True,
        "signer_name": "Synthetic Person",
    }
    assert (
        request(f"/claims/{cid}/approve", {**approval, "legal_attestation_accepted": False}).status_code
        == 422
    )
    assert request(f"/claims/{cid}/approve", {**approval, "packet_hash": "tampered"}).status_code == 409
    assert request(f"/claims/{cid}/approve", approval).status_code == 200
    handoff = request(f"/claims/{cid}/handoff")
    assert handoff.status_code == 200 and handoff.json()["url"] == payload["official_url"]
    assert (
        request(
            f"/claims/{cid}/confirmation",
            {
                "reference": "TEST-CONFIRMATION",
                "submitted_at": utcnow().isoformat(),
                "evidence": "Synthetic receipt, no external form was submitted.",
                "human_completed": True,
            },
        ).status_code
        == 200
    )
    assert request(f"/opportunities/{id}/prepare").status_code == 409
    assert (
        request(
            f"/claims/{cid}/status", {"status": "paid", "evidence": "Synthetic payment receipt only."}
        ).status_code
        == 422
    )
    result = request(
        f"/claims/{cid}/status",
        {"status": "paid", "actual_payout": 123.45, "evidence": "Synthetic payment receipt only."},
    )
    assert result.status_code == 200 and result.json()["actual_payout"] == 123.45
    audit = client.get("/api/audit").json()
    assert {
        "claim.prepared",
        "claim.approved",
        "claim.human_handoff",
        "claim.confirmation_recorded",
        "claim.status_changed",
    }.issubset({a["action"] for a in audit})
    assert request("/opportunities", payload).json()["duplicate"]


def test_deadline_offset_roundtrips_as_utc(client):
    headers = login(client)
    result = client.post(
        "/api/opportunities",
        headers=headers,
        json={
            "title": "Synthetic timezone fixture",
            "official_url": "https://example.com/timezone",
            "deadline": "2030-01-01T23:00:00-05:00",
        },
    )
    assert result.json()["opportunity"]["deadline"] == "2030-01-02T04:00:00+00:00"
    assert client.get("/api/dashboard").json()["opportunities"][0]["deadline"] == "2030-01-02T04:00:00+00:00"
