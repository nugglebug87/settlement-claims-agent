from app.claim_form_links import find_claim_form_links


def test_finds_forms_on_documents_page():
    html = """<a href="/documents">Documents</a><a href="/docs/claim-form.pdf">Download Claim Form</a>"""
    links = find_claim_form_links(html, "https://claims.example.org/documents")
    assert links == ["https://claims.example.org/docs/claim-form.pdf"]


def test_rejects_external_and_insecure_links():
    html = """<a href="https://evil.example/claim.pdf">Claim Form</a><a href="http://claims.example.org/claim.pdf">Claim Form</a>"""
    assert find_claim_form_links(html, "https://claims.example.org/") == []


def test_deduplicates_and_ignores_navigation():
    html = """<a href="/documents">Documents</a><a href="/claim-form.pdf">Claim Form</a><a href="/claim-form.pdf#page=1">Download Claim Form</a>"""
    assert find_claim_form_links(html, "https://claims.example.org/") == ["https://claims.example.org/claim-form.pdf"]


def test_finds_online_claim_form():
    html = '<a href="/file-a-claim">File a Claim</a>'
    assert find_claim_form_links(html, "https://claims.example.org/") == ["https://claims.example.org/file-a-claim"]


def test_documents_page_links_are_discovered_separately():
    from app.claim_form_links import find_documents_pages
    html = '<a href="/documents">Documents</a><a href="/faq">FAQ</a>'
    assert find_documents_pages(html, "https://claims.example.org/") == ["https://claims.example.org/documents"]


def test_documents_pages_reject_external_hosts():
    from app.claim_form_links import find_documents_pages
    html = '<a href="https://other.example/documents">Documents</a>'
    assert find_documents_pages(html, "https://claims.example.org/") == []
