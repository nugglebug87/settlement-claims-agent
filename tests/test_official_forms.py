import base64
import hashlib

import pytest

from app import official_forms

NOTICE_URL = "https://notice.example/settlement"
DOCUMENTS_URL = "https://notice.example/documents"
FORM_URL = "https://notice.example/files/claim-form.pdf"
PDF = b"%PDF-1.7\nsynthetic test form"


def install_fixture(monkeypatch):
    pages = {
        NOTICE_URL: (
            b'<a href="/documents">Settlement Documents</a>',
            "text/html",
        ),
        DOCUMENTS_URL: (
            b'<a href="/files/claim-form.pdf">Claim Form (PDF)</a>',
            "text/html",
        ),
        FORM_URL: (PDF, "application/pdf"),
    }

    def fetch(url, allowed_hosts, limit):
        assert "notice.example" in allowed_hosts
        body, content_type = pages[url]
        assert len(body) <= limit
        return body, content_type

    monkeypatch.setattr(official_forms, "fetch_document", fetch)
    monkeypatch.setattr(official_forms, "validate_source_url", lambda *args, **kwargs: (None, "203.0.113.1"))


def test_finds_claim_form_nested_under_documents(monkeypatch):
    install_fixture(monkeypatch)

    assert official_forms.find_form_candidates(NOTICE_URL) == [
        {"title": "Claim Form (PDF)", "url": FORM_URL, "kind": "pdf"}
    ]


def test_finds_hyphenated_claim_form_urls_without_descriptive_link_text(monkeypatch):
    form_url = "https://notice.example/claim-form.pdf"
    monkeypatch.setattr(official_forms, "validate_source_url", lambda *args, **kwargs: (None, "203.0.113.1"))
    monkeypatch.setattr(
        official_forms,
        "fetch_document",
        lambda url, allowed_hosts, limit: (
            (b'<a href="/claim-form.pdf">Download</a>', "text/html")
            if url == NOTICE_URL
            else (PDF, "application/pdf")
        ),
    )

    assert official_forms.find_form_candidates(NOTICE_URL) == [
        {"title": "Download", "url": form_url, "kind": "pdf"}
    ]


def test_retrieves_only_a_currently_discovered_pdf(monkeypatch):
    install_fixture(monkeypatch)

    with pytest.raises(ValueError, match="found on the current official notice"):
        official_forms.retrieve_form_pdf(NOTICE_URL, "https://notice.example/other.pdf")

    result = official_forms.retrieve_form_pdf(NOTICE_URL, FORM_URL)
    assert result["title"] == "Claim Form (PDF)"
    assert result["url"] == FORM_URL
    assert result["pdf_base64"] == base64.b64encode(PDF).decode("ascii")
    assert result["sha256"] == hashlib.sha256(PDF).hexdigest()


def test_rejects_non_pdf_bytes_even_when_link_looks_like_a_pdf(monkeypatch):
    monkeypatch.setattr(official_forms, "validate_source_url", lambda *args, **kwargs: (None, "203.0.113.1"))
    form_url = "https://notice.example/claim-form.pdf"

    def fetch(url, allowed_hosts, limit):
        if url == NOTICE_URL:
            return b'<a href="/claim-form.pdf">Claim Form</a>', "text/html"
        return b"not a PDF", "application/pdf"

    monkeypatch.setattr(official_forms, "fetch_document", fetch)

    with pytest.raises(ValueError, match="did not return a PDF"):
        official_forms.retrieve_form_pdf(NOTICE_URL, form_url)


def test_does_not_follow_redirects_or_accept_private_hosts(monkeypatch):
    from app.discovery import validate_source_url

    with pytest.raises(ValueError):
        validate_source_url("http://notice.example/form.pdf", "notice.example")

    def redirect(*args, **kwargs):
        raise ValueError("Official page returned HTTP 302; redirects are not followed.")

    monkeypatch.setattr(official_forms, "fetch_document", redirect)
    with pytest.raises(ValueError, match="redirects are not followed"):
        official_forms.find_form_candidates(NOTICE_URL)
