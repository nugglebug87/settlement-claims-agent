"""Private PDF form filler. Uploaded documents remain in process memory only."""
import os
import secrets
from io import BytesIO
import base64
import json
from static_pdf import render_pages, place_text
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
:root{color-scheme:dark}body{font:16px system-ui;background:#110c11;color:#f8eaf0;max-width:850px;margin:45px auto;padding:20px}h1{font-family:Georgia,serif;color:#ff4b9e;font-size:2.5rem}main{background:#261420;border:1px solid #82405d;border-radius:18px;padding:26px}label{display:block;margin:14px 0 5px;font-weight:600}input{box-sizing:border-box;width:100%;padding:12px;border:1px solid #a26781;border-radius:8px;background:#170f17;color:white}button{background:#d22e75;color:white;border:0;padding:13px 24px;border-radius:9px;margin-top:20px;font-weight:bold;cursor:pointer}.note{color:#e5b9cb}small{color:#d4a9bd}</style></head><body><h1>Unfiltered Ink · Form Filler</h1><main>""" + body + "</main><p class='note'>Private workspace · Fillable and flattened PDFs · Review all answers before using.</p></body></html>")

@app.get("/health")
def health():
    return {"status": "ok" if len(os.environ.get("FORM_FILLER_PASSWORD", "")) >= 16 else "unconfigured"}

@app.get("/", response_class=HTMLResponse)
def home(_: bool = Depends(authenticate)):
    return page('<h2>Upload your form</h2><p>Select a fillable PDF to identify its fields. Nothing is saved to a database. Nonfillable forms can be completed by clicking where text belongs.</p><form action="/inspect" method="post" enctype="multipart/form-data"><label for="pdf">PDF form</label><input id="pdf" type="file" name="pdf" accept=".pdf,application/pdf" required><button>Find form fields</button></form>')

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
    if not fields: return manual_editor(data)
    # Stateless workflow: form is re-uploaded for filling. No server-side storage.
    rows = "".join(f'<label for="field{i}">{escape(f["name"])}</label><input id="field{i}" name="field_{i}" maxlength="{f.get(\"max_length\") or 10000}" placeholder="Enter reviewed answer">' for i,f in enumerate(fields))
    return page('<h2>Review fields</h2><p>Enter the values you want in your completed PDF. For privacy, the document must be selected again before filling.</p><form action="/fill" method="post" enctype="multipart/form-data"><label for="pdf">Re-select same PDF</label><input id="pdf" type="file" name="pdf" accept=".pdf,application/pdf" required>' + rows + '<button>Download completed PDF</button></form>')

@app.post("/fill")
async def fill(request: Request, pdf: UploadFile = File(...), _: bool = Depends(authenticate)):
    data = await read_pdf(pdf)
    try:
        fields = extract_fields(data)
        posted = await request.form()
        values = {field["name"]: str(posted[f"field_{i}"]) for i, field in enumerate(fields) if str(posted.get(f"field_{i}", "")).strip()}
        result = fill_pdf(data, values)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        raise HTTPException(400, "Could not fill this PDF. Check the form and try again.")
    return StreamingResponse(BytesIO(result), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="completed-form.pdf"', "Cache-Control": "no-store"})

def manual_editor(data):
    pages = render_pages(data)
    cards = []
    for i, p in enumerate(pages):
        src = base64.b64encode(p["png"]).decode("ascii")
        cards.append(f'<section><h3>Page {i+1}</h3><img class="pdfpage" data-page="{i}" data-width="{p["width"]}" data-height="{p["height"]}" src="data:image/png;base64,{src}" alt="PDF page {i+1}"></section>')
    body = """<h2>Place text on nonfillable form</h2>
<p>Click the page where an answer should begin, then enter its text. Add each line separately. The app will add the text without modifying the original form design.</p>
<label>Text to place</label><input id="answer" placeholder="Type answer, then click page">
<label>Font size (points)</label><input id="size" type="number" min="6" max="24" value="10">
<div id="placed" aria-live="polite"></div>
<form id="submit" action="/manual-fill" method="post" enctype="multipart/form-data">
<label>Re-select the same PDF</label><input type="file" name="pdf" accept=".pdf,application/pdf" required>
<input type="hidden" name="placements" id="placements"><button type="submit">Download completed PDF</button></form>
""" + "".join(cards) + """
<script>
const entries=[], holder=document.getElementById('placed');
document.querySelectorAll('.pdfpage').forEach(img=>img.addEventListener('click',event=>{
 const value=document.getElementById('answer').value.trim();
 if(!value){alert('Type an answer first');return}
 const rect=img.getBoundingClientRect();
 const x=(event.clientX-rect.left)*Number(img.dataset.width)/rect.width;
 const y=(event.clientY-rect.top)*Number(img.dataset.height)/rect.height;
 entries.push({page:Number(img.dataset.page),x,y,value,size:Number(document.getElementById('size').value)});
 holder.textContent=entries.length+' placement(s) added. Last: '+value;
 document.getElementById('answer').value='';
}));
document.getElementById('submit').addEventListener('submit',event=>{
 if(!entries.length){event.preventDefault();alert('Place at least one answer');return}
 document.getElementById('placements').value=JSON.stringify(entries);
});
</script>"""
    return page(body)

@app.post("/manual-fill")
async def manual_fill(request: Request, pdf: UploadFile = File(...), _: bool = Depends(authenticate)):
    data = await read_pdf(pdf)
    try:
        form = await request.form()
        placements = json.loads(str(form.get("placements", "[]")))
        if not isinstance(placements, list):
            raise ValueError("Invalid placements")
        result = place_text(data, placements)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "Invalid placement data")
    return StreamingResponse(BytesIO(result), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="completed-form.pdf"', "Cache-Control": "no-store"})
