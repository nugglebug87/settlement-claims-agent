"""Stateless, unsigned PDF drafts from exact reviewed packet answers."""

import base64
import hashlib
import io
import threading

import pypdfium2 as pdfium
from fastapi import HTTPException
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

MAX_BYTES = 3 * 1024 * 1024
_render_lock = threading.Lock()


def read_upload(encoded):
    try:
        data = base64.b64decode(encoded, validate=True)
        if len(data) > MAX_BYTES:
            raise ValueError()
        if not data.startswith(b"%PDF-"):
            raise ValueError()
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 10:
            raise ValueError()
        root = reader.trailer["/Root"]
        form = root.get("/AcroForm")
        if form and "/XFA" in form.get_object():
            raise ValueError()
        if "/OpenAction" in root or "/AA" in root or "/Names" in root:
            raise ValueError()
        for page in reader.pages:
            if page.rotation or list(page.cropbox) != list(page.mediabox):
                raise ValueError()
            if float(page.mediabox.left) != 0 or float(page.mediabox.bottom) != 0:
                raise ValueError()
            if not (72 <= page.mediabox.width <= 2000 and 72 <= page.mediabox.height <= 2000):
                raise ValueError()
            for ref in page.get("/Annots", []):
                annotation = ref.get_object()
                if "/A" in annotation or "/AA" in annotation:
                    raise ValueError()
        fields = reader.get_fields() or {}
        widgets = widget_fields(reader)
        for name, field in fields.items():
            if field.get("/FT") == "/Sig" and field.get("/V"):
                raise ValueError()
            if field.get("/AA"):
                raise ValueError()
        # Reject ambiguous/orphan widgets rather than inventing a form tree.
        for name, widget, owner in widgets:
            canonical = fields.get(name)
            if not canonical or canonical.indirect_reference != owner.indirect_reference:
                raise ValueError()
            if widget.get("/AA"):
                raise ValueError()
        return data, reader
    except Exception as exc:
        raise HTTPException(
            422,
            "Use an unsigned PDF up to 3 MB and 10 pages, with unrotated full pages and no active actions, XFA or ambiguous form fields.",
        ) from exc


def widget_fields(reader):
    result = []
    for page in reader.pages:
        for ref in page.get("/Annots", []):
            widget = ref.get_object()
            if widget.get("/Subtype") != "/Widget":
                continue
            owner = widget
            if "/T" not in owner and "/Parent" in owner:
                owner = owner["/Parent"]
            parts, node = [], owner
            while node:
                if node.get("/T"):
                    parts.insert(0, str(node["/T"]))
                node = node.get("/Parent")
                node = node.get_object() if node else None
            result.append((".".join(parts), widget, owner))
    return result


def inspect_pdf(encoded):
    data, reader = read_upload(encoded)
    fields = reader.get_fields() or {}
    result = {
        "sha256": hashlib.sha256(data).hexdigest(),
        "fields": [
            {"name": name, "kind": "checkbox" if f.get("/FT") == "/Btn" else "text"}
            for name, f in fields.items()
            if f.get("/FT") in {"/Tx", "/Btn"} and not int(f.get("/Ff", 0)) & (1 | 32768 | 65536)
        ],
        "pages": [],
    }
    with _render_lock, pdfium.PdfDocument(data) as doc:
        for index, page in enumerate(reader.pages):
            rendered_page = doc[index]
            bitmap = rendered_page.render(scale=min(1.25, 1000 / float(page.mediabox.width)))
            try:
                output = io.BytesIO()
                bitmap.to_pil().save(output, format="PNG")
            finally:
                bitmap.close()
                rendered_page.close()
            result["pages"].append(
                {
                    "page": index + 1,
                    "width": float(page.mediabox.width),
                    "height": float(page.mediabox.height),
                    "image": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode(),
                }
            )
    return result


def answer_text(value, label):
    text = "" if value is None else str(value)
    try:
        text.encode("cp1252")
    except UnicodeEncodeError as exc:
        raise HTTPException(
            422, f"{label}: this PDF font cannot represent the answer. Use the official form."
        ) from exc
    if any(ord(c) < 32 for c in text):
        raise HTTPException(422, f"{label}: use a single line without control characters.")
    return text


