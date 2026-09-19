import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import settings
from app.monitor import redis_client

_development_secret = secrets.token_hex(32)
_attempts = defaultdict(deque)
_lock = threading.Lock()


def signature(value):
    return hmac.new(
        (settings.session_secret or _development_secret).encode(), value.encode(), hashlib.sha256
    ).hexdigest()


def create_session():
    payload = f"{int(time.time()) + 43200}.{secrets.token_hex(24)}"
    token = f"{payload}.{signature(payload)}"
    return token, signature("csrf:" + token)


def authenticate(request: Request):
    token = request.cookies.get("claims_session", "")
    try:
        expiry, nonce, signed = token.split(".")
        if int(expiry) < time.time() or not hmac.compare_digest(signed, signature(f"{expiry}.{nonce}")):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(401, "Sign in to continue.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("origin") != settings.app_url.rstrip("/") or not hmac.compare_digest(
            request.headers.get("x-csrf-token", ""), signature("csrf:" + token)
        ):
            raise HTTPException(403, "Invalid request origin or CSRF token.")
    return "owner"


def rate_limit_login(request):
    # Ignore untrusted forwarding headers. Railway is the sole configured proxy in deployment.
    host = request.client.host if request.client else "unknown"
    key = "settlement-agent:login:" + hashlib.sha256(host.encode()).hexdigest()
    client = redis_client()
    if client:
        try:
            with client.pipeline() as pipe:
                pipe.incr(key)
                pipe.expire(key, 300)
                count = pipe.execute()[0]
        except Exception:
            raise HTTPException(503, "Authentication rate limiter is unavailable.")
    else:
        with _lock:
            now = time.time()
            for old_key in list(_attempts):
                while _attempts[old_key] and _attempts[old_key][0] < now - 300:
                    _attempts[old_key].popleft()
                if not _attempts[old_key]:
                    del _attempts[old_key]
            _attempts[key].append(now)
            count = len(_attempts[key])
    if count > 10:
        raise HTTPException(429, "Too many sign-in attempts. Try again in five minutes.")
