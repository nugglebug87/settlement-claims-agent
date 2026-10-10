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


_DOCUMENT_LABEL = re.compile(r"documents?|forms?\s*(?:and|&)\s*notices?|important\s+documents?", re.I)
_DOCUMENT_PATH = re.compile(r"(?:^|/)(?:documents?|forms)(?:/|$)", re.I)


def find_documents_pages(html: str, official_url: str) -> list[str]:
    """Find same-host HTTPS document index pages for a bounded second fetch."""
    base = urlsplit(official_url)
    if base.scheme != "https" or not base.hostname:
        raise ValueError("An official HTTPS URL is required.")
    results = []
    for anchor in BeautifulSoup(html, "html.parser").select("a[href]"):
        target = urlsplit(urljoin(official_url, anchor["href"]))
        if (
            target.scheme != "https"
            or target.hostname != base.hostname
            or target.port not in (None, 443)
            or target.username or target.password
        ):
            continue
        if not (_DOCUMENT_LABEL.search(anchor.get_text(" ", strip=True))
                or _DOCUMENT_PATH.search(target.path)):
            continue
        link = urlunsplit((target.scheme, target.netloc, target.path, target.query, ""))
        if link not in results and link != official_url:
            results.append(link)
    return results[:5]
