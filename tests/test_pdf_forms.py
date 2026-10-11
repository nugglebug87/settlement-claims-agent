import base64
import hashlib
import io

import pytest
from fastapi import HTTPException
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject
from reportlab.pdfgen import canvas

from app.pdf_forms import fill_pdf, inspect_pdf
from app.schemas import FormFieldsInput
from tests.test_api import login


def test_downloads_are_bound_to_session_and_expire(monkeypatch):
    from app import pdf_downloads

    monkeypatch.setattr(pdf_downloads, "_drafts", {})
    clock = [100.0]
    monkeypatch.setattr(pdf_downloads.time, "monotonic", lambda: clock[0])
    url = pdf_downloads.remember_pdf(b"test PDF bytes", "session-one", "test.pdf")
    token = url.rsplit("/", 1)[1]
    with pytest.raises(HTTPException):
        pdf_downloads.retrieve_pdf(token, "session-two")
    assert pdf_downloads.retrieve_pdf(token, "session-one")[0] == b"test PDF bytes"
    clock[0] += 121
    with pytest.raises(HTTPException):
        pdf_downloads.retrieve_pdf(token, "session-one")


def test_download_buffer_is_bounded(monkeypatch):
    from app import pdf_downloads

    monkeypatch.setattr(pdf_downloads, "_drafts", {})
    monkeypatch.setattr(pdf_downloads, "MAX_TOTAL_BYTES", 10)
    old = pdf_downloads.remember_pdf(b"123456", "session", "first.pdf").rsplit("/", 1)[1]
    new = pdf_downloads.remember_pdf(b"789012", "session", "second.pdf").rsplit("/", 1)[1]
    with pytest.raises(HTTPException):
        pdf_downloads.retrieve_pdf(old, "session")
    assert pdf_downloads.retrieve_pdf(new, "session")[0] == b"789012"


def source_pdf(interactive=False):
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=(612, 792))
    c.drawString(36, 750, "Synthetic form - tests only")
    if interactive:
        c.acroForm.textfield(name="FirstName", x=36, y=690, width=220, height=20)
        c.acroForm.checkbox(name="Cash", x=36, y=650, size=14)
    c.showPage()
    c.drawString(36, 750, "Second page preserved")
    c.save()
    data = out.getvalue()
    return base64.b64encode(data).decode(), hashlib.sha256(data).hexdigest()


def packet(digest, interactive=False):
    def target(name, y):
        return (
            {"field_name": name}
            if interactive
            else {"position": {"page": 1, "x": 40, "y": y, "width": 220, "height": 14}}
        )

    return {
        "pdf_sha256": digest,
        "form_fields": [
            {
                "label": "First name",
                "kind": "text",
                "value": "TEST PERSON",
                "pdf_target": target("FirstName", 82),
            },
            {"label": "Cash benefit", "kind": "checkbox", "value": True, "pdf_target": target("Cash", 127)},
        ],
    }


def test_paper_form_filling_preserves_pages_and_marks_unsigned():
    encoded, digest = source_pdf()
    output = fill_pdf(encoded, packet(digest))
    reader = PdfReader(io.BytesIO(output))
    assert len(reader.pages) == 2
    assert "TEST PERSON" in reader.pages[0].extract_text()
    assert "Second page preserved" in reader.pages[1].extract_text()
    assert all("DRAFT - UNSIGNED" in p.extract_text() for p in reader.pages)


def test_interactive_values_and_widget_appearances_survive_reopening():
    encoded, digest = source_pdf(True)
    info = inspect_pdf(encoded)
    assert {f["name"] for f in info["fields"]} == {"FirstName", "Cash"}
    reader = PdfReader(io.BytesIO(fill_pdf(encoded, packet(digest, True))))
    fields = reader.get_fields()
    assert fields["FirstName"]["/V"] == "TEST PERSON"
    assert fields["Cash"]["/V"] == "/Yes"
    widgets = [a.get_object() for a in reader.pages[0]["/Annots"]]
    assert all(w["/AP"]["/N"] for w in widgets)
    assert next(w for w in widgets if w["/T"] == "Cash")["/AS"] == "/Yes"


def test_false_checkbox_is_explicitly_cleared():
    encoded, digest = source_pdf(True)
    draft = packet(digest, True)
    draft["form_fields"][1]["value"] = False
    reader = PdfReader(io.BytesIO(fill_pdf(encoded, draft)))
    assert reader.get_fields()["Cash"]["/V"] == "/Off"


@pytest.mark.parametrize("change", ["digest", "missing", "page", "overflow", "outside", "unsupported"])
def test_invalid_or_changed_destinations_fail_without_a_draft(change):
    encoded, digest = source_pdf()
    draft = packet(digest)
    answer = draft["form_fields"][0]
    if change == "digest":
        draft["pdf_sha256"] = "0" * 64
    elif change == "missing":
        answer["pdf_target"] = None
    elif change == "page":
        answer["pdf_target"]["position"]["page"] = 3
    elif change == "overflow":
        answer["value"] = "TEST " * 100
    elif change == "outside":
        answer["pdf_target"]["position"]["x"] = 600
    else:
        answer["pdf_target"] = {"field_name": "Signature"}
    with pytest.raises(HTTPException):
        fill_pdf(encoded, draft)


