"""Read-only, bounded claim-form discovery on verified official source hosts."""

from app.claim_form_links import find_claim_form_links, find_documents_pages
from app.discovery import fetch_source


def discover_official_claim_forms(official_url: str) -> dict:
    """Inspect one official HTML page and up to five same-host document pages.

    All network reads use the existing HTTPS, DNS/IP, host-allowlist, size,
    timeout and no-redirect checks. Nothing is downloaded or submitted.
    """
    forms: list[str] = []
    pages_checked: list[str] = []
    html, content_type = fetch_source(official_url)
    pages_checked.append(official_url)
    if "html" not in content_type.lower():
        return {"forms": forms, "pages_checked": pages_checked}
    for link in find_claim_form_links(html, official_url):
        if link not in forms:
            forms.append(link)
    for documents_url in find_documents_pages(html, official_url):
        try:
            document_html, document_type = fetch_source(documents_url)
        except (ValueError, OSError):
            continue
        pages_checked.append(documents_url)
        if "html" not in document_type.lower():
            continue
        for link in find_claim_form_links(document_html, documents_url):
            if link not in forms:
                forms.append(link)
        if len(forms) >= 30:
            break
    return {"forms": forms[:30], "pages_checked": pages_checked}
