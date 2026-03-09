import time
import logging
from collections import defaultdict
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.templating import templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.auth import verify_password, create_session_token, COOKIE_NAME
from app.utils.activity import log_activity, get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# ── Rate limiting for login ──────────────────────────────────
# In-memory store: {ip: [(timestamp, ...], ...}
_login_attempts: dict[str, list[float]] = defaultdict(list)
LOGIN_RATE_LIMIT = 5          # max attempts
LOGIN_RATE_WINDOW = 60        # per 60 seconds
LOGIN_LOCKOUT_DURATION = 300  # lockout 5 minutes after exceeding


def _is_rate_limited(ip: str) -> bool:
    """Check if an IP is rate-limited for login attempts."""
    now = time.time()
    # Clean old entries
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < LOGIN_LOCKOUT_DURATION]

    # Count recent attempts within the rate window
    recent = [t for t in _login_attempts[ip] if now - t < LOGIN_RATE_WINDOW]
    return len(recent) >= LOGIN_RATE_LIMIT


def _record_attempt(ip: str):
    """Record a login attempt for rate limiting."""
    _login_attempts[ip].append(time.time())


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {
        "request": request,
        "error": None,
    })


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    ip = get_client_ip(request)

    # Rate limiting check
    if _is_rate_limited(ip):
        logger.warning(f"Login rate limited for IP {ip}")
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "error": "Trop de tentatives de connexion. Veuillez réessayer dans quelques minutes.",
        }, status_code=429)

    # Truncate input to prevent abuse
    username = username[:50]
    password = password[:128]

    # Find user
    result = await db.execute(
        select(User).where(User.username == username, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        _record_attempt(ip)
        # Log failed login
        await log_activity(db, action="login_fail", module="auth",
                           detail=f"username: {username}", ip_address=ip)
        await db.commit()
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "error": "Identifiant ou mot de passe incorrect",
        })

    # Log successful login
    await log_activity(db, user=user, action="login", module="auth",
                       entity_type="user", entity_id=user.id,
                       entity_label=user.full_name, ip_address=ip)
    await db.commit()

    # Create session
    token = create_session_token(user.id)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        max_age=60 * 60 * 8,  # 8 hours
        samesite="lax",
    )
    return response


@router.get("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    # Try to log the logout
    from app.auth import get_current_user_optional
    try:
        user = await get_current_user_optional(request, db)
        if user:
            await log_activity(db, user=user, action="logout", module="auth",
                               entity_type="user", entity_id=user.id,
                               entity_label=user.full_name,
                               ip_address=get_client_ip(request))
            await db.commit()
    except Exception:
        pass
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response
