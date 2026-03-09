"""
Portal security utilities: rate limiting on token lookups and access logging.
"""
import time
import logging
from collections import defaultdict
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# ── Rate limiting for token-based portal access ──
# Track failed token lookups per IP
_token_attempts: dict[str, list[float]] = defaultdict(list)
TOKEN_RATE_LIMIT = 10  # max attempts per window
TOKEN_RATE_WINDOW = 60  # seconds
TOKEN_LOCKOUT_DURATION = 300  # 5 minutes


def check_token_rate_limit(request: Request):
    """Rate-limit token validation attempts per IP. Call before token lookup."""
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    attempts = _token_attempts[ip]
    # Clean old entries
    _token_attempts[ip] = [t for t in attempts if now - t < TOKEN_LOCKOUT_DURATION]
    attempts = _token_attempts[ip]

    if len(attempts) >= TOKEN_RATE_LIMIT:
        oldest_in_window = [t for t in attempts if now - t < TOKEN_RATE_WINDOW]
        if len(oldest_in_window) >= TOKEN_RATE_LIMIT:
            logger.warning(f"Portal rate limit exceeded for IP {ip}")
            raise HTTPException(429, detail="Trop de tentatives. Réessayez dans quelques minutes.")


def record_token_attempt(request: Request):
    """Record a token lookup attempt (call on 404/invalid token)."""
    ip = request.client.host if request.client else "unknown"
    _token_attempts[ip].append(time.time())


async def log_portal_access(db, request: Request, portal_type: str, token: str,
                            booking_id: int = None, packing_list_id: int = None):
    """Log an access to an external portal for RGPD audit trail."""
    from app.models.portal_access_log import PortalAccessLog
    log_entry = PortalAccessLog(
        portal_type=portal_type,
        token=token,
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent", ""))[:500],
        path=str(request.url.path),
        booking_id=booking_id,
        packing_list_id=packing_list_id,
    )
    db.add(log_entry)
