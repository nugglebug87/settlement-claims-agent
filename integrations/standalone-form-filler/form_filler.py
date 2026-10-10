"""Offline-first AcroForm extraction and reviewed filling utilities."""
from io import BytesIO
import re
from pypdf import PdfReader, PdfWriter

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
    return [{"name": name, "type": str(data.get("/FT", "unknown"))} for name, data in fields.items()]

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
    writer = PdfWriter()
    writer.append(reader)
    writer.set_need_appearances_writer(True)
    for page in writer.pages:
        writer.update_page_form_field_values(page, {k: str(v) for k, v in reviewed_values.items()}, auto_regenerate=False)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
