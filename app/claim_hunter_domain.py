"""Claim Hunter profile completeness and queue scoring.

Ported from the separate Claim Hunter AI prototype into the existing Python
application without changing the current claim filing/handoff behavior.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

QUESTIONS = (
    ("states", 3),
    ("country", 1),
    ("breach_notices", 3),
    ("breach_companies", 3),
    ("apps", 2),
    ("grocery", 1),
    ("products", 2),
    ("receipts", 1),
    ("rx", 2),
    ("health_providers", 2),
    ("employers", 2),
    ("banks", 2),
    ("vehicles", 1),
    ("arrests", 1),
)

CLOSED_STATUSES = {"Paid", "Rejected", "paid", "rejected"}
HANDED_OFF_STATUSES = {
    "Submitted", "Approved", "Payment Pending",
    "submitted", "approved", "payment_pending",
}


def is_answered(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def profile_completeness(facts: dict[str, Any] | None) -> int:
    """Weighted 0-100 measure of how useful a profile is for screening."""
    facts = facts or {}
    total = sum(weight for _, weight in QUESTIONS)
    earned = sum(weight for key, weight in QUESTIONS if is_answered(facts.get(key)))
    return round((earned / total) * 100) if total else 0


def combined_score(ai_score: float | int, completeness: float | int) -> int:
    """Discount an AI match score when the underlying profile is incomplete."""
    score = max(0.0, min(100.0, float(ai_score)))
    complete = max(0.0, min(100.0, float(completeness)))
    return round(score * (0.5 + 0.5 * (complete / 100.0)))


def _deadline_date(value: date | datetime | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        try:
            return date.fromisoformat(value[:10])
        except (TypeError, ValueError):
            return None


def days_until(value: date | datetime | str | None, *, today: date | None = None) -> int | None:
    deadline = _deadline_date(value)
    if deadline is None:
        return None
    today = today or datetime.now(timezone.utc).date()
    return (deadline - today).days


def queue_score(
    deadline: date | datetime | str | None,
    eligibility_score: float | int | None,
    priority: int = 3,
    status: str = "Discovered",
    *,
    today: date | None = None,
) -> float:
    """Claim Hunter urgency/fit score. Negative means do not put in active queue."""
    if status in CLOSED_STATUSES or status in HANDED_OFF_STATUSES:
        return -1
    remaining = days_until(deadline, today=today)
    if remaining is not None and remaining < 0:
        return -1
    urgency = 10 if remaining is None else max(0, 60 - remaining)
    fit = 30 if eligibility_score is None else max(0, min(100, float(eligibility_score)))
    user_priority = max(1, min(5, int(priority)))
    return urgency + fit * 0.5 + (6 - user_priority) * 5
