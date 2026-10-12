from datetime import timedelta

from app.engine import utcnow
from tests.test_api import login


def prepare_claim(client):
    headers = login(client)
    client.put(
        "/api/profile",
        headers=headers,
        json={
            "name": "Synthetic Person",
            "facts": {"purchased": True, "first_name": "Synthetic", "benefit": False},
        },
    )
    opportunity = client.post(
        "/api/opportunities",
        headers=headers,
        json={
            "title": "Synthetic extension test",
            "official_url": "https://example.com/claim?case=synthetic",
            "official_notice_url": "https://example.com/notice",
            "record_type": "open_claim",
            "administrator": "Test administrator",
            "source_excerpt": "Synthetic source for tests only",
            "deadline": (utcnow() + timedelta(days=5)).isoformat(),
            "proof_required": False,
            "attestation_text": "Synthetic test declaration",
            "rules": [{"field": "purchased", "op": "eq", "value": True}],
        },
    ).json()["opportunity"]
    path = "/api/opportunities/" + opportunity["id"]
    client.post(
        path + "/verify",
        headers=headers,
        json={
            "administrator_verified": True,
            "official_form_verified": True,
            "criteria_and_deadline_verified": True,
            "claim_window_confirmed": True,
            "notes": "Synthetic official form reviewed for tests",
        },
    )
    client.put(
        path + "/form-fields",
        headers=headers,
        json={
            "official_fields_reviewed": True,
            "fields": [
                {"label": "First name", "profile_key": "first_name"},
                {"label": "Cash benefit", "profile_key": "benefit", "kind": "checkbox"},
            ],
        },
    )
    claim = client.post(path + "/prepare", headers=headers).json()
    return headers, path, claim


def test_browser_packet_is_authenticated_minimal_and_rechecks_revisions(client):
    assert client.get("/api/claims/unknown/browser-packet").status_code == 401
    headers, _, claim = prepare_claim(client)
    path = "/api/claims/" + claim["id"] + "/browser-packet"
    result = client.get(path)
    assert result.status_code == 200
    packet = result.json()
    assert packet["packet_hash"] == claim["packet_hash"]
    assert packet["official_url"] == "https://example.com/claim?case=synthetic"
    assert packet["fields"] == [{"label": "First name", "kind": "text", "value": "Synthetic"}]
    assert "facts" not in packet and "attestation_text" not in packet and "evidence" not in packet
    assert result.headers["cache-control"] == "no-store"
    client.put(
        "/api/profile",
        headers=headers,
        json={
            "name": "Synthetic Person",
            "facts": {"purchased": True, "first_name": "Changed"},
        },
    )
    assert client.get(path).status_code == 409


def test_browser_packet_available_during_handoff_but_not_after_submission(client):
    headers, _, claim = prepare_claim(client)
    path = "/api/claims/" + claim["id"]
    client.post(
        path + "/approve",
        headers=headers,
        json={
            "packet_hash": claim["packet_hash"],
            "facts_confirmed": True,
            "legal_attestation_accepted": True,
            "signer_name": "Synthetic Person",
        },
    )
    assert client.post(path + "/handoff", headers=headers).status_code == 200
    assert client.get(path + "/browser-packet").status_code == 200
    client.post(
        path + "/confirmation",
        headers=headers,
        json={
            "reference": "TEST ONLY",
            "submitted_at": utcnow().isoformat(),
            "evidence": "Synthetic receipt used only in this test",
            "human_completed": True,
        },
    )
    assert client.get(path + "/browser-packet").status_code == 409


def test_extension_download_is_authenticated_and_contains_only_installable_source(client):
    import io
    import json
    import zipfile

    assert client.get("/api/browser-extension").status_code == 401
    login(client)
    result = client.get("/api/browser-extension")
    assert result.status_code == 200
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "page.js",
            "popup.js",
            "popup.html",
            "popup.css",
            "README.md",
        }
        manifest = json.loads(archive.read("manifest.json"))
        assert set(manifest["permissions"]) == {"activeTab", "scripting", "storage"}
        assert "host_permissions" not in manifest and "content_scripts" not in manifest
