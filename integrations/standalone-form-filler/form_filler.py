"""Offline-first AcroForm extraction and reviewed filling utilities."""
from io import BytesIO
import re
from pypdf import PdfReader
import fitz

COMB_FLAG = 1 << 24

ALIASES = {
    "full_name": {"full name", "name", "claimant name", "your name"},
    "email": {"email", "email address", "e-mail"},
    "phone": {"phone", "phone number", "telephone"},
    "address": {"address", "street address", "mailing address"},
    "city": {"city"}, "state": {"state"}, "zip": {"zip", "zip code", "postal code"},
}

def extract_fields(pdf_bytes):
    reader = PdfReader(BytesIO(pdf_bytes))
    fields = reader.get_fields() or {}
    return [{"name": name, "type": str(data.get("/FT", "unknown")), "max_length": data.get("/MaxLen"), "comb": bool(int(data.get("/Ff", 0)) & COMB_FLAG)} for name, data in fields.items()]

def suggest_mappings(field_names, profile):
    result = {}
    for name in field_names:
        normalized = re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()
        for key, aliases in ALIASES.items():
            if normalized in aliases and key in profile and profile[key] is not None:
                result[name] = str(profile[key])
                break
    return result

def fill_pdf(pdf_bytes, reviewed_values):
    reader = PdfReader(BytesIO(pdf_bytes))
    available = set((reader.get_fields() or {}).keys())
    unknown = set(reviewed_values) - available
    if unknown:
        raise ValueError("Unknown form fields: " + ", ".join(sorted(unknown)))
    for name, value in reviewed_values.items():
        field = (reader.get_fields() or {})[name]
        limit = field.get("/MaxLen")
        if limit and len(str(value)) > int(limit):
            raise ValueError(f"{name} accepts at most {limit} characters; received {len(str(value))}")
    # PyMuPDF regenerates true comb-field appearance streams with one glyph per cell.
    # pypdf's generic appearance generation can clip or misalign these forms.
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    updated = set()
    for page in document:
        for widget in page.widgets() or []:
            if widget.field_name in reviewed_values:
                widget.field_value = str(reviewed_values[widget.field_name])
                widget.update()
                updated.add(widget.field_name)
    if set(reviewed_values) - updated:
        raise ValueError("Some form fields could not be located")
    output = document.tobytes(garbage=3, deflate=True)
    document.close()
    return output
