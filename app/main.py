from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
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
from app.routers.passenger_ext_router import ext_router as passenger_ext_router
from app.routers.mrv_router import router as mrv_router
from app.routers.claim_router import router as claim_router
from app.routers.tracking_router import router as tracking_router
from app.routers.pricing_router import router as pricing_router
from app.routers.planning_ext_router import ext_router as planning_ext_router

import os
import stat

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    _fix_static_permissions()
    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    redirect_slashes=False,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://my.towt.eu", "http://51.178.59.174", "http://localhost", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https://*.tile.openstreetmap.org; "
            "connect-src 'self' https://unpkg.com https://nominatim.openstreetmap.org; "
        )
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(AuthRequired)
async def auth_required_handler(request: Request, exc: AuthRequired):
    return RedirectResponse(url="/login", status_code=303)


from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    from app.templating import templates
    from app.auth import get_current_user_optional
    from app.database import get_db
    # Try to get user for sidebar
    return templates.TemplateResponse("403.html", {
        "request": request, "user": None,
        "active_module": "", "lang": "fr",
    }, status_code=403)


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
app.include_router(mrv_router, dependencies=[Depends(require_permission("mrv", "C"))])
app.include_router(claim_router, dependencies=[Depends(require_permission("captain", "C"))])
app.include_router(pricing_router, dependencies=[Depends(require_permission("commercial", "C"))])
app.include_router(planning_ext_router)  # Public — shareable planning links (no auth)
app.include_router(tracking_router)  # API — no auth (called by Power Automate)
