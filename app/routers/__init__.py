from app.routers.auth_router import router as auth_router
from app.routers.dashboard_router import router as dashboard_router
from app.routers.planning_router import router as planning_router
from app.routers.api_ports import router as api_ports_router

__all__ = [
    "auth_router",
    "dashboard_router",
    "planning_router",
    "api_ports_router",
]
