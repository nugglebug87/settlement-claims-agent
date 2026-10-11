# Changelog

## Unreleased

### Changed

- The home screen is now Claim Finder, with short instructions, a single search button, default source selections, and easy-to-read claim cards. Source options and search details expand when needed.
- Form Filler has its own navigation entry and preparation screen.

### Added

- PDF inspection returns page text, interactive field labels, required flags, and top-left field positions. The review screen shows extracted text beside page previews.
- Pages without a text layer explicitly require visual review; OCR is not implemented.

### Fixed

- API tests isolate login rate-limit state so additional endpoint tests do not cause unrelated sign-in failures.

## 0.1.0 — Initial MVP

### Added

- Rose-led gothic editorial dashboard and responsive private claim workspace.
- Source discovery, optional AI extraction, explainable eligibility, duplicate protection and seven priority queues.
- Evidence references, exact-packet approval, human submission handoff, confirmations and payment/status records.
- PostgreSQL migrations, optional existing Redis integration, in-app monitoring alerts and audit history.
- Secure configuration, Railway/Docker deployment and PostgreSQL/Redis CI startup checks.
