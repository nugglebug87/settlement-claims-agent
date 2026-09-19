"""Conservative, deterministic decisions. Unknown information stays unknown."""

import hashlib
import ipaddress
from datetime import date, datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def canonical_url(url):
    parts = urlsplit(url)
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query)
        if not k.lower().startswith("utm_") and k not in {"fbclid", "gclid"}
    )
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", urlencode(query), "")
    )


def fingerprint(url):
    return hashlib.sha256(canonical_url(url).encode()).hexdigest()


def case_key(case_number):
    return " ".join(case_number.casefold().split()) if case_number and case_number.strip() else None


def evaluate(rules, facts):
    reasons = []
    for rule in rules:
        field, op, expected = rule["field"], rule["op"], rule.get("value")
        actual = facts.get(field)
        result = "unknown"
        if actual is not None:
            if (
                op in ("date_on_or_after", "date_on_or_before")
                and isinstance(actual, str)
                and isinstance(expected, str)
            ):
                try:
                    actual_date, expected_date = date.fromisoformat(actual), date.fromisoformat(expected)
                    passed = (
                        actual_date >= expected_date
                        if op == "date_on_or_after"
                        else actual_date <= expected_date
                    )
                    result = "pass" if passed else "fail"
                except ValueError:
                    pass
            elif op == "in" and isinstance(expected, list) and any(type(actual) is type(v) for v in expected):
                result = "pass" if any(type(actual) is type(v) and actual == v for v in expected) else "fail"
            elif type(actual) is type(expected) or (
                type(actual) in (int, float) and type(expected) in (int, float)
            ):
                if op == "eq":
                    result = "pass" if actual == expected else "fail"
                elif op in ("gte", "lte") and type(actual) in (int, float):
                    result = "pass" if (actual >= expected if op == "gte" else actual <= expected) else "fail"
        reasons.append(
            {
                "field": field,
                "question": rule.get("question", field),
                "operator": op,
                "expected": expected,
                "actual": actual,
                "result": result,
            }
        )
    results = {r["result"] for r in reasons}
    status = (
        "ineligible"
        if "fail" in results
        else "needs_answer"
        if not reasons or "unknown" in results
        else "eligible"
    )
    return {
        "status": status,
        "reasons": reasons,
        "notice": "Matches recorded criteria only; administrator makes the final determination.",
    }


def priority(eligibility, deadline, payout, category, proof_required, verified, now=None):
    now = now or utcnow()
    days = (aware(deadline) - now).total_seconds() / 86400 if deadline else None
    queues = []
    if eligibility == "needs_answer":
        queues.append("NEEDS ANSWER")
    if category in {"data_breach", "privacy", "tcpa"}:
        queues.append({"data_breach": "DATA BREACH", "privacy": "PRIVACY", "tcpa": "TCPA"}[category])
    if proof_required is False:
        queues.append("NO PROOF")
    if payout is not None and payout >= 100:
        queues.append("HIGH VALUE")
    actionable = eligibility == "eligible" and verified and days is not None and days >= 0
    if actionable and days <= 14:
        queues.append("FILE NOW")
    score = (
        (40 if actionable else 0)
        + (max(0, 30 - int(days)) if actionable and days < 30 else 0)
        + (min(20, int(payout / 25)) if payout else 0)
        + (10 if proof_required is False else 0)
    )
    return {
        "score": score,
        "queues": queues,
        "days_remaining": round(days, 1) if days is not None else None,
        "expired": days is not None and days < 0,
    }


def quality_flags(url, text):
    parts = urlsplit(url)
    flags = []
    if parts.scheme != "https":
        flags.append("https_required")
    host = parts.hostname or ""
    try:
        if not ipaddress.ip_address(host).is_global:
            flags.append("non_public_host")
    except ValueError:
        if "." not in host or host.endswith((".local", ".internal", ".localhost")):
            flags.append("non_public_host")
    if parts.username or parts.password:
        flags.append("embedded_credentials")
    if "xn--" in host:
        flags.append("internationalized_domain_review")
    if any(
        word in text.lower()
        for word in ["upfront fee", "gift card", "seed phrase", "wire transfer", "processing fee"]
    ):
        flags.append("payment_request")
    return flags
