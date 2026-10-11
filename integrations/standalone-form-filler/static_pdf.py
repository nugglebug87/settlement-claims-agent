"""Place reviewed text on flattened or scanned PDF pages without AcroForm widgets."""
import fitz

def render_pages(pdf_bytes, scale=1.3):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if len(doc) > 20:
            raise ValueError("Maximum 20 pages")
        result = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            result.append({"width": page.rect.width, "height": page.rect.height, "png": pix.tobytes("png")})
        return result
    finally:
        doc.close()

def place_text(pdf_bytes, placements):
    """Coordinates are PDF points from the top-left. User confirms each placement."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if len(placements) > 200:
            raise ValueError("Too many placements")
        for item in placements:
            page_index = int(item["page"])
            if page_index < 0 or page_index >= len(doc):
                raise ValueError("Invalid page")
            page = doc[page_index]
            x, y = float(item["x"]), float(item["y"])
            size = float(item.get("size", 10))
            value = str(item["value"])
            if not 6 <= size <= 24 or len(value) > 500:
                raise ValueError("Invalid text size or length")
            if not (0 <= x <= page.rect.width and 0 <= y <= page.rect.height):
                raise ValueError("Text location outside page")
            if "\n" in value or "\r" in value:
                raise ValueError("Use one line per placement")
            # Baseline is offset from the clicked top-left position.
            page.insert_text((x, y + size), value, fontsize=size, fontname="helv", color=(0, 0, 0), overlay=True)
        return doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()