def fill_pdf(encoded, packet):
    data, reader = read_upload(encoded)
    if not packet.get("pdf_sha256") or hashlib.sha256(data).hexdigest() != packet["pdf_sha256"]:
        raise HTTPException(409, "Choose the exact original PDF reviewed for this packet.")
    answers = packet.get("form_fields", [])
    if not answers or any(not f.get("pdf_target") for f in answers):
        raise HTTPException(409, "Review PDF destinations for every prepared field first.")
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    fields = reader.get_fields() or {}
    widgets = widget_fields(reader)
    values, overlays = {}, {}
    for answer in answers:
        target, value, label = answer["pdf_target"], answer["value"], answer["label"]
        name = target.get("field_name")
        if name:
            field = fields.get(name)
            if not field or field.get("/FT") not in {"/Tx", "/Btn"}:
                raise HTTPException(
                    422, f"{label}: PDF field is missing or unsupported. Signature fields cannot be filled."
                )
            if int(field.get("/Ff", 0)) & (1 | 32768 | 65536):
                raise HTTPException(422, f"{label}: read-only and radio/button fields are unsupported.")
            matches = [w for n, w, _ in widgets if n == name]
            if not matches:
                raise HTTPException(422, f"{label}: PDF field has no visible widget.")
            if field.get("/FT") == "/Btn":
                if answer["kind"] != "checkbox" or type(value) is not bool:
                    raise HTTPException(422, f"{label}: map a true/false answer to this checkbox.")
                states = set()
                for widget in matches:
                    states.update(widget.get("/AP", {}).get("/N", {}).keys())
                states.discard("/Off")
                if len(states) != 1:
                    raise HTTPException(422, f"{label}: checkbox appearance is ambiguous.")
                values[name] = next(iter(states)) if value else "/Off"
            else:
                if answer["kind"] == "checkbox":
                    raise HTTPException(422, f"{label}: select a PDF checkbox or page position.")
                text = answer_text(value, label)
                if field.get("/MaxLen") and len(text) > int(field["/MaxLen"]):
                    raise HTTPException(422, f"{label}: answer exceeds the PDF field length.")
                for widget in matches:
                    rect = widget["/Rect"]
                    if stringWidth(text, "Helvetica", 10) > float(rect[2] - rect[0]) - 4:
                        raise HTTPException(422, f"{label}: answer does not fit. Review its destination.")
                values[name] = (text, "/Helv", 10)
        else:
            position = target.get("position")
            if not position or not 1 <= position["page"] <= len(reader.pages):
                raise HTTPException(422, f"{label}: invalid PDF page position.")
            page = reader.pages[position["page"] - 1]
            if position["x"] + position["width"] > float(page.mediabox.width) or position["y"] + position[
                "height"
            ] > float(page.mediabox.height):
                raise HTTPException(422, f"{label}: destination falls outside the page.")
            text = (
                "X"
                if answer["kind"] == "checkbox" and value is True
                else ""
                if answer["kind"] == "checkbox"
                else answer_text(value, label)
            )
            if stringWidth(text, "Helvetica", 10) > position["width"]:
                raise HTTPException(
                    422, f"{label}: answer does not fit. Widen the destination or use the official form."
                )
            overlays.setdefault(position["page"] - 1, []).append((position, text))
    if values:
        writer.update_page_form_field_values(None, values, auto_regenerate=False)
    for index, page in enumerate(writer.pages):
        output = io.BytesIO()
        drawing = canvas.Canvas(output, pagesize=(float(page.mediabox.width), float(page.mediabox.height)))
        drawing.setFont("Helvetica", 10)
        for position, text in overlays.get(index, []):
            drawing.drawString(position["x"], float(page.mediabox.height) - position["y"] - 10, text)
        drawing.saveState()
        drawing.setFillColorRGB(0.85, 0.85, 0.85)
        drawing.setFillAlpha(0.3)
        drawing.translate(float(page.mediabox.width) / 2, float(page.mediabox.height) / 2)
        drawing.rotate(35)
        drawing.setFont("Helvetica", 38)
        drawing.drawCentredString(0, 0, "DRAFT - UNSIGNED")
        drawing.restoreState()
        drawing.save()
        page.merge_page(PdfReader(io.BytesIO(output.getvalue())).pages[0])
    writer.add_metadata({"/Title": "Unsigned claim review draft", "/Subject": "Not signed or submitted"})
    output = io.BytesIO()
    writer.write(output)
    reopened = PdfReader(io.BytesIO(output.getvalue()))
    actual = reopened.get_fields() or {}
    for name, expected in values.items():
        expected = expected[0] if isinstance(expected, tuple) else expected
        if str(actual.get(name, {}).get("/V")) != str(expected):
            raise HTTPException(422, "PDF field verification failed. No draft was returned.")
    for name, widget, owner in widget_fields(reopened):
        if name in values:
            if str(widget.get("/V", owner.get("/V"))) != str(actual[name].get("/V")) or not widget.get(
                "/AP", {}
            ).get("/N"):
                raise HTTPException(422, "PDF widget verification failed. No draft was returned.")
    return output.getvalue()
