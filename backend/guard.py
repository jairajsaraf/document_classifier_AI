"""Open-upload guard rails: per-IP and global daily caps, page cap, filename clean-up.

State is in memory (one process on a free instance). A restart resets it, so the hard spend
cap on the API key in the Anthropic Console is the real backstop.
"""
import io
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from loguru import logger

from backend.config import settings

_hits = defaultdict(deque)  # ip -> upload timestamps within the last hour
_day = {"date": None, "n": 0}


def reset():
    _hits.clear()
    _day.update(date=None, n=0)


def client_ip(request: Request) -> str:
    # Behind a proxy that appends the address it saw (X-Forwarded-For), the LAST entry is the one a
    # visitor cannot forge; earlier entries are whatever the client sent. Whether Render does this is
    # a deploy-time fact: see docs/VERIFY.md.
    h = settings.CLIENT_IP_HEADER
    if h and request.headers.get(h):
        return request.headers[h].split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def check_upload_quota(request: Request) -> None:
    """429 when this IP or the whole service is over its cap; otherwise counts one upload."""
    now = time.time()
    ip = client_ip(request)
    hits = _hits[ip]
    while hits and hits[0] < now - 3600:
        hits.popleft()
    if len(hits) >= settings.UPLOADS_PER_IP_PER_HOUR:
        logger.warning(f"per-IP upload limit hit for {ip!r} (header {settings.CLIENT_IP_HEADER!r}={request.headers.get(settings.CLIENT_IP_HEADER) if settings.CLIENT_IP_HEADER else None!r})")
        raise HTTPException(429, f"Upload limit reached: {settings.UPLOADS_PER_IP_PER_HOUR} per hour per visitor in this demo.")
    today = datetime.now(timezone.utc).date()
    if _day["date"] != today:
        _day.update(date=today, n=0)
    if _day["n"] >= settings.UPLOADS_PER_DAY:
        raise HTTPException(429, "The demo's daily upload limit is used up. Try the sample documents, or come back tomorrow.")
    hits.append(now)
    _day["n"] += 1


def pdf_page_count(content: bytes):
    """Page count, or None when the file does not parse (classification will fail on it anyway)."""
    from pypdf import PdfReader
    try:
        return len(PdfReader(io.BytesIO(content)).pages)
    except Exception:
        return None


def clean_filename(name) -> str:
    """Display name only (the saved file gets a generated name): no path parts, no control characters."""
    base = re.split(r"[\/]", name or "")[-1]
    base = re.sub(r"[^\w .()\[\]-]", "_", base).strip(" .")
    return base[:100] or "document"
