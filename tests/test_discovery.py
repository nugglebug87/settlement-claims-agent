import pytest

from app.discovery import validate_source_url


def test_private_and_unapproved_source_hosts_are_rejected():
    for url in [
        "http://example.com/feed",
        "https://127.0.0.1/feed",
        "https://example.com@127.0.0.1/feed",
        "https://evil.example/feed",
    ]:
        with pytest.raises(ValueError):
            validate_source_url(url, "example.com")


def test_dns_private_address_is_rejected(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.1.2.3", 443))])
    with pytest.raises(ValueError):
        validate_source_url("https://example.com/feed", "example.com")
