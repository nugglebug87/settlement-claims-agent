from app.claim_form_links import find_claim_form_links


def test_finds_document_and_submission_links_without_duplicates():
    html = """<a href="/documents/claim-form.pdf">Claim Form</a>
    <a href="/documents/claim-form.pdf#page=1">Download Claim Form</a>
    <a href="/submit">File a Claim</a><a href="/notice.pdf">Notice</a>"""
    found = find_claim_form_links(html, "https://settlement.example/documents/")
    assert len(found) == 2
    assert found[0]["is_pdf"] is True
    assert all(x["status"] == "candidate_requires_review" for x in found)


def test_rejects_external_insecure_and_sample_links():
    html = """<a href="https://evil.example/claim.pdf">Claim Form</a>
    <a href="http://settlement.example/claim.pdf">Claim Form</a>
    <a href="javascript:alert(1)">Claim Form</a>
    <a href="/sample.pdf">Sample Claim Form</a>"""
    assert find_claim_form_links(html, "https://settlement.example/") == []
