from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from app.templating import templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime
import csv
import io

from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.vessel import Vessel
from app.models.port import Port
from app.models.leg import Leg
from app.models.finance import OpexParameter, PortConfig
from app.models.emission_parameter import EmissionParameter

router = APIRouter(prefix="/admin", tags=["admin"])

USER_ROLES = [
    {"value": "administrateur", "label": "Administrateur"},
    {"value": "operation", "label": "Opération"},
    {"value": "armement", "label": "Armement"},
    {"value": "technique", "label": "Technique"},
    {"value": "data_analyst", "label": "Data Analyst"},
    {"value": "marins", "label": "Marins"},
]




def pf(val, default=0):
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return default
    try:
        if isinstance(val, str):
            val = val.replace(" ", "").replace("\u00a0", "")
            if "." in val and "," in val:
                val = val.replace(".", "").replace(",", ".")
            elif "," in val:
                val = val.replace(",", ".")
        return float(val)
    except (ValueError, TypeError):
        return default


# ─── SETTINGS HOME ───────────────────────────────────────────
@router.get("/settings", response_class=HTMLResponse)
async def settings_home(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Users
    users_result = await db.execute(select(User).order_by(User.id))
    users = users_result.scalars().all()

    # Vessels
    vessels_result = await db.execute(select(Vessel).order_by(Vessel.code))
    vessels = vessels_result.scalars().all()

    # Port configs
    ports_result = await db.execute(
        select(PortConfig).options(selectinload(PortConfig.port)).order_by(PortConfig.port_locode)
    )
    port_configs = ports_result.scalars().all()

    # OPEX
    opex_result = await db.execute(select(OpexParameter).order_by(OpexParameter.parameter_name))
    opex_params = opex_result.scalars().all()

    # Emission params
    emission_result = await db.execute(select(EmissionParameter).order_by(EmissionParameter.parameter_name))
    emission_params = emission_result.scalars().all()

    # Locked legs count
    locked_result = await db.execute(
        select(func.count(Leg.id)).where(Leg.status == "completed")
    )
    locked_count = locked_result.scalar() or 0

    # Cabin pricing grid
    from app.models.passenger import CabinPriceGrid, CABIN_TYPE_LABELS
    pricing_result = await db.execute(
        select(CabinPriceGrid).order_by(CabinPriceGrid.origin_locode, CabinPriceGrid.destination_locode, CabinPriceGrid.cabin_type)
    )
    pricing_grid = pricing_result.scalars().all()

    # Existing routes (unique origin→dest pairs from legs)
    from sqlalchemy.orm import selectinload as sl
    routes_result = await db.execute(
        select(
            Leg.departure_port_locode, Leg.arrival_port_locode
        ).distinct()
    )
    route_pairs = routes_result.all()

    # Collect unique port locodes used in routes
    route_locodes = set()
    for dep, arr in route_pairs:
        route_locodes.add(dep)
        route_locodes.add(arr)

    # Load port names for those locodes
    route_ports = {}
    if route_locodes:
        ports_result = await db.execute(
            select(Port).where(Port.locode.in_(route_locodes)).order_by(Port.name)
        )
        for p in ports_result.scalars().all():
            route_ports[p.locode] = p.name

    # Build structured routes list for template
    existing_routes = sorted(
        [{"dep": dep, "arr": arr, "dep_name": route_ports.get(dep, dep), "arr_name": route_ports.get(arr, arr)}
         for dep, arr in route_pairs],
        key=lambda r: (r["dep_name"], r["arr_name"])
    )

    return templates.TemplateResponse("admin/settings.html", {
        "request": request, "user": user,
        "users": users, "vessels": vessels,
        "port_configs": port_configs,
        "opex_params": opex_params,
        "emission_params": emission_params,
        "locked_count": locked_count,
        "pricing_grid": pricing_grid,
        "existing_routes": existing_routes,
        "route_ports": route_ports,
        "cabin_type_labels": CABIN_TYPE_LABELS,
        "active_module": "settings",
    })


# ─── USERS CRUD ──────────────────────────────────────────────
@router.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request, user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    return templates.TemplateResponse("admin/users.html", {
        "request": request, "user": user, "users": users,
        "active_module": "settings",
    })


@router.get("/users/create", response_class=HTMLResponse)
async def user_create_form(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse("admin/user_form.html", {
        "request": request, "user": user, "edit_user": None, "error": None, "roles": USER_ROLES,
    })


@router.post("/users/create", response_class=HTMLResponse)
async def user_create_submit(
    request: Request,
    username: str = Form(...), password: str = Form(...),
    full_name: str = Form(""), role: str = Form("operation"),
    email: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.auth import hash_password
    if not email:
        email = f"{username}@towt.eu"
    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        return templates.TemplateResponse("admin/user_form.html", {
            "request": request, "user": user, "edit_user": None,
            "error": "Ce nom d'utilisateur existe déjà.", "roles": USER_ROLES,
        })
    pwd_hash = hash_password(password)
    new_user = User(username=username, email=email, hashed_password=pwd_hash, full_name=full_name, role=role)
    db.add(new_user)
    await db.flush()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/users/{uid}/edit", response_class=HTMLResponse)
async def user_edit_form(
    uid: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == uid))
    edit_user = result.scalar_one_or_none()
    if not edit_user:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("admin/user_form.html", {
        "request": request, "user": user, "edit_user": edit_user, "error": None, "roles": USER_ROLES,
    })


@router.post("/users/{uid}/edit", response_class=HTMLResponse)
async def user_edit_submit(
    uid: int, request: Request,
    full_name: str = Form(""), role: str = Form("viewer"),
    password: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.auth import hash_password as _hp
    result = await db.execute(select(User).where(User.id == uid))
    edit_user = result.scalar_one_or_none()
    if not edit_user:
        raise HTTPException(status_code=404)
    edit_user.full_name = full_name
    edit_user.role = role
    if password and password.strip():
        edit_user.hashed_password = _hp(password)
    await db.flush()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.delete("/users/{uid}", response_class=HTMLResponse)
async def user_delete(
    uid: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == uid))
    u = result.scalar_one_or_none()
    if u and u.id != user.id:
        await db.delete(u)
        await db.flush()
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/admin/users"})
    return RedirectResponse(url="/admin/users", status_code=303)


# ─── VESSELS ─────────────────────────────────────────────────
@router.get("/vessels/{vid}/edit", response_class=HTMLResponse)
async def vessel_edit_form(
    vid: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Vessel).where(Vessel.id == vid))
    vessel = result.scalar_one_or_none()
    if not vessel:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("admin/vessel_form.html", {
        "request": request, "user": user, "vessel": vessel,
    })


@router.post("/vessels/{vid}/edit", response_class=HTMLResponse)
async def vessel_edit_submit(
    vid: int, request: Request,
    name: str = Form(...),
    capacity_palettes: str = Form("0"),
    default_speed: str = Form("8"),
    default_elongation: str = Form("1.25"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Vessel).where(Vessel.id == vid))
    vessel = result.scalar_one_or_none()
    if not vessel:
        raise HTTPException(status_code=404)
    vessel.name = name
    vessel.capacity_palettes = int(pf(capacity_palettes, 0))
    vessel.default_speed = pf(default_speed, 8)
    vessel.default_elongation = pf(default_elongation, 1.25)
    await db.flush()
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/admin/settings"})
    return RedirectResponse(url="/admin/settings", status_code=303)


# ─── OPEX PARAMETER ──────────────────────────────────────────
@router.post("/opex/update", response_class=HTMLResponse)
async def opex_update(
    request: Request,
    opex_daily_rate: str = Form("11600"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OpexParameter).where(OpexParameter.parameter_name == "opex_daily_rate")
    )
    param = result.scalar_one_or_none()
    if param:
        param.parameter_value = pf(opex_daily_rate, 11600)
    else:
        param = OpexParameter(
            parameter_name="opex_daily_rate", parameter_value=pf(opex_daily_rate, 11600),
            unit="EUR/jour", category="global", description="Coût journalier en mer",
        )
        db.add(param)
    await db.flush()
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/admin/settings"})
    return RedirectResponse(url="/admin/settings", status_code=303)


# ─── LOCK/UNLOCK LEGS ────────────────────────────────────────
@router.post("/legs/lock", response_class=HTMLResponse)
async def lock_completed_legs(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lock all legs where ATD is set (voyage completed)."""
    result = await db.execute(select(Leg).where(Leg.atd != None, Leg.status != "completed"))
    legs = result.scalars().all()
    count = 0
    for leg in legs:
        leg.status = "completed"
        count += 1
    await db.flush()
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": f"/admin/settings?locked={count}"})
    return RedirectResponse(url="/admin/settings", status_code=303)


@router.post("/legs/{lid}/unlock", response_class=HTMLResponse)
async def unlock_leg(
    lid: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Leg).where(Leg.id == lid))
    leg = result.scalar_one_or_none()
    if leg:
        leg.status = "planned"
        await db.flush()
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/admin/settings"})
    return RedirectResponse(url="/admin/settings", status_code=303)


# ─── GLOBAL EXPORT ───────────────────────────────────────────
@router.get("/export/global", response_class=StreamingResponse)
async def export_global(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    legs_result = await db.execute(
        select(Leg).options(selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
        .order_by(Leg.year, Leg.vessel_id, Leg.sequence)
    )
    legs = legs_result.scalars().all()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Leg", "Navire", "Année", "Départ", "Arrivée",
        "ETD", "ETA", "ATD", "ATA",
        "Distance NM", "Durée jours", "Statut",
    ])
    for leg in legs:
        writer.writerow([
            leg.leg_code, leg.vessel.name, leg.year,
            f"{leg.departure_port.locode} {leg.departure_port.name}",
            f"{leg.arrival_port.locode} {leg.arrival_port.name}",
            leg.etd.strftime('%d/%m/%Y') if leg.etd else '',
            leg.eta.strftime('%d/%m/%Y') if leg.eta else '',
            leg.atd.strftime('%d/%m/%Y') if leg.atd else '',
            leg.ata.strftime('%d/%m/%Y') if leg.ata else '',
            leg.computed_distance or '', 
            round((leg.estimated_duration_hours or 0) / 24, 1),
            leg.status,
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=export_global_towt.csv"},
    )


# ─── USER LANGUAGE ────────────────────────────────────────────
@router.post("/settings/language", response_class=HTMLResponse)
async def update_language(
    request: Request,
    language: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.i18n import SUPPORTED_LANGUAGES
    if language in SUPPORTED_LANGUAGES:
        user.language = language
        await db.flush()
    url = "/admin/settings"
    response = RedirectResponse(url=url, status_code=303)
    response.set_cookie("towt_lang", language, max_age=365*24*3600)
    return response


# ─── CABIN PRICING GRID ──────────────────────────────────────
@router.post("/settings/pricing/add", response_class=HTMLResponse)
async def pricing_add(
    request: Request,
    origin_locode: str = Form(...),
    destination_locode: str = Form(...),
    cabin_type: str = Form(...),
    price: float = Form(...),
    deposit_pct: int = Form(30),
    notes: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.passenger import CabinPriceGrid
    entry = CabinPriceGrid(
        origin_locode=origin_locode.strip().upper(),
        destination_locode=destination_locode.strip().upper(),
        cabin_type=cabin_type,
        price=price,
        deposit_pct=deposit_pct,
        notes=notes.strip() or None,
    )
    db.add(entry)
    await db.flush()
    return RedirectResponse(url="/admin/settings#pricing", status_code=303)


@router.post("/settings/pricing/{price_id}/edit", response_class=HTMLResponse)
async def pricing_edit(
    price_id: int, request: Request,
    price: float = Form(...),
    deposit_pct: int = Form(30),
    notes: str = Form(""),
    is_active: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.passenger import CabinPriceGrid
    entry = await db.get(CabinPriceGrid, price_id)
    if entry:
        entry.price = price
        entry.deposit_pct = deposit_pct
        entry.notes = notes.strip() or None
        entry.is_active = is_active == "on"
        await db.flush()
    return RedirectResponse(url="/admin/settings#pricing", status_code=303)


@router.delete("/settings/pricing/{price_id}", response_class=HTMLResponse)
async def pricing_delete(
    price_id: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.passenger import CabinPriceGrid
    entry = await db.get(CabinPriceGrid, price_id)
    if entry:
        await db.delete(entry)
        await db.flush()
    return HTMLResponse("", status_code=200)