def test_upload_rejects_malformed_encrypted_and_active_documents():
    with pytest.raises(HTTPException):
        inspect_pdf(base64.b64encode(b"not a PDF").decode())
    encoded, _ = source_pdf()
    writer = PdfWriter(clone_from=io.BytesIO(base64.b64decode(encoded)))
    writer.encrypt("test")
    out = io.BytesIO()
    writer.write(out)
    with pytest.raises(HTTPException):
        inspect_pdf(base64.b64encode(out.getvalue()).decode())
    writer = PdfWriter(clone_from=io.BytesIO(base64.b64decode(encoded)))
    writer.add_js("app.alert('test')")
    out = io.BytesIO()
    writer.write(out)
    with pytest.raises(HTTPException):
        inspect_pdf(base64.b64encode(out.getvalue()).decode())


def test_signed_pdf_is_rejected():
    encoded, _ = source_pdf(True)
    writer = PdfWriter(clone_from=io.BytesIO(base64.b64decode(encoded)))
    field = writer.pages[0]["/Annots"][0].get_object()
    field[NameObject("/FT")] = NameObject("/Sig")
    field[NameObject("/V")] = TextStringObject("Synthetic signature - not real")
    out = io.BytesIO()
    writer.write(out)
    with pytest.raises(HTTPException):
        inspect_pdf(base64.b64encode(out.getvalue()).decode())


def test_mapping_requires_every_pdf_destination_and_digest():
    data = {
        "fields": [{"label": "First", "profile_key": "first", "pdf_target": {"field_name": "FirstName"}}],
        "official_fields_reviewed": True,
    }
    with pytest.raises(ValueError):
        FormFieldsInput(**data)
    FormFieldsInput(**data, pdf_sha256="a" * 64)


def test_pdf_routes_require_login_and_csrf(client):
    encoded, _ = source_pdf()
    assert client.post("/api/pdf/inspect", json={"pdf_base64": encoded}).status_code == 401
    headers = login(client)
    assert client.post("/api/pdf/inspect", json={"pdf_base64": encoded}).status_code == 403
    response = client.post("/api/pdf/inspect", headers=headers, json={"pdf_base64": encoded})
    assert response.status_code == 200, response.text
    assert len(response.json()["pages"]) == 2


def test_pdf_export_uses_current_packet_and_original_source(client):
    from datetime import timedelta
    from app.engine import utcnow

    headers = login(client)
    client.put(
        "/api/profile",
        headers=headers,
        json={"name": "TEST ONLY", "facts": {"purchased": True, "first": "TEST PERSON", "cash": True}},
    )
    item = client.post(
        "/api/opportunities",
        headers=headers,
        json={
            "title": "Synthetic PDF case",
            "official_url": "https://example.com/pdf-case",
            "official_notice_url": "https://example.com/notice",
            "record_type": "open_claim",
            "administrator": "Test admin",
            "source_excerpt": "Synthetic source only",
            "deadline": (utcnow() + timedelta(days=5)).isoformat(),
            "proof_required": False,
            "attestation_text": "Test declaration",
            "rules": [{"field": "purchased", "op": "eq", "value": True}],
        },
    ).json()["opportunity"]
    path = "/api/opportunities/" + item["id"]
    assert (
        client.post(
            path + "/verify",
            headers=headers,
            json={
                "administrator_verified": True,
                "official_form_verified": True,
                "criteria_and_deadline_verified": True,
                "claim_window_confirmed": True,
                "notes": "Synthetic PDF fixture reviewed for tests",
            },
        ).status_code
        == 200
    )
    encoded, digest = source_pdf(True)
    fields = [{"label": "First name", "profile_key": "first", "pdf_target": {"field_name": "FirstName"}}]
    assert (
        client.put(
            path + "/form-fields",
            headers=headers,
            json={"fields": fields, "official_fields_reviewed": True, "pdf_sha256": digest},
        ).status_code
        == 200
    )
    claim = client.post(path + "/prepare", headers=headers).json()
    url = "/api/claims/" + claim["id"] + "/pdf"
    response = client.post(url, headers=headers, json={"pdf_base64": encoded})
    assert response.status_code == 200, response.text
    response = client.get(response.json()["download_url"])
    assert response.headers["content-type"] == "application/pdf"
    assert PdfReader(io.BytesIO(response.content)).get_fields()["FirstName"]["/V"] == "TEST PERSON"
    other, _ = source_pdf()
    assert client.post(url, headers=headers, json={"pdf_base64": other}).status_code == 409
    client.put(
        "/api/profile",
        headers=headers,
        json={"name": "TEST ONLY", "facts": {"purchased": True, "first": "CHANGED"}},
    )
    assert client.post(url, headers=headers, json={"pdf_base64": encoded}).status_code == 409
