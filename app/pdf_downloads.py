"""Short-lived private PDF downloads; never written to disk or the database."""

import hashlib
import secrets
import threading
import time

from fastapi import HTTPException

_drafts = {}
_lock = threading.Lock()
TTL_SECONDS = 120
MAX_TOTAL_BYTES = 32 * 1024 * 1024


def remember_pdf(data, session, filename):
    if len(data) > MAX_TOTAL_BYTES:
        raise HTTPException(413, "Generated PDF is too large. Use the official form.")
    with _lock:
        now = time.monotonic()
        for key in list(_drafts):
            if _drafts[key][0] <= now:
                del _drafts[key]
        while _drafts and sum(len(v[2]) for v in _drafts.values()) + len(data) > MAX_TOTAL_BYTES:
            del _drafts[next(iter(_drafts))]
        token = secrets.token_urlsafe(32)
        _drafts[token] = (now + TTL_SECONDS, hashlib.sha256(session.encode()).hexdigest(), data, filename)
    return "/api/pdf/drafts/" + token


def retrieve_pdf(token, session):
    with _lock:
        entry = _drafts.get(token)
        if not entry or entry[0] <= time.monotonic():
            _drafts.pop(token, None)
            raise HTTPException(404, "This draft link expired. Generate the PDF again.")
        if entry[1] != hashlib.sha256(session.encode()).hexdigest():
            raise HTTPException(404, "Draft not found in this session.")
        return entry[2], entry[3]
