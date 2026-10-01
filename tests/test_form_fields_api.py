from datetime import timedelta

from app.engine import utcnow
from tests.test_api import login


def test_form_fields_roundtrip_and_stale_approval(client):
    headers = login(client)
    client.put(
        "/api/profile",
        headers=headers,
        json={
            "name": "Test person",
            "facts": {"purchased": True, "first_name": "Test"},
        },
    )
    opportunity = client.post(
        "/api/opportunities",
        headers=headers,
        json={
            "title": "Synthetic API fixture",
            "official_url": "https://example.com/claim",
            "record_type": "open_claim",
            "official_notice_url": "https://example.com/notice",
            "administrator": "Test administrator",
            "source_excerpt": "Synthetic source for tests only",
            "deadline": (utcnow() + timedelta(days=5)).isoformat(),
            "proof_required": False,
            "attestation_text": "Synthetic declaration for testing only",
            "rules": [{"field": "purchased", "op": "eq", "value": True}],
        },
    ).json()["opportunity"]
    path = "/api/opportunities/" + opportunity["id"]
    assert (
        client.put(
            path + "/form-fields",
            headers=headers,
            json={
                "fields": [{"label": "First name", "profile_key": "first_name"}],
                "official_fields_reviewed": True,
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            path + "/verify",
            headers=headers,
            json={
                "administrator_verified": True,
                "official_form_verified": True,
                "criteria_and_deadline_verified": True,
                "claim_window_confirmed": True,
                "notes": "Synthetic fixture reviewed for API testing",
            },
        ).status_code
        == 200
    )
    mapping = {
        "fields": [{"label": "First name", "profile_key": "first_name"}],
        "official_fields_reviewed": True,
    }
    assert client.put(path + "/form-fields", headers=headers, json=mapping).status_code == 200
    claim = client.post(path + "/prepare", headers=headers).json()
    assert claim["packet"]["form_fields"][0]["value"] == "Test"
    approval = {
        "packet_hash": claim["packet_hash"],
        "facts_confirmed": True,
        "legal_attestation_accepted": True,
        "signer_name": "Test person",
    }
    claim_path = "/api/claims/" + claim["id"]
    assert client.post(claim_path + "/approve", headers=headers, json=approval).status_code == 200
    assert client.put(path + "/form-fields", headers=headers, json=mapping).status_code == 200
    assert client.post(claim_path + "/handoff", headers=headers).status_code == 409
    fresh = client.post(path + "/prepare", headers=headers).json()
    approval["packet_hash"] = fresh["packet_hash"]
    assert client.post(claim_path + "/approve", headers=headers, json=approval).status_code == 200
    assert client.post(claim_path + "/handoff", headers=headers).status_code == 200
    assert client.put(path + "/form-fields", headers=headers, json=mapping).status_code == 409
