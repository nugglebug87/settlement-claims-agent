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


def test_comb_fields_report_length_and_reject_overflow():
    from reportlab.pdfgen import canvas
    import pytest
    output = BytesIO()
    c = canvas.Canvas(output)
    c.acroForm.textfield(name="ZIP Code", x=70, y=700, width=200, height=25, maxlen=5, fieldFlags="comb")
    c.showPage()
    c.save()
    data = output.getvalue()
    fields = extract_fields(data)
    assert fields[0]["max_length"] == 5
    assert fields[0]["comb"] is True
    with pytest.raises(ValueError, match="at most 5 characters"):
        fill_pdf(data, {"ZIP Code": "123456"})
    result = fill_pdf(data, {"ZIP Code": "56055"})
    assert PdfReader(BytesIO(result)).get_fields()["ZIP Code"].get("/V") == "56055"


def test_comb_appearance_spaces_characters_into_cells():
    import fitz
    from reportlab.pdfgen import canvas
    output = BytesIO()
    c = canvas.Canvas(output)
    c.acroForm.textfield(name="First Name", x=60, y=650, width=240, height=20, maxlen=12, fieldFlags="comb")
    c.showPage()
    c.save()
    completed = fill_pdf(output.getvalue(), {"First Name": "AMBER"})
    document = fitz.open(stream=completed, filetype="pdf")
    words = document[0].get_text("words")
    letters = [w for w in words if w[4] == "AMBER"]
    assert not letters, "Comb appearance should not render the name as one continuous word"
    assert any(w[4] == "A" for w in words)
    assert any(w[4] == "M" for w in words)
