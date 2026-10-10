"""Identify candidate claim forms in already-fetched official settlement HTML.

Pure parsing only: no network access, downloading, or submission. Callers must
verify the official source and use the existing allowlisted fetch safeguards.
"""
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

_FORM_LABEL = re.compile(r"claim\s*form|file\s+(?:a\s+)?claim|submit\s+(?:a\s+)?claim|proof\s+of\s+claim", re.I)
_FORM_PATH = re.compile(r"(?:claim[-_]?form|proof[-_]?of[-_]?claim)", re.I)


def find_claim_form_links(html: str, official_url: str) -> list[str]:
    """Return deduplicated same-host HTTPS candidate form links in page order."""
    base = urlsplit(official_url)
    if base.scheme != "https" or not base.hostname or base.username or base.password:
        raise ValueError("An official HTTPS URL is required.")
    soup = BeautifulSoup(html, "html.parser")
    results: list[str] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("#", "javascript:", "data:")):
            continue
        candidate = urlsplit(urljoin(official_url, href))
        if (
            candidate.scheme != "https"
            or candidate.hostname != base.hostname
            or candidate.port not in (None, 443)
            or candidate.username
            or candidate.password
        ):
            continue
        label = anchor.get_text(" ", strip=True) + " " + anchor.get("title", "")
        if not (_FORM_LABEL.search(label) or _FORM_PATH.search(candidate.path)):
            continue
        normalized = urlunsplit((candidate.scheme, candidate.netloc, candidate.path, candidate.query, ""))
        if normalized not in seen:
            seen.add(normalized)
            results.append(normalized)
    return results
