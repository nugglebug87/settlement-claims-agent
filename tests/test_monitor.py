from datetime import timedelta

from sqlalchemy import select

from app.engine import utcnow
from app.models import Claim, Notification, Source
from app.monitor import monitor
from app.discovery import run_source
from tests.test_workflow import setup_claim


def test_deadline_notifications_are_idempotent(db):
    setup_claim(db)
    monitor(db)
    db.flush()
    monitor(db)
    db.flush()
    notes = list(db.scalars(select(Notification).where(Notification.title == "Claim deadline approaching")))
    assert len(notes) == 1


def test_monitor_never_invents_payment(db):
    person, opportunity = setup_claim(db)
    claim = Claim(
        profile_id=person.id,
        opportunity_id=opportunity.id,
        status="submitted",
        packet={},
        packet_hash="test",
        expected_payment_date=utcnow() - timedelta(days=1),
    )
    db.add(claim)
    db.flush()
    monitor(db)
    assert claim.status == "submitted" and claim.actual_payout is None
    assert db.scalar(select(Notification).where(Notification.title == "Check expected payment")) is not None


def test_json_source_run_imports_and_deduplicates(db, monkeypatch):
    source = Source(name="Synthetic source", url="https://example.com/feed", kind="json")
    db.add(source)
    db.flush()
    monkeypatch.setattr(
        "app.discovery.fetch_source",
        lambda url: (
            '{"opportunities":[{"title":"SYNTHETIC fixture","official_url":"https://example.com/claim"}]}',
            "application/json",
        ),
    )
    first = run_source(db, source)
    second = run_source(db, source)
    assert first.status == "completed" and first.imported == 1
    assert second.status == "completed" and second.duplicates == 1


def test_source_failure_is_visible_without_sensitive_exception_text(db, monkeypatch):
    source = Source(name="Synthetic source", url="https://example.com/feed", kind="json")
    db.add(source)
    db.flush()

    def fail(url):
        raise ValueError("SECRET SHOULD NOT BE STORED")

    monkeypatch.setattr("app.discovery.fetch_source", fail)
    result = run_source(db, source)
    assert result.status == "failed" and "SECRET" not in result.message
    assert (
        db.scalar(select(Notification).where(Notification.title == "Discovery source needs attention"))
        is not None
    )
