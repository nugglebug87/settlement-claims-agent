from io import BytesIO
from pypdf import PdfReader
from form_filler import extract_fields, fill_pdf, suggest_mappings

def sample_pdf():
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=letter)
    c.acroForm.textfield(name="Full Name", x=70, y=700, width=200, height=25)
    c.acroForm.textfield(name="Email Address", x=70, y=650, width=200, height=25)
    c.showPage()
    c.save()
    return output.getvalue()

def test_extract_fields():
    assert [x["name"] for x in extract_fields(sample_pdf())] == ["Full Name", "Email Address"]

def test_mapping_only_known_facts():
    result = suggest_mappings(["Full Name", "Email Address", "Social Security Number"], {"full_name": "Example Person", "email": "example@example.com"})
    assert result == {"Full Name": "Example Person", "Email Address": "example@example.com"}

def test_fill_pdf():
    result = fill_pdf(sample_pdf(), {"Full Name": "Example Person", "Email Address": "example@example.com"})
    fields = PdfReader(BytesIO(result)).get_fields()
    assert fields["Full Name"].get("/V") == "Example Person"
    assert fields["Email Address"].get("/V") == "example@example.com"

def test_reject_unknown_field():
    import pytest
    with pytest.raises(ValueError):
        fill_pdf(sample_pdf(), {"Not a Field": "anything"})
