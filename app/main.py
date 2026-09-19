import hmac
from datetime import datetime
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app import services
from app.auth import authenticate, create_session, rate_limit_login, signature
from app.config import settings
from app.db import get_db
from app.discovery import run_source, validate_source_url
from app.engine import aware, case_key, evaluate, fingerprint, priority, quality_flags
from app.models import Audit, Claim, Evidence, Notification, Opportunity, Profile, Source, SourceRun
from app.monitor import monitor, redis_client, start_worker
from app.schemas import (
    ApprovalInput,
    ConfirmationInput,
    EvidenceInput,
    LoginInput,
    OpportunityInput,
    ProfileInput,
    SourceInput,
    StatusInput,
    VerifyInput,
)

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app):
    settings.validate_production()
    stop = start_worker() if settings.worker_enabled else None
    yield
    if stop:
        stop.set()


app = FastAPI(
    title="Settlement Claims Agent",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def security_headers(request, call_next):
    if request.method in {"POST", "PUT", "PATCH"}:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 150000:
                return JSONResponse({"detail": "Request exceeds 150 KB limit."}, status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(
        {"detail": "This record already exists or changed concurrently. Refresh and retry."}, status_code=409
    )


def record(row):
    values = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    return jsonable_encoder(
        {key: aware(value) if isinstance(value, datetime) else value for key, value in values.items()}
    )


def get_record(db, model, id, lock=False):
    query = select(model).where(model.id == id)
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise HTTPException(404, "Record not found.")
    return row


def profile(db, lock=False):
    query = select(Profile).where(Profile.id == "owner")
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        row = Profile(id="owner", name="My profile", facts={})
        db.add(row)
        db.flush()
    return row


def claim_context(db, id):
    person = profile(db, True)
    claim = get_record(db, Claim, id, True)
    opportunity = get_record(db, Opportunity, claim.opportunity_id, True)
    return claim, person, opportunity


@app.get("/health")
def health(db=Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        # Confirm migration exists, not only that the database accepts connections.
        db.execute(text("SELECT version_num FROM alembic_version"))
        client = redis_client()
        if client:
            client.ping()
        return {"status": "ok", "database": "ok", "redis": "ok" if client else "not_configured"}
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)


@app.post("/api/login")
def login(data: LoginInput, request: Request, response: Response):
    if request.headers.get("origin") != settings.app_url.rstrip("/"):
        raise HTTPException(403, "Invalid request origin.")
    rate_limit_login(request)
    if not settings.app_password or not hmac.compare_digest(
        data.password.encode(), settings.app_password.encode()
    ):
        raise HTTPException(401, "Invalid password or APP_PASSWORD is not configured.")
    token, csrf = create_session()
    response.set_cookie(
        "claims_session",
        token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="strict",
        max_age=43200,
    )
    return {"csrf_token": csrf}


@app.get("/api/session", dependencies=[Depends(authenticate)])
def session(request: Request):
    return {"csrf_token": signature("csrf:" + request.cookies["claims_session"])}


@app.post("/api/logout", dependencies=[Depends(authenticate)])
def logout(response: Response):
    response.delete_cookie("claims_session")
    return {"ok": True}


@app.get("/api/profile", dependencies=[Depends(authenticate)])
def read_profile(db=Depends(get_db)):
    row = profile(db)
    db.commit()
    return record(row)


@app.put("/api/profile", dependencies=[Depends(authenticate)])
def save_profile(data: ProfileInput, db=Depends(get_db)):
    row = profile(db, True)
    row.name, row.facts, row.revision = data.name, data.facts, row.revision + 1
    services.audit(db, "profile.updated", row.id, {"revision": row.revision, "fields": sorted(data.facts)})
    db.commit()
    return record(row)


def enriched(opportunity, person):
    eligibility = evaluate(opportunity.rules, person.facts)
    return {
        **record(opportunity),
        "eligibility": eligibility,
        "priority": priority(
            eligibility["status"],
            opportunity.deadline,
            opportunity.expected_payout,
            opportunity.category,
            opportunity.proof_required,
            opportunity.verified,
        ),
    }


@app.get("/api/dashboard", dependencies=[Depends(authenticate)])
def dashboard(db=Depends(get_db)):
    person = profile(db)
    opportunities = [
        enriched(o, person) for o in db.scalars(select(Opportunity).order_by(Opportunity.created_at.desc()))
    ]
    claims = [record(c) for c in db.scalars(select(Claim).order_by(Claim.updated_at.desc()))]
    db.commit()
    return {
        "opportunities": sorted(opportunities, key=lambda o: o["priority"]["score"], reverse=True),
        "claims": claims,
        "notifications": [
            record(n)
            for n in db.scalars(select(Notification).order_by(Notification.created_at.desc()).limit(100))
        ],
        "configuration": {
            "database": "postgresql" if "postgres" in settings.database_url else "sqlite (development)",
            "redis": bool(settings.redis_url),
            "ai_discovery": bool(settings.openai_api_key),
            "worker_enabled": settings.worker_enabled,
        },
    }


@app.post("/api/opportunities", dependencies=[Depends(authenticate)])
def add_opportunity(data: OpportunityInput, db=Depends(get_db)):
    opportunity, duplicate = services.ingest(db, data)
    db.commit()
    return {"opportunity": record(opportunity), "duplicate": duplicate}


@app.put("/api/opportunities/{id}", dependencies=[Depends(authenticate)])
def edit_opportunity(id: str, data: OpportunityInput, db=Depends(get_db)):
    row = get_record(db, Opportunity, id, True)
    # A URL identifies the case; changing it can create a duplicate submission path.
    if fingerprint(data.official_url) != row.fingerprint:
        raise HTTPException(
            409, "Canonical claim URL cannot change. Import a different opportunity separately."
        )
    for key, value in data.model_dump(exclude={"source_excerpt"}).items():
        setattr(row, key, value)
    row.case_key = case_key(data.case_number)
    row.provenance = {**row.provenance, "excerpt": data.source_excerpt}
    row.quality_flags = quality_flags(data.official_url, data.source_excerpt + " " + data.summary)
    row.verified, row.verification_notes, row.revision = False, None, row.revision + 1
    services.audit(db, "opportunity.updated", id, {"revision": row.revision})
    db.commit()
    return record(row)


@app.post("/api/opportunities/{id}/verify", dependencies=[Depends(authenticate)])
def verify_opportunity(id: str, data: VerifyInput, db=Depends(get_db)):
    row = get_record(db, Opportunity, id, True)
    services.verify(db, row, data)
    db.commit()
    return record(row)


@app.post("/api/opportunities/{id}/prepare", dependencies=[Depends(authenticate)])
def prepare_claim(id: str, db=Depends(get_db)):
    person = profile(db, True)
    opportunity = get_record(db, Opportunity, id, True)
    claim = services.prepare(db, person, opportunity)
    db.commit()
    return record(claim)


@app.post("/api/opportunities/{id}/evidence", dependencies=[Depends(authenticate)])
def record_evidence(id: str, data: EvidenceInput, db=Depends(get_db)):
    person = profile(db, True)
    get_record(db, Opportunity, id, True)
    row = Evidence(
        profile_id=person.id, opportunity_id=id, reference=data.reference, description=data.description
    )
    db.add(row)
    person.revision += 1
    db.flush()
    services.audit(db, "evidence.recorded", row.id, {"opportunity_id": id, "personally_verified": True})
    db.commit()
    return record(row)


@app.post("/api/claims/{id}/approve", dependencies=[Depends(authenticate)])
def approve_claim(id: str, data: ApprovalInput, db=Depends(get_db)):
    claim, person, opportunity = claim_context(db, id)
    services.approve(db, claim, person, opportunity, data)
    db.commit()
    return record(claim)


@app.post("/api/claims/{id}/handoff", dependencies=[Depends(authenticate)])
def handoff_claim(id: str, db=Depends(get_db)):
    claim, person, opportunity = claim_context(db, id)
    result = services.handoff(db, claim, person, opportunity)
    db.commit()
    return result


@app.post("/api/claims/{id}/confirmation", dependencies=[Depends(authenticate)])
def confirm_claim(id: str, data: ConfirmationInput, db=Depends(get_db)):
    claim = get_record(db, Claim, id, True)
    services.confirm(db, claim, data)
    db.commit()
    return record(claim)


@app.post("/api/claims/{id}/status", dependencies=[Depends(authenticate)])
def status_claim(id: str, data: StatusInput, db=Depends(get_db)):
    claim = get_record(db, Claim, id, True)
    services.update_status(db, claim, data)
    db.commit()
    return record(claim)


@app.get("/api/claims/{id}/packet", dependencies=[Depends(authenticate)])
def export_packet(id: str, db=Depends(get_db)):
    claim = get_record(db, Claim, id)
    return JSONResponse(
        claim.packet, headers={"Content-Disposition": f'attachment; filename="claim-{claim.id}.json"'}
    )


@app.get("/api/sources", dependencies=[Depends(authenticate)])
def sources(db=Depends(get_db)):
    return {
        "sources": [record(s) for s in db.scalars(select(Source).order_by(Source.created_at.desc()))],
        "runs": [
            record(r) for r in db.scalars(select(SourceRun).order_by(SourceRun.created_at.desc()).limit(50))
        ],
    }


@app.post("/api/sources", dependencies=[Depends(authenticate)])
def add_source(data: SourceInput, db=Depends(get_db)):
    try:
        validate_source_url(data.url)
    except (ValueError, OSError):
        raise HTTPException(
            422, "Source must be a public HTTPS URL on the configured SOURCE_ALLOWED_HOSTS allowlist."
        )
    row = Source(**data.model_dump())
    db.add(row)
    db.flush()
    services.audit(db, "source.created", row.id)
    db.commit()
    return record(row)


@app.post("/api/sources/{id}/toggle", dependencies=[Depends(authenticate)])
def toggle_source(id: str, db=Depends(get_db)):
    row = get_record(db, Source, id, True)
    row.enabled = not row.enabled
    services.audit(db, "source.toggled", id, {"enabled": row.enabled})
    db.commit()
    return record(row)


@app.post("/api/sources/{id}/run", dependencies=[Depends(authenticate)])
def discover_source(id: str, db=Depends(get_db)):
    row = get_record(db, Source, id, True)
    run = run_source(db, row)
    db.commit()
    return record(run)


@app.post("/api/monitor", dependencies=[Depends(authenticate)])
def run_monitor(db=Depends(get_db)):
    profile(db, True)
    monitor(db)
    services.audit(db, "monitor.requested", "owner")
    db.commit()
    return {"ok": True}


@app.post("/api/notifications/{id}/read", dependencies=[Depends(authenticate)])
def mark_read(id: str, db=Depends(get_db)):
    get_record(db, Notification, id, True).read = True
    db.commit()
    return {"ok": True}


@app.get("/api/audit", dependencies=[Depends(authenticate)])
def read_audit(offset: int = 0, db=Depends(get_db)):
    if offset < 0:
        raise HTTPException(422, "Offset must be nonnegative.")
    return [
        record(a)
        for a in db.scalars(select(Audit).order_by(Audit.created_at.desc()).offset(offset).limit(100))
    ]


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
