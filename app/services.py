import hashlib
import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select

from app.engine import aware, case_key, evaluate, fingerprint, quality_flags, utcnow
from app.models import Audit, Claim, Evidence, Notification, Opportunity


def audit(db, action, entity_id, details=None, actor="owner"):
    db.add(Audit(action=action, entity_id=entity_id, details=details or {}, actor=actor))


def notify(db, key, title, message):
    if not db.scalar(select(Notification).where(Notification.dedupe_key == key)):
        db.add(Notification(dedupe_key=key, title=title, message=message))


def ingest(db, data, source_id=None):
    key = fingerprint(data.official_url)
    existing = db.scalar(select(Opportunity).where(Opportunity.fingerprint == key))
    if not existing and data.case_number:
        existing = db.scalar(select(Opportunity).where(Opportunity.case_key == case_key(data.case_number)))
    if existing:
        audit(db, "discovery.duplicate", existing.id, {"source_id": source_id})
        return existing, True
    values = data.model_dump(exclude={"source_excerpt"})
    if values["case_number"]:
        values["case_number"] = values["case_number"].strip()
    opportunity = Opportunity(
        **values,
        fingerprint=key,
        case_key=case_key(data.case_number),
        source_id=source_id,
        provenance={
            "url": data.official_url,
            "excerpt": data.source_excerpt,
            "captured_at": utcnow().isoformat(),
            "method": "source_import" if source_id else "manual",
        },
        quality_flags=quality_flags(data.official_url, data.source_excerpt + " " + data.summary),
    )
    db.add(opportunity)
    db.flush()
    audit(db, "opportunity.discovered", opportunity.id)
    notify(db, f"discovered:{opportunity.id}", "Opportunity needs review", opportunity.title)
    return opportunity, False


def verify(db, opportunity, data):
    if any(
        f in opportunity.quality_flags
        for f in ["https_required", "non_public_host", "embedded_credentials", "payment_request"]
    ):
        raise HTTPException(
            409,
            "Blocking fraud/quality flags must be resolved by correcting the opportunity before verification.",
        )
    if (
        not opportunity.deadline
        or not opportunity.rules
        or not opportunity.attestation_text
        or not opportunity.administrator
        or not opportunity.provenance.get("excerpt")
        or opportunity.proof_required is None
    ):
        raise HTTPException(
            409,
            "Record the administrator, source excerpt, official deadline, proof requirements, eligibility criteria, and exact legal attestation before verification.",
        )
    opportunity.verified = True
    opportunity.verification_notes = data.notes
    opportunity.revision += 1
    audit(db, "opportunity.verified", opportunity.id, data.model_dump())


def ready(profile, opportunity):
    if not opportunity.verified:
        raise HTTPException(409, "Administrator and official form require human verification.")
    if not opportunity.deadline or aware(opportunity.deadline) <= utcnow():
        raise HTTPException(409, "Deadline is unknown or has passed.")
    result = evaluate(opportunity.rules, profile.facts)
    if result["status"] != "eligible":
        raise HTTPException(409, "Resolve eligibility answers before preparing or approving this claim.")
    if not opportunity.attestation_text:
        raise HTTPException(409, "Exact official legal attestation is required.")
    return result


def prepare(db, profile, opportunity):
    result = ready(profile, opportunity)
    evidence = list(
        db.scalars(
            select(Evidence).where(
                Evidence.profile_id == profile.id, Evidence.opportunity_id == opportunity.id
            )
        )
    )
    if opportunity.proof_required and not evidence:
        raise HTTPException(
            409, "This settlement requires proof. Record an actual evidence reference before preparing."
        )
    claim = db.scalar(
        select(Claim)
        .where(Claim.profile_id == profile.id, Claim.opportunity_id == opportunity.id)
        .with_for_update()
    )
    if claim and claim.status not in {"prepared", "approved_for_handoff"}:
        raise HTTPException(409, "A claim already exists or was handed off. Duplicate filing is blocked.")
    # Include only facts required by this claim, never inferred purchases or losses.
    packet = {
        "opportunity_id": opportunity.id,
        "title": opportunity.title,
        "official_url": opportunity.official_url,
        "profile_revision": profile.revision,
        "opportunity_revision": opportunity.revision,
        "facts": {r["field"]: profile.facts.get(r["field"]) for r in opportunity.rules},
        "evidence": [{"id": e.id, "reference": e.reference, "description": e.description} for e in evidence],
        "eligibility": result,
        "attestation_text": opportunity.attestation_text,
        "prepared_at": utcnow().isoformat(),
        "deadline": aware(opportunity.deadline).isoformat(),
    }
    digest = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
    if not claim:
        claim = Claim(profile_id=profile.id, opportunity_id=opportunity.id)
        db.add(claim)
    claim.packet, claim.packet_hash, claim.status, claim.approval = packet, digest, "prepared", None
    claim.updated_at = utcnow()
    db.flush()
    audit(db, "claim.prepared", claim.id, {"packet_hash": digest})
    return claim


