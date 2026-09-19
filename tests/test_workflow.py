from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import make_engine
from app.engine import utcnow
from app.models import Base, Profile
from app.schemas import ApprovalInput, ConfirmationInput, OpportunityInput, VerifyInput
from app.services import approve, confirm, handoff, ingest, prepare, verify


@pytest.fixture
def db():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def setup_claim(db):
    profile = Profile(name="Test person", facts={"purchased": True})
    db.add(profile)
    db.flush()
    opportunity, _ = ingest(
        db,
        OpportunityInput(
            title="Synthetic test only",
            official_url="https://example.com/claim",
            record_type="open_claim",
            official_notice_url="https://example.com/notice",
            deadline=utcnow() + timedelta(days=5),
            rules=[{"field": "purchased", "op": "eq", "value": True}],
            attestation_text="Synthetic test declaration",
            administrator="Synthetic test administrator",
            source_excerpt="Synthetic source excerpt for testing only.",
            proof_required=False,
        ),
    )
    verify(
        db,
        opportunity,
        VerifyInput(
            administrator_verified=True,
            official_form_verified=True,
            criteria_and_deadline_verified=True,
            claim_window_confirmed=True,
            notes="Synthetic fixture reviewed for testing",
        ),
    )
    return profile, opportunity


def test_duplicate_opportunity_is_not_overwritten(db):
    item = OpportunityInput(title="Synthetic fixture", official_url="https://example.com/claim")
    first, duplicate = ingest(db, item)
    second, duplicate = ingest(db, item)
    assert duplicate and first.id == second.id


def test_unverified_opportunity_cannot_prepare(db):
    profile, opportunity = setup_claim(db)
    opportunity.verified = False
    with pytest.raises(HTTPException) as exc:
        prepare(db, profile, opportunity)
    assert exc.value.status_code == 409


def test_missing_proof_cannot_prepare_claim(db):
    person, opportunity = setup_claim(db)
    opportunity.proof_required = True
    with pytest.raises(HTTPException):
        prepare(db, person, opportunity)


def test_unknown_proof_requirements_block_verification(db):
    person, opportunity = setup_claim(db)
    opportunity.proof_required = None
    with pytest.raises(HTTPException):
        verify(
            db,
            opportunity,
            VerifyInput(
                administrator_verified=True,
                official_form_verified=True,
                criteria_and_deadline_verified=True,
                claim_window_confirmed=True,
                notes="Synthetic test review notes.",
            ),
        )


def test_duplicate_case_with_different_url_is_preserved(db):
    first, _ = ingest(
        db,
        OpportunityInput(
            title="Synthetic test fixture",
            official_url="https://example.com/one",
            case_number="Court 1: Test-123",
        ),
    )
    second, duplicate = ingest(
        db,
        OpportunityInput(
            title="Another source title",
            official_url="https://example.com/two",
            case_number="  court 1: test-123  ",
        ),
    )
    assert duplicate and first.id == second.id


def test_handoff_requires_explicit_approval(db):
    profile, opportunity = setup_claim(db)
    claim = prepare(db, profile, opportunity)
    with pytest.raises(HTTPException):
        handoff(db, claim, profile, opportunity)


def test_profile_change_invalidates_approval(db):
    profile, opportunity = setup_claim(db)
    claim = prepare(db, profile, opportunity)
    approve(
        db,
        claim,
        profile,
        opportunity,
        ApprovalInput(
            packet_hash=claim.packet_hash,
            facts_confirmed=True,
            legal_attestation_accepted=True,
            signer_name="Test Person",
        ),
    )
    profile.revision += 1
    with pytest.raises(HTTPException):
        handoff(db, claim, profile, opportunity)


def test_complete_human_submission_flow(db):
    profile, opportunity = setup_claim(db)
    claim = prepare(db, profile, opportunity)
    approve(
        db,
        claim,
        profile,
        opportunity,
        ApprovalInput(
            packet_hash=claim.packet_hash,
            facts_confirmed=True,
            legal_attestation_accepted=True,
            signer_name="Test Person",
        ),
    )
    handoff(db, claim, profile, opportunity)
    assert claim.status == "awaiting_human"
    confirm(
        db,
        claim,
        ConfirmationInput(
            reference="TEST-123",
            submitted_at=utcnow(),
            evidence="Synthetic confirmation receipt for test",
            human_completed=True,
        ),
    )
    assert claim.status == "submitted"
    with pytest.raises(HTTPException):
        prepare(db, profile, opportunity)


def test_confirmation_cannot_skip_approval_or_handoff(db):
    profile, opportunity = setup_claim(db)
    claim = prepare(db, profile, opportunity)
    with pytest.raises(HTTPException):
        confirm(
            db,
            claim,
            ConfirmationInput(
                reference="TEST",
                submitted_at=utcnow(),
                evidence="Synthetic test evidence",
                human_completed=True,
            ),
        )
