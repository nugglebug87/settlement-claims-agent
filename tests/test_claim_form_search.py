from unittest.mock import patch

from app.claim_form_search import discover_official_claim_forms


def test_searches_official_documents_page_with_existing_safe_fetch():
    homepage = '<a href="/documents">Documents</a>'
    documents = '<a href="/docs/claim-form.pdf">Claim Form</a>'
    with patch("app.claim_form_search.fetch_source", side_effect=[
        (homepage, "text/html"), (documents, "text/html")
    ]) as fetch:
        result = discover_official_claim_forms("https://claims.example.org/")
    assert result["forms"] == ["https://claims.example.org/docs/claim-form.pdf"]
    assert result["pages_checked"] == ["https://claims.example.org/", "https://claims.example.org/documents"]
    assert fetch.call_count == 2


def test_rejects_non_html_without_following_links():
    with patch("app.claim_form_search.fetch_source", return_value=("%PDF", "application/pdf")):
        result = discover_official_claim_forms("https://claims.example.org/form.pdf")
    assert result["forms"] == []
    assert result["pages_checked"] == ["https://claims.example.org/form.pdf"]


def test_failing_document_page_does_not_hide_homepage_forms():
    homepage = '<a href="/claim-form.pdf">Claim Form</a><a href="/documents">Documents</a>'
    with patch("app.claim_form_search.fetch_source", side_effect=[
        (homepage, "text/html"), ValueError("Blocked")
    ]):
        result = discover_official_claim_forms("https://claims.example.org/")
    assert result["forms"] == ["https://claims.example.org/claim-form.pdf"]
