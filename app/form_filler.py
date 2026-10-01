"""Deterministic filling of reviewed official fields from explicitly recorded facts."""

from fastapi import HTTPException


def fill_fields(opportunity, person):
    fields = []
    for field in opportunity.provenance.get("form_fields", []):
        value = person.facts.get(field["profile_key"])
        missing = value is None or (isinstance(value, str) and not value.strip())
        if field["required"] and missing:
            raise HTTPException(409, f"Record the required form answer: {field['label']}.")
        if not missing:
            kind = field["kind"]
            if kind == "checkbox" and type(value) is not bool:
                raise HTTPException(409, f"{field['label']} requires a true/false profile fact.")
            if kind == "number" and type(value) not in (int, float):
                raise HTTPException(409, f"{field['label']} requires a numeric profile fact.")
            if kind == "text" and not isinstance(value, str):
                raise HTTPException(409, f"{field['label']} requires a text profile fact.")
        fields.append({**field, "value": value, "source": "recorded_profile"})
    return fields
