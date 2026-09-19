from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Rule(Input):
    field: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    op: Literal["eq", "in", "gte", "lte", "date_on_or_after", "date_on_or_before"]
    value: Any
    question: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def valid_value(self):
        from datetime import date
        import math

        def scalar(v):
            return type(v) in (str, bool, int, float) and (not isinstance(v, float) or math.isfinite(v))

        if self.op == "in":
            if not isinstance(self.value, list) or not self.value or not all(scalar(v) for v in self.value):
                raise ValueError("One-of requires a nonempty list of scalar values.")
        elif not scalar(self.value):
            raise ValueError("Rule value must be a finite scalar, not null.")
        if self.op in {"gte", "lte"} and type(self.value) not in (int, float):
            raise ValueError("Numeric comparison requires a number.")
        if self.op.startswith("date_"):
            if not isinstance(self.value, str):
                raise ValueError("Date comparison requires an ISO date string.")
            date.fromisoformat(self.value)
        return self


class OpportunityInput(Input):
    title: str = Field(min_length=3, max_length=300)
    official_url: str = Field(max_length=2000)
    case_number: str | None = Field(default=None, max_length=200)
    administrator: str | None = Field(default=None, max_length=300)
    defendant: str | None = Field(default=None, max_length=300)
    record_type: Literal[
        "unknown",
        "open_claim",
        "investigation",
        "breach_announcement",
        "proposed_settlement",
        "automatic_payment",
        "expired",
        "closed",
    ] = "unknown"
    program_type: Literal["settlements", "government_refunds", "breach_announcements"] = "settlements"
    official_notice_url: str | None = Field(default=None, max_length=2000)
    claim_opens_at: datetime | None = None
    eligibility_start: date | None = None
    eligibility_end: date | None = None
    documentation_requirements: str | None = Field(default=None, max_length=10000)
    payment_timeline: str | None = Field(default=None, max_length=5000)
    category: Literal["consumer", "data_breach", "privacy", "tcpa", "other"] = "other"
    summary: str = Field(default="", max_length=10000)
    deadline: datetime | None = None
    expected_payout: float | None = Field(default=None, ge=0, le=10000000, allow_inf_nan=False)
    proof_required: bool | None = None
    rules: list[Rule] = Field(default_factory=list, max_length=100)
    attestation_text: str | None = Field(default=None, max_length=20000)
    source_excerpt: str = Field(default="", max_length=30000)

    @field_validator("official_url", "official_notice_url")
    @classmethod
    def valid_url(cls, value):
        if value is None:
            return None
        from urllib.parse import urlsplit

        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("Use an HTTP(S) URL without embedded credentials")
        return value

    @field_validator("deadline", "claim_opens_at")
    @classmethod
    def timezone_required(cls, value):
        if value and value.tzinfo is None:
            raise ValueError("Deadline requires an explicit timezone offset")
        return value.astimezone(timezone.utc) if value else None

    @model_validator(mode="after")
    def valid_periods(self):
        if self.eligibility_start and self.eligibility_end and self.eligibility_start > self.eligibility_end:
            raise ValueError("Eligibility start must be on or before eligibility end.")
        if self.claim_opens_at and self.deadline and self.claim_opens_at >= self.deadline:
            raise ValueError("Claim opening must precede deadline.")
        return self


class ProfileInput(Input):
    name: str = Field(min_length=1, max_length=200)
    facts: dict[str, Any] = Field(default_factory=dict)

    @field_validator("facts")
    @classmethod
    def validate_facts(cls, value):
        import json

        if len(json.dumps(value, allow_nan=False)) > 30000:
            raise ValueError("Profile is too large")
        if any(not isinstance(v, (str, bool, int, float, type(None))) for v in value.values()):
            raise ValueError("Facts must be scalar values or null")
        return value


class VerifyInput(Input):
    administrator_verified: Literal[True]
    official_form_verified: Literal[True]
    criteria_and_deadline_verified: Literal[True]
    claim_window_confirmed: Literal[True]
    notes: str = Field(min_length=10, max_length=5000)


class ApprovalInput(Input):
    packet_hash: str
    facts_confirmed: Literal[True]
    legal_attestation_accepted: Literal[True]
    signer_name: str = Field(min_length=2, max_length=200)


class ConfirmationInput(Input):
    reference: str = Field(min_length=1, max_length=300)
    submitted_at: datetime
    evidence: str = Field(min_length=10, max_length=10000)
    human_completed: Literal[True]

    @field_validator("submitted_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("Submission time requires a timezone")
        return value


class StatusInput(Input):
    status: Literal["submitted", "under_review", "needs_action", "approved", "rejected", "paid"]
    evidence: str = Field(min_length=10, max_length=10000)
    actual_payout: float | None = Field(default=None, ge=0, le=10000000, allow_inf_nan=False)
    expected_payment_date: datetime | None = None

    @field_validator("expected_payment_date")
    @classmethod
    def timezone_required(cls, value):
        if value and value.tzinfo is None:
            raise ValueError("Expected payment date requires a timezone")
        return value.astimezone(timezone.utc) if value else None


class SourceInput(Input):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(max_length=2000)
    kind: Literal["json", "html_ai", "html_links"] = "json"
    stream: Literal["settlements", "government_refunds", "breach_announcements"] = "settlements"
    source_role: Literal["directory", "administrator", "government", "breach_notice"] = "directory"
    enabled: bool = False


class LoginInput(Input):
    password: str = Field(max_length=500)


class EvidenceInput(Input):
    reference: str = Field(min_length=3, max_length=1000)
    description: str = Field(min_length=10, max_length=5000)
    personally_verified: Literal[True]


class DuplicateReviewInput(Input):
    distinct_case_confirmed: Literal[True]
    notes: str = Field(min_length=20, max_length=5000)
