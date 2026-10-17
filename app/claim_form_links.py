"""Identify candidate claim-form links in an already fetched settlement page.

No network requests or eligibility decisions are made here. Results require review.
"""
import re
from urllib.parse import urljoin, urlsplit, urldefrag
from bs4 import BeautifulSoup

FORM_LABEL = re.compile(r"\b(claim\s*form|submit\s*(?:a\s*)?claim|file\s*(?:a\s*)?claim|proof\s*of\s*claim)\b", re.I)
FORM_FILE = re.compile(r"(?:claim[-_ ]?form|proof[-_ ]?of[-_ ]?claim)[^/]*\.pdf$", re.I)
EXCLUDE = re.compile(r"\b(sample|example|instructions?\s+only)\b", re.I)


def find_claim_form_links(html: str, page_url: str, *, max_results: int = 25) -> list[dict]:
    """Find candidate links on the same HTTPS hostname, without fetching them."""
    base = urlsplit(page_url)
    if base.scheme != "https" or not base.hostname or base.username or base.password:
        raise ValueError("An HTTPS settlement page URL is required")
    soup = BeautifulSoup(html, "html.parser")
    results, seen = [], set()
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "data:")):
            continue
        url, _ = urldefrag(urljoin(page_url, href))
        target = urlsplit(url)
        if (target.scheme != "https" or target.hostname != base.hostname or
                target.username or target.password or target.port not in (None, 443)):
            continue
        label = " ".join(anchor.stripped_strings).strip()
        if EXCLUDE.search(label):
            continue
        if not (FORM_LABEL.search(label) or FORM_FILE.search(target.path)):
            continue
        if url not in seen:
            seen.add(url)
            results.append({"url": url, "label": label[:200] or "Claim form PDF",
                            "is_pdf": target.path.lower().endswith(".pdf"),
                            "status": "candidate_requires_review"})
        if len(results) >= max_results:
            break
    return results
