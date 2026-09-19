import logging
import threading
from datetime import timedelta

import redis
from sqlalchemy import select

from app.config import settings
from app.db import Session
from app.discovery import run_source
from app.engine import aware, record_classification, utcnow
from app.models import Claim, Opportunity, Source
from app.services import notify

log = logging.getLogger(__name__)


def redis_client():
    return (
        redis.Redis.from_url(settings.redis_url, socket_timeout=3, socket_connect_timeout=3)
        if settings.redis_url
        else None
    )


def monitor(db):
    now = utcnow()
    for opportunity in db.scalars(select(Opportunity)):
        if opportunity.deadline and record_classification(opportunity) == "open_claim":
            days = (aware(opportunity.deadline) - now).total_seconds() / 86400
            if 0 <= days <= 14:
                band = "1" if days <= 1 else "3" if days <= 3 else "14"
                notify(
                    db,
                    f"deadline:{opportunity.id}:{aware(opportunity.deadline).isoformat()}:{band}",
                    "Claim deadline approaching",
                    f"{opportunity.title}: deadline {aware(opportunity.deadline).isoformat()}. Eligibility and approval are still required.",
                )
    for claim in db.scalars(select(Claim).where(Claim.status.notin_(["paid", "rejected", "prepared"]))):
        if claim.expected_payment_date and aware(claim.expected_payment_date) <= now:
            notify(
                db,
                f"payment:{claim.id}:{now.date()}",
                "Check expected payment",
                "The recorded expected payment date has arrived. Check the administrator and record actual evidence; payment is not assumed.",
            )
        if aware(claim.updated_at) < now - timedelta(days=14):
            notify(
                db,
                f"check:{claim.id}:{now.strftime('%Y-%W')}",
                "Claim status check due",
                "Review the official administrator portal or correspondence and record the status with evidence.",
            )


def due_sources(db, now=None):
    now = now or utcnow()
    result = []
    # One due source per stream per tick prevents breach/government leads being starved by directories.
    for stream in ("settlements", "government_refunds", "breach_announcements"):
        sources = db.scalars(
            select(Source)
            .where(Source.enabled.is_(True), Source.stream == stream)
            .order_by(Source.last_run.asc().nullsfirst(), Source.created_at.asc())
        )
        due = next(
            (s for s in sources if not s.last_run or aware(s.last_run) <= now - timedelta(days=1)), None
        )
        if due:
            result.append(due)
    return result


def tick():
    client = redis_client()
    lock = client.lock("settlement-agent:monitor", timeout=600, blocking_timeout=0) if client else None
    try:
        if lock and not lock.acquire(blocking=False):
            return
        with Session() as db:
            monitor(db)
            db.commit()
            # Bound each tick to three sources; each source is refreshed at most daily.
            due = due_sources(db)
            for source in due:
                run_source(db, source)
                db.commit()
    finally:
        if lock and lock.owned():
            lock.release()


def start_worker():
    stop = threading.Event()

    def loop():
        while not stop.wait(max(30, settings.monitor_interval_seconds)):
            try:
                tick()
            except Exception:
                log.error("Monitor tick failed; retry on next interval", exc_info=False)

    thread = threading.Thread(target=loop, daemon=True, name="claims-monitor")
    thread.start()
    return stop
