"""CSRF protection for forms.

Strategy: Double-submit cookie pattern.
- A random token is stored in a cookie (towt_csrf).
- Templates inject the token as a hidden field via {{ csrf_input() }}.
- On POST/DELETE, the middleware compares cookie vs form field.
- HTMX requests with HX-Request header also need the token.
- External routes (/p/, /passenger/, /boarding/, /planning/ext/) are excluded.
"""
import secrets
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

CSRF_COOKIE_NAME = "towt_csrf"
CSRF_FIELD_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
TOKEN_LENGTH = 32

# Routes excluded from CSRF validation (public/external portals)
CSRF_EXEMPT_PREFIXES = ("/p/", "/passenger/", "/boarding/", "/planning/ext/", "/api/", "/login", "/.well-known/")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def generate_csrf_token() -> str:
    return secrets.token_hex(TOKEN_LENGTH)


def csrf_input(request: Request) -> str:
    """Template helper: returns an HTML hidden input with the CSRF token."""
    token = request.cookies.get(CSRF_COOKIE_NAME, "")
    return f'<input type="hidden" name="{CSRF_FIELD_NAME}" value="{token}">'


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Ensure CSRF cookie exists (set on every response if missing)
        csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)

        if request.method in SAFE_METHODS:
            response = await call_next(request)
            if not csrf_cookie:
                token = generate_csrf_token()
                response.set_cookie(
                    CSRF_COOKIE_NAME, token,
                    httponly=False,  # JS/HTMX needs to read it
                    secure=True,
                    samesite="lax",
                    max_age=60 * 60 * 8,
                )
            return response

        # For unsafe methods, check exemptions
        path = request.url.path
        if any(path.startswith(prefix) for prefix in CSRF_EXEMPT_PREFIXES):
            response = await call_next(request)
            return response

        # Validate CSRF token
        if not csrf_cookie:
            logger.warning(f"CSRF: missing cookie for {request.method} {path}")
            return JSONResponse({"detail": "CSRF token missing"}, status_code=403)

        # Check header first (HTMX/AJAX), then form field
        submitted_token = request.headers.get(CSRF_HEADER_NAME)
        if not submitted_token:
            # Try to read from form data (only if content-type is form)
            content_type = request.headers.get("content-type", "")
            if "form" in content_type:
                try:
                    form = await request.form()
                    submitted_token = form.get(CSRF_FIELD_NAME)
                except Exception:
                    pass

        if not submitted_token or submitted_token != csrf_cookie:
            logger.warning(f"CSRF: token mismatch for {request.method} {path}")
            return JSONResponse({"detail": "CSRF validation failed"}, status_code=403)

        response = await call_next(request)
        return response
