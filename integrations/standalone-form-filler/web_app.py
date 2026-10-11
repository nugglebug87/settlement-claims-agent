"""Private PDF form filler. Uploaded documents remain in process memory only."""
import os
import secrets
from io import BytesIO
from html import escape
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from form_filler import extract_fields, fill_pdf, suggest_mappings

app = FastAPI(title="Unfiltered Ink Form Filler", docs_url=None, redoc_url=None, openapi_url=None)
security = HTTPBasic()
MAX_PDF = 10 * 1024 * 1024

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    expected = os.environ.get("FORM_FILLER_PASSWORD", "")
    if len(expected) < 16 or not secrets.compare_digest(credentials.password.encode(), expected.encode()):
        raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Basic"})
    return True

def page(body):
    return HTMLResponse("""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Unfiltered Ink — Form Filler</title><style>
:root{color-scheme:dark}body{font:16px system-ui;background:#110c11;color:#f8eaf0;max-width:850px;margin:45px auto;padding:20px}h1{font-family:Georgia,serif;color:#ff4b9e;font-size:2.5rem}main{background:#261420;border:1px solid #82405d;border-radius:18px;padding:26px}label{display:block;margin:14px 0 5px;font-weight:600}input{box-sizing:border-box;width:100%;padding:12px;border:1px solid #a26781;border-radius:8px;background:#170f17;color:white}button{background:#d22e75;color:white;border:0;padding:13px 24px;border-radius:9px;margin-top:20px;font-weight:bold;cursor:pointer}.note{color:#e5b9cb}small{color:#d4a9bd}</style></head><body><h1>Unfiltered Ink · Form Filler</h1><main>""" + body + "</main><p class='note'>Private workspace · Fillable PDFs only · Review all answers before using.</p></body></html>")

@app.get("/health")
def health():
    return {"status": "ok" if len(os.environ.get("FORM_FILLER_PASSWORD", "")) >= 16 else "unconfigured"}

@app.get("/", response_class=HTMLResponse)
def home(_: bool = Depends(authenticate)):
    return page('<h2>Upload your form</h2><p>Select a fillable PDF to identify its fields. Nothing is saved to a database.</p><form action="/inspect" method="post" enctype="multipart/form-data"><label for="pdf">PDF form</label><input id="pdf" type="file" name="pdf" accept=".pdf,application/pdf" required><button>Find form fields</button></form>')

async def read_pdf(upload):
    data = await upload.read(MAX_PDF + 1)
    if len(data) > MAX_PDF: raise HTTPException(413, "PDF exceeds 10 MB")
    if not data.startswith(b"%PDF-"): raise HTTPException(400, "Upload a valid PDF")
    return data

@app.post("/inspect", response_class=HTMLResponse)
async def inspect(pdf: UploadFile = File(...), _: bool = Depends(authenticate)):
    data = await read_pdf(pdf)
    try: fields = extract_fields(data)
    except Exception: raise HTTPException(400, "Unable to read this PDF")
    if not fields: return page("<h2>No interactive fields found</h2><p>This PDF may be scanned or flattened. OCR support is not yet available.</p><a href='/'>Try another PDF</a>")
    # Stateless workflow: form is re-uploaded for filling. No server-side storage.
    rows = "".join(f'<label for="field{i}">{escape(f["name"])}</label><input id="field{i}" name="field_{i}" placeholder="Enter reviewed answer">' for i,f in enumerate(fields))
    return page('<h2>Review fields</h2><p>Enter the values you want in your completed PDF. For privacy, the document must be selected again before filling.</p><form action="/fill" method="post" enctype="multipart/form-data"><label for="pdf">Re-select same PDF</label><input id="pdf" type="file" name="pdf" accept=".pdf,application/pdf" required>' + rows + '<button>Download completed PDF</button></form>')

@app.post("/fill")
async def fill(request: Request, pdf: UploadFile = File(...), _: bool = Depends(authenticate)):
    data = await read_pdf(pdf)
    try:
        fields = extract_fields(data)
        posted = await request.form()
        values = {field["name"]: str(posted[f"field_{i}"]) for i, field in enumerate(fields) if str(posted.get(f"field_{i}", "")).strip()}
        result = fill_pdf(data, values)
    except Exception:
        raise HTTPException(400, "Could not fill this PDF. Check the form and try again.")
    return StreamingResponse(BytesIO(result), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="completed-form.pdf"', "Cache-Control": "no-store"})
