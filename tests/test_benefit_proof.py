import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models import Evidence
from app.schemas import FormField, OpportunityInput
from app.services import ingest, prepare
from tests.test_workflow import setup_claim


def benefit(db, selected):
    person, opportunity = setup_claim(db)
    person.facts = {**person.facts, "losses": selected}
    opportunity.provenance = {
        **opportunity.provenance,
        "form_fields": [
            dict(
                label="Documented losses",
                profile_key="losses",
                kind="checkbox",
                required=True,
                evidence_when_selected=True,
            ),
        ],
    }
    return person, opportunity


def test_selected_loss_benefit_blocks_no_proof_cash_opportunity(db):
    person, opportunity = benefit(db, True)
    assert opportunity.proof_required is False
    with pytest.raises(HTTPException) as error:
        prepare(db, person, opportunity)
    assert error.value.status_code == 409


def test_unselected_loss_benefit_does_not_require_proof(db):
    person, opportunity = benefit(db, False)
    assert prepare(db, person, opportunity).packet["form_fields"][0]["value"] is False


def test_evidence_for_another_case_does_not_satisfy_selected_benefit(db):
    person, opportunity = benefit(db, True)
    other, _ = ingest(
        db, OpportunityInput(title="Unrelated test case", official_url="https://example.com/other-case")
    )
    db.add(
        Evidence(
            profile_id=person.id,
            opportunity_id=other.id,
            reference="OTHER-CASE",
            description="Synthetic unrelated evidence",
        )
    )
    with pytest.raises(HTTPException):
        prepare(db, person, opportunity)


def test_selected_benefit_with_case_evidence_prepares(db):
    person, opportunity = benefit(db, True)
    db.add(
        Evidence(
            profile_id=person.id,
            opportunity_id=opportunity.id,
            reference="TEST-RECEIPT",
            description="Synthetic loss evidence for this case",
        )
    )
    claim = prepare(db, person, opportunity)
    assert claim.packet["form_fields"][0]["evidence_when_selected"] is True
    assert claim.packet["evidence"][0]["reference"] == "TEST-RECEIPT"


def test_evidence_condition_cannot_be_attached_to_free_text():
    with pytest.raises(ValidationError):
        FormField(label="Name", profile_key="name", kind="text", evidence_when_selected=True)
