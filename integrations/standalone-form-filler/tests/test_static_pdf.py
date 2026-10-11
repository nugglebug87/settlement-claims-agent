from io import BytesIO
import fitz
import pytest
from static_pdf import render_pages, place_text

def blank_pdf():
    doc = fitz.open()
    doc.new_page(width=400, height=500)
    data = doc.tobytes()
    doc.close()
    return data

def test_render_flattened_page():
    pages = render_pages(blank_pdf())
    assert len(pages) == 1
    assert pages[0]["width"] == 400
    assert pages[0]["png"].startswith(b"\\x89PNG".decode("unicode_escape").encode("latin1"))

def test_place_text_in_nonfillable_pdf():
    result = place_text(blank_pdf(), [{"page": 0, "x": 50, "y": 100, "size": 12, "value": "Sample Name"}])
    doc = fitz.open(stream=result, filetype="pdf")
    assert "Sample Name" in doc[0].get_text()
    doc.close()

def test_reject_out_of_bounds():
    with pytest.raises(ValueError):
        place_text(blank_pdf(), [{"page": 0, "x": 999, "y": 10, "value": "No"}])