def current_packet(claim, profile, opportunity):
    ready(profile, opportunity)
    if (
        claim.packet["profile_revision"] != profile.revision
        or claim.packet["opportunity_revision"] != opportunity.revision
    ):
        raise HTTPException(409, "Profile or opportunity changed. Prepare and approve a fresh packet.")


def approve(db, claim, profile, opportunity, data):
    current_packet(claim, profile, opportunity)
    if claim.status != "prepared" or data.packet_hash != claim.packet_hash:
        raise HTTPException(409, "Approval must match the current prepared packet.")
    claim.approval = {
        **data.model_dump(),
        "approved_at": utcnow().isoformat(),
        "attestation_text": opportunity.attestation_text,
    }
    claim.status = "approved_for_handoff"
    claim.updated_at = utcnow()
    audit(
        db, "claim.approved", claim.id, {"packet_hash": claim.packet_hash, "legal_attestation_accepted": True}
    )


def handoff(db, claim, profile, opportunity):
    current_packet(claim, profile, opportunity)
    if claim.status != "approved_for_handoff" or not claim.approval:
        raise HTTPException(409, "Explicit facts and legal-attestation approval are required first.")
    claim.status = "awaiting_human"
    claim.updated_at = utcnow()
    audit(db, "claim.human_handoff", claim.id)
    return {
        "url": opportunity.official_url,
        "instructions": "Complete the official form yourself, including CAPTCHA, identity verification, evidence and legal declarations. Return with the actual confirmation. No form has been submitted by this application.",
    }


def confirm(db, claim, data):
    if claim.status != "awaiting_human" or not claim.approval:
        raise HTTPException(409, "Confirmation requires an approved claim handed off to the user.")
    if data.submitted_at > utcnow():
        raise HTTPException(422, "Submission time cannot be in the future.")
    if data.submitted_at < datetime.fromisoformat(claim.approval["approved_at"]):
        raise HTTPException(422, "Submission time must be after this packet was approved.")
    claim.confirmation = data.model_dump(mode="json")
    claim.status, claim.updated_at = "submitted", utcnow()
    audit(
        db, "claim.confirmation_recorded", claim.id, {"reference": data.reference, "evidence": data.evidence}
    )
    notify(
        db,
        f"submitted:{claim.id}",
        "Submission confirmation recorded",
        "Your user-provided receipt has been saved. Administrator acceptance is not yet verified.",
    )


def update_status(db, claim, data):
    transitions = {
        "submitted": {"under_review", "needs_action", "approved", "rejected", "paid"},
        "under_review": {"needs_action", "approved", "rejected", "paid"},
        "needs_action": {"submitted", "under_review", "approved", "rejected", "paid"},
        "approved": {"needs_action", "paid", "rejected"},
        "rejected": {"under_review"},
        "paid": set(),
    }
    if data.status not in transitions.get(claim.status, set()):
        raise HTTPException(409, "Invalid claim status transition.")
    if data.status == "paid" and data.actual_payout is None:
        raise HTTPException(422, "Record the actual payment amount from your receipt.")
    if data.status != "paid" and data.actual_payout is not None:
        raise HTTPException(422, "Actual payment amount belongs to a paid status only.")
    before = claim.status
    claim.status, claim.updated_at = data.status, utcnow()
    claim.actual_payout = data.actual_payout
    claim.expected_payment_date = data.expected_payment_date
    audit(db, "claim.status_changed", claim.id, {"previous": before, **data.model_dump(mode="json")})
    notify(
        db,
        f"status:{claim.id}:{claim.updated_at.isoformat()}",
        "Claim status updated",
        f"Claim is now {claim.status.replace('_', ' ')}.",
    )
