# Settlement Claims Agent

A deployable single-owner settlement workspace with a rose-led gothic editorial dashboard: burgundy velvet, candlelit roses, antique gold, dark textures, and locally hosted serif/script fonts.

**The MVP prepares claims and supports human submission. It does not automatically file claims.** It never invents purchases, losses, dates, eligibility answers, payout records, or legal declarations. The database starts empty; synthetic fixtures are confined to tests.

## Agents in the app

Open **Agents** in the sidebar. The Claims Search Agent runs a selected configured discovery source immediately and shows profile-based matches. Sources can be paused for daily monitoring and still run manually; source configuration and official review remain required.

The home screen is named Claim Finder. It provides three short instructions, one optional company/product box and a Find claims button. Up to five connected sources are selected by default (enabled sources first); source choices and run details are expandable. Plain-language result cards show deadline, estimated payment and a Review claim button. Form Filler has its own navigation item. The Claim Finder reads up to five selected configured sources in sequence and reports each source outcome. An optional company/product filter searches the collection locally, including newly imported leads. Results include open claims and unclassified leads that do not already contradict recorded eligibility facts; closed, expired, future-window, investigation, breach-only and automatic-payment records remain available in Opportunities. The summary distinguishes verified open claims matching recorded facts from leads needing review. A keyword match never establishes class membership. This searches configured sources, not the entire web.

The Form Filler Agent lets you map exact official form labels to saved profile facts for a verified, eligible settlement. It fills those answers in a claim review packet, validates required values and types, and binds the filled answers to the existing approval fingerprint. Changes to mappings or profile facts invalidate earlier approval. For a true/false benefit field that requires documentation, enable “This benefit requires proof when selected” after reviewing the official form. Selecting that benefit then requires an evidence reference attached to the same profile and settlement; evidence for another claim does not qualify. References still need human review for authenticity and sufficiency. Prepared packets can be downloaded. No database migration is needed because reviewed field mappings are retained in opportunity provenance and filled answers in claim packets.

PDF drafts are available from the Agents field-mapping dialog. Choose a blank official PDF (up to 3 MB / 10 pages), inspect every page, and map each ordinary answer to an interactive field name or a reviewed page position. For paper forms, select the answer and click its blank space on the page, then adjust the box dimensions. Leave signature and certification areas untouched. All mapped fields need a destination. Save the mappings and prepare a packet; its review dialog then offers **Download unsigned PDF draft**. Choose the same original PDF again to generate the draft. Uploads are processed in memory; the database saves only the file SHA-256 digest and reviewed destinations. Generated downloads use session-bound links valid for two minutes, with PDF bytes kept only in bounded server memory. A restart or an expired link requires regeneration. This deployment uses one application process; multiple workers or replicas would need a shared private download store. The output retains every original page and marks it DRAFT - UNSIGNED. Interactive fields remain editable, so edits outside the app are not covered by the packet approval.

Changed source PDFs, stale profile/source revisions, oversized answers, invalid destinations, signed/encrypted PDFs, XFA, rotated/cropped pages, ambiguous fields, and active document actions are rejected. Supported native fields are text and independent checkboxes; radio groups, choice fields and signatures require the official form. Standard PDF fonts must be able to represent the supplied answers. Evidence references are included in the review packet; evidence files are not embedded in the PDF.

The app prepares answers and unsigned PDF drafts. An optional unpacked browser helper fills reviewed ordinary answers on the official website after explicit transmission authorization. Signing, certifications, attachments, and final submission remain human steps; approval and the official-form handoff continue to work.

### PDF extraction API

