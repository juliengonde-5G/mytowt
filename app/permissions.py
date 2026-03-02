"""
Permission system for TOWT Planning App.

Roles: administrateur, operation, armement, technique, data_analyst, marins
Modules: planning, commercial, escale, finance, kpi, captain, crew, cargo
Permissions: C (consult), M (modify), S (delete/suppress)

Usage:
  from app.permissions import can_view, can_edit, can_delete, require_permission
  
  # In route:
  if not can_view(user, 'commercial'):
      raise HTTPException(403)
  
  # As dependency:
  @router.get("/commercial")
  async def index(user = Depends(require_permission('commercial', 'C'))):
"""

from fastapi import Depends, HTTPException
from app.auth import get_current_user

# ═══════════════════════════════════════════════════════════════
# PERMISSION MATRIX
# Key: (role, module) → set of permissions {'C', 'M', 'S'}
# Empty set or absent = no access
# ═══════════════════════════════════════════════════════════════

_MATRIX = {
    # ─── ADMINISTRATEUR ──────────────────────────────────
    ("administrateur", "planning"):    {"C", "M", "S"},
    ("administrateur", "commercial"):  {"C", "M", "S"},
    ("administrateur", "escale"):      {"C", "M", "S"},
    ("administrateur", "finance"):     {"C", "M", "S"},
    ("administrateur", "kpi"):         {"C", "M", "S"},
    ("administrateur", "captain"):     {"C", "M", "S"},
    ("administrateur", "crew"):        {"C", "M", "S"},
    ("administrateur", "cargo"):       {"C", "M", "S"},
    ("administrateur", "mrv"):         {"C", "M", "S"},

    # ─── OPERATION ───────────────────────────────────────
    ("operation", "planning"):    {"C", "M"},
    ("operation", "commercial"):  {"C", "M"},
    ("operation", "escale"):      {"C", "M"},
    # finance: no access
    ("operation", "kpi"):         {"C"},
    ("operation", "captain"):     {"C"},
    ("operation", "crew"):        {"C"},
    ("operation", "cargo"):       {"C", "M", "S"},
    ("operation", "mrv"):         {"C", "M"},

    # ─── ARMEMENT ────────────────────────────────────────
    ("armement", "planning"):    {"C"},
    # commercial: no access
    ("armement", "escale"):      {"C"},
    # finance: no access
    ("armement", "kpi"):         {"C"},
    ("armement", "captain"):     {"C"},
    ("armement", "crew"):        {"C", "M", "S"},
    # cargo: no access
    ("armement", "mrv"):         {"C"},

    # ─── TECHNIQUE ───────────────────────────────────────
    ("technique", "planning"):    {"C"},
    # commercial: no access
    ("technique", "escale"):      {"C", "M", "S"},
    # finance: no access
    ("technique", "kpi"):         {"C"},
    ("technique", "captain"):     {"C"},
    ("technique", "crew"):        {"C"},
    # cargo: no access
    ("technique", "mrv"):         {"C", "M"},

    # ─── DATA ANALYST ────────────────────────────────────
    ("data_analyst", "planning"):    {"C"},
    ("data_analyst", "commercial"):  {"C"},
    ("data_analyst", "escale"):      {"C"},
    ("data_analyst", "finance"):     {"C", "M", "S"},
    ("data_analyst", "kpi"):         {"C"},
    ("data_analyst", "captain"):     {"C"},
    ("data_analyst", "crew"):        {"C"},
    ("data_analyst", "cargo"):       {"C"},
    ("data_analyst", "mrv"):         {"C", "M"},

    # ─── MARINS ──────────────────────────────────────────
    ("marins", "planning"):    {"C"},
    # commercial: no access
    ("marins", "escale"):      {"C", "M", "S"},
    # finance: no access
    ("marins", "kpi"):         {"C"},
    ("marins", "captain"):     {"C", "M", "S"},
    ("marins", "crew"):        {"C"},
    ("marins", "cargo"):       {"C"},
    ("marins", "mrv"):         {"C"},
}

# Legacy role mapping (old roles → new roles)
_LEGACY_MAP = {
    "admin": "administrateur",
    "manager": "operation",
    "operator": "operation",
    "viewer": "data_analyst",
}

# All roles for settings page
ROLES = [
    ("administrateur", "Administrateur"),
    ("operation", "Opération"),
    ("armement", "Armement"),
    ("technique", "Technique"),
    ("data_analyst", "Data Analyst"),
    ("marins", "Marins"),
]

# All modules
MODULES = [
    "planning", "commercial", "escale", "finance",
    "kpi", "captain", "crew", "cargo", "mrv",
]

# Module display names
MODULE_NAMES = {
    "planning": "Planning",
    "commercial": "Commercial",
    "escale": "Escale",
    "finance": "Finance",
    "kpi": "KPI",
    "captain": "Capitaine",
    "crew": "Équipage",
    "cargo": "Cargo Docs",
    "mrv": "MRV Fuel",
}


def _resolve_role(role: str) -> str:
    """Map legacy roles to new ones."""
    return _LEGACY_MAP.get(role, role)


def get_permissions(user, module: str) -> set:
    """Get permission set for a user on a module."""
    role = _resolve_role(user.role) if user else ""
    return _MATRIX.get((role, module), set())


def can_view(user, module: str) -> bool:
    """Can the user see this module?"""
    return "C" in get_permissions(user, module)


def can_edit(user, module: str) -> bool:
    """Can the user modify data in this module?"""
    return "M" in get_permissions(user, module)


def can_delete(user, module: str) -> bool:
    """Can the user delete data in this module?"""
    return "S" in get_permissions(user, module)


def has_any_access(user, module: str) -> bool:
    """Does the user have any access to this module?"""
    return len(get_permissions(user, module)) > 0


def get_accessible_modules(user) -> list:
    """Return list of modules the user can access."""
    role = _resolve_role(user.role) if user else ""
    return [m for m in MODULES if _MATRIX.get((role, m), set())]


def require_permission(module: str, level: str = "C"):
    """
    FastAPI dependency factory. Checks user has required permission level.
    level: 'C' (view), 'M' (modify), 'S' (delete)
    """
    async def _check(user=Depends(get_current_user)):
        perms = get_permissions(user, module)
        if level not in perms:
            raise HTTPException(
                status_code=403,
                detail=f"Accès non autorisé au module {module}"
            )
        return user
    return _check
