import pytest
from fastapi import HTTPException

from app.schemas import ApprovalInput
from app.services import approve, handoff, prepare
from tests.test_workflow import setup_claim


def test_preparation_fills_only_reviewed_fields_and_preserves_false(db):
    person, opportunity = setup_claim(db)
    person.facts = {**person.facts, "first_name": "Test", "marketing": False, "unrelated": "private"}
    opportunity.provenance = {
        **opportunity.provenance,
        "form_fields": [
            {"label": "First name", "profile_key": "first_name", "kind": "text", "required": True},
            {"label": "Marketing opt-in", "profile_key": "marketing", "kind": "checkbox", "required": True},
        ],
    }
    claim = prepare(db, person, opportunity)
    assert [f["value"] for f in claim.packet["form_fields"]] == ["Test", False]
    assert "unrelated" not in str(claim.packet)


def test_missing_or_wrong_type_required_answer_blocks_preparation(db):
    person, opportunity = setup_claim(db)
    opportunity.provenance = {
        **opportunity.provenance,
        "form_fields": [
            {"label": "First name", "profile_key": "first_name", "kind": "text", "required": True},
        ],
    }
    for value in (None, " ", False, 10):
        person.facts = {**person.facts, "first_name": value}
        with pytest.raises(HTTPException) as error:
            prepare(db, person, opportunity)
        assert error.value.status_code == 409


def test_mapping_change_invalidates_approved_handoff(db):
    person, opportunity = setup_claim(db)
    claim = prepare(db, person, opportunity)
    approve(
        db,
        claim,
        person,
        opportunity,
        ApprovalInput(
            packet_hash=claim.packet_hash,
            facts_confirmed=True,
            legal_attestation_accepted=True,
            signer_name="Test person",
        ),
    )
    opportunity.revision += 1
    with pytest.raises(HTTPException):
        handoff(db, claim, person, opportunity)


def test_form_mapping_api_requires_login_and_csrf(client):
    assert client.put("/api/opportunities/missing/form-fields", json={}).status_code == 401
    from tests.test_api import login

    login(client)
    assert client.put("/api/opportunities/missing/form-fields", json={}).status_code == 403
