# Standalone Form Filler — integration contract

This directory specifies a **separate** form-filling service that can connect to Claims Agent and other apps. It must not share Claims Agent's session secret, database, or personal profile by default.

## MVP flow
1. Import an uploaded PDF or an explicitly provided official form URL.
2. Extract text and interactive fields. For scanned PDFs, use OCR and require review of low-confidence fields.
3. Normalize labels into a field schema: `id, label, type, required, options, page, source_locator`.
4. Match against user-approved profile facts. Every proposed match includes source, confidence and a user-editable value. Never invent missing answers.
5. Show the original form side-by-side with proposed values; validate field types and required values.
6. After explicit review, generate a filled PDF or a browser handoff; preserve the original and a redacted audit log.
7. For approved claims, hand off a signed, expiring submission authorization scoped to one form, one destination, and one exact payload. Record receipts and failure details. CAPTCHA and administrator identity checks stay human-controlled.

## Integration boundary
Claims Agent sends only `form_url`, `claim_id`, and a short-lived signed request token to the Form Filler. The Form Filler requests only user-selected facts; it returns a prepared artifact identifier, mapping report, and status. No credentials, SSNs, signatures, or evidence attachments in URLs or logs. Use OAuth/OIDC or independently authenticated service tokens for multi-user deployment. Verify destination allowlists and protect against SSRF and malicious uploads.

## API draft
- `POST /v1/forms/import` — upload or official URL; returns job ID.
- `GET /v1/forms/{id}/fields` — extracted field schema and confidence.
- `POST /v1/forms/{id}/map` — suggest mappings from explicitly authorized profile keys.
- `POST /v1/forms/{id}/prepare` — validated reviewed values; returns artifact ID.
- `POST /v1/forms/{id}/authorize-submission` — user-approved exact payload, method and destination.
- `POST /v1/forms/{id}/submit` — permitted adapter only; idempotency key required.
- `GET /v1/forms/{id}/status` — prepared/submitted/manual-action/failed with receipt.

## Implementation order
1. Standalone app shell and private profile vault.
2. PDF text and AcroForm extraction, field mapper and downloadable filled PDF.
3. Scanned PDF OCR and quality checks.
4. HTML form parser and reviewed browser filling.
5. Submission adapters, print/mail packet generation, batch jobs, and integrations.

## Brand
Unfiltered Ink: charcoal/black backgrounds, burgundy and hot-pink highlights, rose accents, elegant high-contrast typography. Prioritize readable field labels and accessible controls over decoration.

**Not implemented by this document:** working endpoints, extraction, submission, or deployment.
