from datetime import datetime, timedelta, timezone

from app.engine import evaluate, fingerprint, priority, quality_flags


def test_date_criteria_require_real_iso_dates():
    rules = [{"field": "purchase_date", "op": "date_on_or_after", "value": "2024-01-01"}]
    assert evaluate(rules, {"purchase_date": "2024-06-01"})["status"] == "eligible"
    assert evaluate(rules, {"purchase_date": "2023-01-01"})["status"] == "ineligible"
    assert evaluate(rules, {"purchase_date": "2024-99-99"})["status"] == "needs_answer"


def test_missing_facts_never_become_eligible():
    result = evaluate([{"field": "purchased", "op": "eq", "value": True, "question": "Did you buy it?"}], {})
    assert result["status"] == "needs_answer"
    assert result["reasons"][0]["result"] == "unknown"


def test_false_fact_is_not_missing():
    result = evaluate([{"field": "purchased", "op": "eq", "value": True}], {"purchased": False})
    assert result["status"] == "ineligible"


def test_no_rules_are_not_proof_of_eligibility():
    assert evaluate([], {})["status"] == "needs_answer"


def test_wrong_types_do_not_satisfy_rules():
    assert evaluate([{"field": "loss", "op": "gte", "value": 10}], {"loss": "20"})["status"] == "needs_answer"
    assert (
        evaluate([{"field": "purchased", "op": "eq", "value": True}], {"purchased": 1})["status"]
        == "needs_answer"
    )


def test_explainable_eligible_result():
    result = evaluate([{"field": "state", "op": "in", "value": ["CA", "NY"]}], {"state": "CA"})
    assert result["status"] == "eligible"
    assert result["reasons"][0]["result"] == "pass"


def test_dedupe_ignores_tracking_and_trailing_slash():
    assert fingerprint("https://example.com/claim/?utm_source=x") == fingerprint("https://example.com/claim")
    assert fingerprint("https://example.com/claim?id=1") != fingerprint("https://example.com/claim?id=2")


def test_expired_or_unverified_never_file_now():
    now = datetime.now(timezone.utc)
    for deadline, verified in [(now - timedelta(days=1), True), (now + timedelta(days=1), False)]:
        result = priority("eligible", deadline, 500, "privacy", False, verified, now)
        assert "FILE NOW" not in result["queues"]


def test_quality_flags_reject_suspicious_urls_and_fee_requests():
    flags = quality_flags("http://127.0.0.1/claim", "Pay an upfront fee using gift cards")
    assert "https_required" in flags
    assert "non_public_host" in flags
    assert "payment_request" in flags
