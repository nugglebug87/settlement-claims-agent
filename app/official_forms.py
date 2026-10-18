"""Bounded retrieval of claim-form PDFs linked from an official notice."""

import base64
import hashlib
import http.client
import re
import socket
import ssl
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from app.config import settings
from app.discovery import validate_source_url

MAX_HTML_BYTES = 1_000_000
MAX_PDF_BYTES = 3 * 1024 * 1024
MAX_DOCUMENT_PAGES = 3
FORM_TERMS = re.compile(r"claim[\s_-]+form|proof[\s_-]+of[\s_-]+claim|claim[\s_-]+application", re.I)
DOCUMENT_TERMS = re.compile(r"documents?|court\s+filings", re.I)


def _allowed_hosts(notice_url):
    notice_host = urlsplit(notice_url).hostname
    configured = [part.strip().lower() for part in settings.source_allowed_hosts.split(",") if part.strip()]
    return ",".join(sorted({notice_host.lower(), *configured}))


def fetch_document(url, allowed_hosts, limit):
    """Fetch a public HTTPS document with pinned DNS, a strict host list, and a byte cap."""
    parts, address = validate_source_url(url, allowed_hosts=allowed_hosts)
    connection = http.client.HTTPSConnection(parts.hostname, timeout=20, context=ssl.create_default_context())
    raw = socket.create_connection((address, 443), timeout=20)
    try:
        connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=parts.hostname)
        path = (parts.path or "/") + ("?" + parts.query if parts.query else "")
        connection.request(
            "GET",
            path,
            headers={
                "User-Agent": "SettlementClaimsAgent/0.1 (+official form retrieval)",
                "Accept": "text/html,application/pdf,application/octet-stream",
                "Accept-Encoding": "identity",
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"Official page returned HTTP {response.status}; redirects are not followed.")
        body = response.read(limit + 1)
        if len(body) > limit:
            raise ValueError("Official document exceeds the retrieval size limit.")
        return body, response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
    finally:
        connection.close()
        raw.close()


def _links(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.select("a[href]"):
        label = anchor.get_text(" ", strip=True)[:300]
        url = urljoin(page_url, anchor["href"])
        parts = urlsplit(url)
        if parts.scheme == "https" and parts.hostname and not parts.username and not parts.password:
            yield {"title": label or parts.path.rsplit("/", 1)[-1] or "Official document", "url": url}


def find_form_candidates(notice_url):
    """Find claim-form PDFs on the official notice page or a linked documents page."""
    allowed_hosts = _allowed_hosts(notice_url)
    body, content_type = fetch_document(notice_url, allowed_hosts, MAX_HTML_BYTES)
    if body.startswith(b"%PDF-") or content_type == "application/pdf":
        return [{"title": "Official notice PDF", "url": notice_url, "kind": "pdf"}]
    if content_type not in {"text/html", "application/xhtml+xml", ""}:
        raise ValueError("The official notice is not an HTML page or PDF.")

    pages = [(notice_url, body.decode("utf-8", errors="replace"))]
    candidates = {}
    visited = {notice_url}
    for page_url, html in pages:
        links = list(_links(html, page_url))
        for item in links:
            if FORM_TERMS.search(item["title"] + " " + item["url"]):
                try:
                    validate_source_url(item["url"], allowed_hosts=allowed_hosts)
                except (ValueError, OSError):
                    continue
                kind = "pdf" if urlsplit(item["url"]).path.lower().endswith(".pdf") else "website"
                candidates[item["url"]] = {**item, "kind": kind}
        if page_url == notice_url:
            for item in links:
                if not DOCUMENT_TERMS.search(item["title"] + " " + item["url"]):
                    continue
                if len(pages) >= MAX_DOCUMENT_PAGES:
                    break
                if item["url"] in visited:
                    continue
                try:
                    validate_source_url(item["url"], allowed_hosts=allowed_hosts)
                    document_body, document_type = fetch_document(item["url"], allowed_hosts, MAX_HTML_BYTES)
                except (ValueError, OSError):
                    continue
                visited.add(item["url"])
                if document_body.startswith(b"%PDF-") or document_type == "application/pdf":
                    if FORM_TERMS.search(item["title"] + " " + item["url"]):
                        candidates[item["url"]] = {**item, "kind": "pdf"}
                elif document_type in {"text/html", "application/xhtml+xml", ""}:
                    if len(pages) < MAX_DOCUMENT_PAGES:
                        pages.append((item["url"], document_body.decode("utf-8", errors="replace")))

    for page_url, html in pages[1:]:
        for item in _links(html, page_url):
            if not FORM_TERMS.search(item["title"] + " " + item["url"]):
                continue
            try:
                validate_source_url(item["url"], allowed_hosts=allowed_hosts)
            except (ValueError, OSError):
                continue
            kind = "pdf" if urlsplit(item["url"]).path.lower().endswith(".pdf") else "website"
            candidates[item["url"]] = {**item, "kind": kind}

    return list(candidates.values())[:50]


def retrieve_form_pdf(notice_url, selected_url):
    """Re-discover the selected official PDF before returning its bounded in-memory bytes."""
    allowed_hosts = _allowed_hosts(notice_url)
    candidates = find_form_candidates(notice_url)
    match = next((item for item in candidates if item["url"] == selected_url and item["kind"] == "pdf"), None)
    if not match:
        raise ValueError("Choose a PDF claim form found on the current official notice page.")
    data, content_type = fetch_document(selected_url, allowed_hosts, MAX_PDF_BYTES)
    if not data.startswith(b"%PDF-") or content_type not in {
        "application/pdf",
        "application/octet-stream",
        "",
    }:
        raise ValueError("The selected official link did not return a PDF.")
    return {
        "title": match["title"],
        "url": selected_url,
        "pdf_base64": base64.b64encode(data).decode("ascii"),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
