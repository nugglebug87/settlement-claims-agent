from datetime import date

from app.claim_hunter_domain import combined_score, days_until, profile_completeness, queue_score


def test_profile_completeness_empty_and_full():
    assert profile_completeness({}) == 0
    full = {
        "states": "MN", "country": "US", "breach_notices": False,
        "breach_companies": "None known", "apps": ["Amazon"], "grocery": True,
        "products": "Phone", "receipts": False, "rx": True,
        "health_providers": "Clinic", "employers": "Employer", "banks": "Bank",
        "vehicles": "Car", "arrests": False,
    }
    assert profile_completeness(full) == 100


def test_false_boolean_counts_as_answered():
    assert profile_completeness({"breach_notices": False}) > 0


def test_combined_score_discounts_thin_profile():
    assert combined_score(100, 0) == 50
    assert combined_score(100, 100) == 100
    assert combined_score(80, 50) == 60


def test_days_until_is_deterministic():
    assert days_until("2026-10-15", today=date(2026, 10, 6)) == 9


def test_queue_score_excludes_expired_and_closed():
    today = date(2026, 10, 6)
    assert queue_score("2026-10-01", 90, status="Likely Eligible", today=today) == -1
    assert queue_score("2026-10-20", 90, status="Paid", today=today) == -1


def test_queue_score_rewards_urgency_and_fit():
    today = date(2026, 10, 6)
    urgent = queue_score("2026-10-10", 90, priority=1, today=today)
    later = queue_score("2026-11-20", 50, priority=3, today=today)
    assert urgent > later
