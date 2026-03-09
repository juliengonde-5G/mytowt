import logging
import os
import stat

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager

from app.config import get_settings
from app.database import init_db
from app.auth import AuthRequired
from app.routers.auth_router import router as auth_router
from app.routers.dashboard_router import router as dashboard_router
from app.routers.planning_router import router as planning_router
from app.routers.api_ports import router as api_ports_router
from app.routers.admin_router import router as admin_router
from app.routers.kpi_router import router as kpi_router
from app.routers.commercial_router import router as commercial_router
from app.routers.escale_router import router as escale_router
from app.routers.finance_router import router as finance_router
from app.routers.crew_router import router as crew_router
from app.routers.cargo_router import router as cargo_router, ext_router as cargo_ext_router
from app.routers.onboard_router import router as onboard_router
from app.routers.passenger_router import router as passenger_router
from app.routers.passenger_ext_router import ext_router as passenger_ext_router, boarding_redirect_router
from app.routers.mrv_router import router as mrv_router
from app.routers.claim_router import router as claim_router
from app.routers.tracking_router import router as tracking_router
from app.routers.pricing_router import router as pricing_router
from app.routers.planning_ext_router import ext_router as planning_ext_router

logger = logging.getLogger(__name__)

settings = get_settings()


def _fix_static_permissions():
    """Fix file permissions on static and templates directories at startup to prevent 403."""
    for base_dir in ["app/static", "app/templates"]:
        if not os.path.isdir(base_dir):
            continue
        try:
            os.chmod(base_dir, os.stat(base_dir).st_mode | stat.S_IROTH | stat.S_IXOTH | stat.S_IRGRP | stat.S_IXGRP)
        except OSError:
            pass
        for root, dirs, files in os.walk(base_dir):
            for d in dirs:
                p = os.path.join(root, d)
                try:
                    os.chmod(p, os.stat(p).st_mode | stat.S_IROTH | stat.S_IXOTH | stat.S_IRGRP | stat.S_IXGRP)
                except OSError:
                    pass
            for f in files:
                p = os.path.join(root, f)
                try:
                    os.chmod(p, os.stat(p).st_mode | stat.S_IROTH | stat.S_IRGRP)
                except OSError:
                    pass


def _validate_secret_key():
    """Warn if SECRET_KEY is still the default insecure value."""
    default_key = "towt_secret_key_change_in_production_2025"
    if settings.SECRET_KEY == default_key:
        logger.warning(
            "SECURITY WARNING: SECRET_KEY is set to the default value. "
            "Set a strong, unique SECRET_KEY in your .env file for production. "
            "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _fix_static_permissions()
    _validate_secret_key()
    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    redirect_slashes=False,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ── CORS — restricted methods and headers ────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://my.towt.eu", "http://51.178.59.174"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "HX-Request",
                   "HX-Current-URL", "HX-Target", "HX-Trigger"],
)


# ── Security headers middleware ──────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https://*.tile.openstreetmap.org; "
            "connect-src 'self' https://unpkg.com https://nominatim.openstreetmap.org; "
        )
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# ── CSRF middleware ──────────────────────────────────────────
from app.csrf import CSRFMiddleware
app.add_middleware(CSRFMiddleware)


# ── Exception handlers ───────────────────────────────────────
@app.exception_handler(AuthRequired)
async def auth_required_handler(request: Request, exc: AuthRequired):
    return RedirectResponse(url="/login", status_code=303)


from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    # Content negotiation: JSON for API clients, HTML for browsers
    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return JSONResponse({"detail": "Forbidden"}, status_code=403)

    from app.templating import templates
    return templates.TemplateResponse("403.html", {
        "request": request, "user": None,
        "active_module": "", "lang": "fr",
    }, status_code=403)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return JSONResponse({"detail": "Not found"}, status_code=404)

    from app.templating import templates
    try:
        return templates.TemplateResponse("404.html", {
            "request": request, "user": None,
            "active_module": "", "lang": "fr",
        }, status_code=404)
    except Exception:
        return PlainTextResponse("Page non trouvée", status_code=404)


# ── Security.txt endpoint ────────────────────────────────────
@app.get("/.well-known/security.txt", response_class=PlainTextResponse)
async def security_txt():
    return (
        "Contact: security@towt.eu\n"
        "Expires: 2027-03-09T12:00:00.000Z\n"
        "Preferred-Languages: fr, en\n"
    )


from app.permissions import require_permission

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(planning_router, dependencies=[Depends(require_permission("planning", "C"))])
app.include_router(api_ports_router)
from app.routers.admin_router import require_admin
app.include_router(admin_router, dependencies=[Depends(require_admin)])
app.include_router(kpi_router, dependencies=[Depends(require_permission("kpi", "C"))])
app.include_router(commercial_router, dependencies=[Depends(require_permission("commercial", "C"))])
app.include_router(escale_router, dependencies=[Depends(require_permission("escale", "C"))])
app.include_router(finance_router, dependencies=[Depends(require_permission("finance", "C"))])
app.include_router(crew_router, dependencies=[Depends(require_permission("crew", "C"))])
app.include_router(cargo_router, dependencies=[Depends(require_permission("cargo", "C"))])
app.include_router(cargo_ext_router)
app.include_router(onboard_router, dependencies=[Depends(require_permission("captain", "C"))])
app.include_router(passenger_router, dependencies=[Depends(require_permission("passengers", "C"))])
app.include_router(passenger_ext_router)
app.include_router(boarding_redirect_router)  # Legacy /boarding/{token} → /passenger/{token}
app.include_router(mrv_router, dependencies=[Depends(require_permission("mrv", "C"))])
app.include_router(claim_router, dependencies=[Depends(require_permission("captain", "C"))])
app.include_router(pricing_router, dependencies=[Depends(require_permission("commercial", "C"))])
app.include_router(planning_ext_router)  # Public — shareable planning links (no auth)
app.include_router(tracking_router)  # API — no auth (called by Power Automate)