`POST /api/pdf/inspect` accepts JSON containing `pdf_base64`. It requires a signed-in session, the configured Origin, and an `X-CSRF-Token`. It returns the original SHA-256 fingerprint, supported interactive fields (name, label, kind, required flag, and positions in points from the page's top-left), and page previews with extracted text. Page text is limited to 30,000 characters per page and is for review, not an eligibility attestation. `text_status: no_text_layer` means visual review is needed; OCR is not implemented. Upload bytes and extracted text are not saved by this endpoint.

After reviewing the official fields, save mappings with `PUT /api/opportunities/{id}/form-fields`, prepare with `POST /api/opportunities/{id}/prepare`, and generate an unsigned draft with `POST /api/claims/{id}/pdf` using the same original PDF. Download from the returned session-bound URL within two minutes. Signature and certification fields remain manual. No browser extension is required for this PDF workflow.

### Browser form helper

Claim review dialogs offer a downloadable unpacked Chrome/Edge helper. Load the claim while its workspace review is open, keep that tab signed in, then open the exact official form in another tab and inspect it with the helper. Review each mapping and explicitly authorize transmitting the selected ordinary answers, including any immediate autosave. The extension rechecks the current packet before filling and rejects stale packets, completed submissions, changed fields, and mismatched destinations.

Only visible ordinary text inputs and textareas in the top document are supported. Legal/sensitive fields are conservatively excluded by wording; these heuristics still need personal review. Checkboxes, choices, signatures, uploads, CAPTCHA and submission remain manual. The helper never clicks submit or records a claim as submitted. A prepared packet authorizes drafting only; final signing and submission require the separate claim-specific approval.

The extension requests activeTab, scripting, and storage. It retains only a ten-minute claim reference in session storage; answer values are transient popup memory. There is no permanent website permission or cloud sync. The supported workspace origins are this project's current Railway domain and localhost:8000. See extension/README.md for installation, privacy limits, and testing. No database migration is needed.

Endpoints: authenticated GET /api/browser-extension downloads the installable ZIP; GET /api/claims/{id}/browser-packet returns current ordinary answers and their packet hash without evidence or attestation text. Both responses use Cache-Control: no-store. Browser tests run with npm ci, npx playwright install chromium, and npm test in extension/.

## Local setup

Requires Python 3.13. PostgreSQL is required in production; SQLite is supported only for development.

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
cp .env.example .env
# Windows PowerShell: Copy-Item .env.example .env
```

Set your own `APP_PASSWORD` in `.env`. Generate `SESSION_SECRET` with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Start with the same command used by Railway:

```bash
python -m app.start
```

Open **http://localhost:8000** and sign in. The command validates configuration, applies Alembic migrations, and starts Uvicorn on `0.0.0.0:$PORT` (8000 by default). `/health` checks database connectivity, the migration table, and Redis when configured; dependency failures return 503.

## Architecture and capabilities

Settlement Sources → Discovery AI → Deduplication → Eligibility Engine → Priority Score → Claim Preparation → User Approval → Human Submission → Confirmation Capture → Claim Database → Payment/Status Monitoring → In-app Notifications.

| Stage | Implemented behavior |
| --- | --- |
| Sources/discovery | Public HTTPS JSON feeds and optional AI extraction from official HTML; source provenance and run history |
| Duplicate detection | Canonical URL fingerprint, normalized court/case identifier, unique claimant/opportunity pairs |
| Eligibility | Typed, deterministic criteria with pass/fail/unknown explanations; missing facts remain unknown |
| Priority | FILE NOW, HIGH VALUE, NO PROOF, DATA BREACH, PRIVACY, TCPA, NEEDS ANSWER |
| Preparation | Snapshot of relevant facts, evidence references, deadline, criteria and exact legal-attestation text |
| Approval | Fact confirmation, legal-attestation acceptance, signer name, timestamp and SHA-256 packet binding |
| Submission | Explicit handoff to the official form; CAPTCHA, identity checks, evidence and declarations remain human steps |
| Confirmation | Actual reference, actual submission time and user-provided receipt/evidence text |
| Tracking | Status transitions, expected payment dates and actual received payment amounts kept separate |
| Monitoring | Daily source refresh, 14/3/1-day deadline alerts, expected-payment follow-ups and stale-status reminders |
| Notifications | Persistent, deduplicated in-app alerts and read/unread state |
| Quality | HTTPS/host/credential checks, fee-request indicators, internationalized-domain flag and mandatory source review |
| Security | Private-workspace login, signed cookies, origin/CSRF checks, login rate limiting, validation and audit history |

### Important MVP boundaries

- “Eligible” means recorded facts match recorded criteria. The administrator makes the final determination; this is not a guarantee or legal advice.
- Rules are ANDed. Complex alternatives, exclusions, household limits and previous filings must be resolved manually before source verification. Explicit answers can be recorded as facts, but must never be inferred.
- AI returns **unverified candidates**. Human review must check all criteria, exceptions, deadlines, declarations and omissions against the official source. AI cannot approve sources/claims or write personal eligibility answers.
- Evidence is stored as references and descriptions, not uploaded identity documents or receipt binaries. Keep originals secure and provide them directly to the official administrator. Proof-required claims need a reference before preparation.
- Status/payment monitoring creates reminders to check official records. The MVP does not log into administrator portals, access bank accounts, or automatically mark claims accepted/paid. Changes require user-provided evidence.
- Notifications are **in-app**. Email/SMS delivery and administrator-specific automated submission/status adapters are not implemented.
- Different URLs without a shared court/case identifier may still represent the same settlement. Review duplicate risk, including claims filed outside this application.
- This is a **single-owner private workspace**, not multi-tenant SaaS. One password protects one profile; do not share it among unrelated claimants. Audit actors are `owner` or `system`, not independently verified identities.

## Deploy on Railway

The repository includes a non-root `Dockerfile`, `railway.json`, and a production start command. Connect the desired GitHub branch as an application service in your existing Railway project.

**Reuse the existing PostgreSQL and Redis services.** Add reference variables to the application service using the actual service names in your project:

```dotenv
APP_ENV=production
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
APP_PASSWORD=<unique private password, at least 16 characters>
SESSION_SECRET=<random secret, at least 32 characters>
APP_URL=https://<your-application-domain>
WORKER_ENABLED=true
MONITOR_INTERVAL_SECONDS=900
```

`Postgres` and `Redis` are example service names, not resources this application creates. Select the existing services using Railway's reference-variable selector. Keep them on Railway's private network and never commit credentials.

1. Connect the repository/branch and use this directory as the service root.
2. Set the environment variables above. If Redis is unavailable, omit `REDIS_URL`; the single-process scheduler and login limiter run locally. A configured but unavailable Redis causes health/authentication to fail closed.
3. Generate or attach an HTTPS domain and set `APP_URL` to that **exact origin**, without a path. A mismatched origin blocks login or writes.
4. Deploy. `railway.json` specifies `python -m app.start`, `/health`, a 120-second health timeout and one replica. Railway supplies `PORT`.
5. Check `/health`, sign in, record real profile facts and configure source hosts below.

Production startup rejects short/missing secrets, non-PostgreSQL storage and a non-HTTPS origin. Cookies are Secure, HttpOnly and SameSite in production. Use **one replica and one worker** for this MVP; startup migrations must not race between replicas.

References: [Railway config as code](https://docs.railway.com/config-as-code/reference), [Railway health checks](https://docs.railway.com/deployments/healthchecks), [FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/).

### Discovery configuration

```dotenv
SOURCE_ALLOWED_HOSTS=official-administrator.example,feed-you-control.example
OPENAI_API_KEY=<optional server-only key>
OPENAI_MODEL=gpt-4.1-mini
```

Replace example hostnames with independently reviewed sources. Blank host configuration blocks remote discovery. Fetches require exact allowlisted hostnames, HTTPS/443, public DNS addresses, a pinned validated destination IP and certificate validation. Redirects are not followed. Requests have a 20-second timeout and 1 MB response limit.

JSON sources need no AI key. HTML sources use the OpenAI Responses API with `store: false`, passing stripped source text (up to 30,000 characters) and an extraction schema. No personal profile or claim packet is sent. Excerpts must appear verbatim in source text. Enabling HTML discovery can incur provider charges.

JSON feeds use an `opportunities` array, with at most 30 records per run:

```json
{"opportunities": []}
```

Each record follows `OpportunityInput` in `app/schemas.py`. Required: `title`, `official_url`. Optional: `case_number` (include court/jurisdiction), `administrator`, `category`, `summary`, `deadline` (ISO timestamp **with timezone offset**), `expected_payout`, `proof_required`, `rules`, `attestation_text`, and exact `source_excerpt`. Leave unknowns null or omitted.

Rule syntax example only — **not real settlement terms or claimant facts**:

```json
[
  {"field":"example_purchase","op":"eq","value":true,"question":"Does the official purchase criterion apply?"},
  {"field":"example_state","op":"in","value":["CA","NY"],"question":"What was your state during the relevant period?"},
  {"field":"example_purchase_date","op":"date_on_or_after","value":"2024-01-01","question":"What is the documented purchase date?"}
]
```

Operators: `eq`, `in`, `gte`, `lte`, `date_on_or_after`, `date_on_or_before`. Dates use `YYYY-MM-DD`. The application never supplies default dates. `false`, `0`, `null` and omitted answers have distinct meanings. The UI edits typed facts and criteria without changing application code.

Each run records status, imports, duplicates and sanitized failures. Enable daily discovery or run a source manually. The worker checks every `MONITOR_INTERVAL_SECONDS`, processing at most three due sources per tick. Redis supplies a worker lease when configured; PostgreSQL remains the system of record.

## How to use the workspace

1. Import an official opportunity or connect a reviewed source.
2. Review the original notice. Correct missing/incorrect data and record the exact official attestation. Verify administrator identity, form ownership, criteria and deadline, recording the supporting reference.
3. Record your actual eligibility facts. Missing answers appear in `NEEDS ANSWER`. Record a reference to real proof where required.
4. Prepare a packet. Unreviewed sources, unknown/expired deadlines, nonmatching criteria, missing proof or missing declarations block preparation.
5. Review the exact facts and declaration. Personally confirm both and enter the signer name. Approval binds to the packet hash and source/profile revisions.
6. Continue to human submission. Complete the official form, evidence upload, CAPTCHA, identity checks and declarations yourself. Opening the form never counts as submission.
7. Record the actual confirmation reference, time and receipt text. Only then is the claim marked `submitted`.
8. Record evidenced administrator updates. `paid` requires the actual received amount and receipt description; expected payout is never treated as money received.

Profile/source changes invalidate prepared approvals: prepare and approve again. Handed-off/submitted claims cannot be prepared again, preventing duplicate filing. If you abandoned a form, reopen its existing link and continue; do not import another opportunity to bypass the duplicate protection. There is intentionally no unsafe reset-submitted-claim shortcut.

## Priority rules

- `FILE NOW`: criteria match, source reviewed and deadline within 14 days. Proof requirements still apply to preparation.
- `HIGH VALUE`: sourced expected payout ≥ $100, not a guaranteed return.
- `NO PROOF`: source explicitly says no proof; unknown is not no proof.
- `DATA BREACH`, `PRIVACY`, `TCPA`: opportunity classification.
- `NEEDS ANSWER`: missing/invalid criteria or required facts.

Score = 40 for an actionable opportunity + up to 30 for urgency + up to 20 for stated payout + 10 for explicitly no proof. Queues overlap and are sorting aids, not submission permissions.

## Database and migrations

| Table | Purpose |
| --- | --- |
| `profiles` | Owner facts and revision |
| `sources`, `source_runs` | Configured sources, refresh history and outcomes |
| `opportunities` | Terms, provenance, canonical identity, source review and quality state |
| `evidence` | Personally verified document references |
| `claims` | Unique profile/opportunity, packet hash, approval, confirmation, status/payment |
| `audit_log` | Event history with no edit/delete API |
| `notifications` | Alerts with unique deduplication keys |

```bash
python -m alembic upgrade head
python -m alembic check
# With DATABASE_URL set to PostgreSQL, inspect PostgreSQL DDL without connecting:
python -m alembic upgrade head --sql
```

Foreign keys and unique constraints enforce identity and duplicate prevention. Money uses `NUMERIC(12,2)`. API timestamps use UTC and display in the browser's timezone. Unknown values stay null. Back up PostgreSQL before upgrades. Downgrades exist for disposable development databases and can drop data; production rollback should restore a tested backup and its matching application version.

## Security and operations

- Environment-only secrets; no keys/passwords shipped to the frontend. Rotate `SESSION_SECRET` and restart to invalidate sessions. Sessions expire after 12 hours.
- Exact-origin checks and session-bound CSRF tokens protect mutations. Login is rate-limited. Forwarded client headers are ignored rather than trusted blindly; behind Railway, the one-owner workspace may share a proxy-wide login limit.
- Bounded request bodies, strict input validation, escaped text, self-only CSP and no third-party scripts/fonts. Health is public and minimal; workspace APIs require sign-in.
- Audit history is append-only through the app, but a database administrator can alter it. It is not a tamper-proof compliance ledger.
- Fraud checks are indicators, not certification. Independently review administrator identity and complete legal criteria. Never pay an upfront fee to receive a settlement.
- Limit stored personal data. Receipts/approvals are sensitive: restrict DB access, use secure connections and encrypted managed storage/backups, and choose a retention policy. Keep identity and payment-card documents out of this app.
- Source failures appear in history and notifications. Worker errors are logged without sensitive provider bodies and retried on the next tick.

### Docker development

Compose is for fresh **local development** only; reuse existing Railway services in production. Set `POSTGRES_PASSWORD`, `APP_PASSWORD` and `SESSION_SECRET` in `.env`, then:

```bash
docker compose up --build
```

The local PostgreSQL volume persists data. PostgreSQL/Redis ports are not publicly exposed.

## Verification

```bash
python -m pytest -q
python -m ruff check app tests
python -m ruff format --check app tests migrations
node --check app/static/app.js
python -m alembic check
```

Node is only an optional JavaScript syntax checker, not a build/runtime dependency. The frontend is plain HTML/CSS/JavaScript.

Tests cover eligibility, dates/types, duplicates, proof, exact-packet approvals, stale revisions, human handoff, confirmation, payment evidence, auth/CSRF, timezone preservation, source failures and idempotent reminders. They never submit external claims. GitHub Actions also starts PostgreSQL/Redis, checks migration drift, and smoke-tests production startup and `/health`.

## Project structure

```text
app/
  auth.py          Signed sessions, CSRF, login limits
  config.py        Environment and production validation
  db.py            PostgreSQL/SQLite sessions
  discovery.py     Safe fetch, JSON imports, optional AI extraction
  engine.py        Eligibility, priority, deduplication, quality
  main.py          Authenticated API and dashboard
  models.py        Database schema
  monitor.py       Source/deadline/status/payment reminders
  schemas.py       Validated API contracts
  services.py      Claim lifecycle, approval and audit
  start.py         Validate → migrate → serve
  static/          Responsive rose dashboard, artwork, fonts
migrations/        Versioned schema upgrades/downgrades
tests/             Unit and end-to-end API tests
.github/workflows/ PostgreSQL/Redis CI
Dockerfile
compose.yaml
railway.json
```

Design asset provenance and font licenses: [docs/design.md](docs/design.md).
# Discovery streams and retained breach announcements

The opportunity collection retains three independently scheduled streams: settlements,
government refunds, and breach announcements. Breach notices stay in the database even
when no compensation program exists. Filter **Discovery stream → breach announcements**
to review them. A breach announcement does not establish that the user was affected.

Records distinguish unknown leads, breach announcements, investigations, proposed
settlements, open claims, automatic payments, expired cases, and closed cases. Only a
verified open claim can be prepared. Verification requires an official notice URL and
explicit confirmation of the open claim window, in addition to the existing safeguards.
Older records migrate to unknown and need classification before further filing actions.

In Sources, **Add supplied source catalog** imports the 28 distinct supplied locations,
including six breach sources, without duplicates. They start paused. Configure exact
hostnames in `SOURCE_ALLOWED_HOSTS`, then enable the reviewed sources individually.
Catalog inclusion is not verification of a website or administrator. Some supplied
homepages redirect or need a more specific listing URL; failed fetches are visible in
discovery history. Add a corrected source URL when necessary. Redirects are not followed.
No Have I Been Pwned email, password, identity lookup, or private account access is performed.

`html_links` discovery retains up to 30 relevant public links per fetched page without
an AI key. It does not crawl linked pages or invent terms. `html_ai` optionally extracts
structured candidate terms with source excerpts; human source review remains mandatory.
Record the official notice, defendant, eligibility dates, documentation requirements,
and stated payment timeline when supported by evidence. The recorded claim URL can be
corrected before human handoff; prepared approvals then require renewal.

Exact URL and case-number matches deduplicate. Defendant/administrator matches flag
potential duplicates for a documented review rather than merging unrelated cases.
Repeat discovery stores observations. Changed terms revoke source verification and
require review and corrected details before filing. Breach announcements can be updated
to open claims only when official evidence supports that change; historical observations
remain available. At the default 15-minute worker interval, one due source in each stream
runs per tick, with each source eligible again after 24 hours. This is a bounded listing
monitor, not exhaustive web search or a guarantee that every new case will be found.

## Install on your phone

Open the live HTTPS app and choose **Install app**. On Android, use Chrome’s installation prompt or menu. On iPhone or iPad, open Safari, choose Share → Add to Home Screen → Add. The home-screen icon launches the same signed-in workspace in its own window. Desktop Chrome and Edge also support installation.

The manifest includes 192px and 512px icons made from the supplied Claim Huntr thumbnail, plus an Apple touch icon. A root-scoped service worker handles an offline navigation message without caching pages, sessions, APIs, PDFs, or claim data. An internet connection is required; installation adds no background monitoring or submission capability. Browser installation UI and availability vary by device.
