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

ADMIN_ROLES = {"administrateur", "admin", "data_analyst"}


async def require_admin(user: User = Depends(get_current_user)):
    """Require admin or data_analyst role for settings access."""
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, detail="Admin access required")
    return user

from app.models.vessel import Vessel
from app.models.port import Port
from app.models.leg import Leg
from app.models.finance import OpexParameter, PortConfig
from app.models.emission_parameter import EmissionParameter
from app.models.co2_variable import Co2Variable, CO2_DEFAULTS
from app.models.mrv import MrvParameter, MRV_DEFAULTS
from app.utils.activity import log_activity

router = APIRouter(prefix="/admin", tags=["admin"])

USER_ROLES = [
    {"value": "administrateur", "label": "Administrateur"},
    {"value": "operation", "label": "Opération"},
    {"value": "armement", "label": "Armement / Équipage"},
    {"value": "technique", "label": "Technique"},
    {"value": "data_analyst", "label": "Data Analyst"},
    {"value": "marins", "label": "Marins"},
    {"value": "gestionnaire_passagers", "label": "Gestionnaire Passagers"},
    {"value": "commercial", "label": "Commercial"},
    {"value": "manager_maritime", "label": "Manager Maritime"},
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

    # Port count
    port_count_result = await db.execute(select(func.count(Port.id)))
    port_count = port_count_result.scalar() or 0
    port_msg = request.query_params.get("port_msg", "")

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

    # CO2 decarbonation variables (current values)
    co2_result = await db.execute(
        select(Co2Variable).where(Co2Variable.is_current == True).order_by(Co2Variable.variable_name)
    )
    co2_variables = co2_result.scalars().all()

    # CO2 history for TOWT CO2 EF (historized)
    co2_history_result = await db.execute(
        select(Co2Variable).where(Co2Variable.variable_name == "towt_co2_ef")
        .order_by(Co2Variable.effective_date.desc())
    )
    co2_history = co2_history_result.scalars().all()

    # MRV parameters
    mrv_result = await db.execute(select(MrvParameter).order_by(MrvParameter.parameter_name))
    mrv_params = mrv_result.scalars().all()

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
        "port_count": port_count,
        "port_msg": port_msg,
        "opex_params": opex_params,
        "emission_params": emission_params,
        "co2_variables": co2_variables,
        "co2_history": co2_history,
        "co2_defaults": CO2_DEFAULTS,
        "mrv_params": mrv_params,
        "mrv_defaults": MRV_DEFAULTS,
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
    await log_activity(db, user, "admin", "create", "User", new_user.id, f"Création utilisateur {username}")
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
    await log_activity(db, user, "admin", "update", "User", uid, f"Modification utilisateur {edit_user.username}")
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
        uname = u.username
        await db.delete(u)
        await db.flush()
        await log_activity(db, user, "admin", "delete", "User", uid, f"Suppression utilisateur {uname}")
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/admin/users"})
    return RedirectResponse(url="/admin/users", status_code=303)


# ─── VESSELS ─────────────────────────────────────────────────
@router.get("/vessels/create", response_class=HTMLResponse)
async def vessel_create_form(
    request: Request,
    user: User = Depends(get_current_user),
):
    return templates.TemplateResponse("admin/vessel_form.html", {
        "request": request, "user": user, "vessel": None,
    })


@router.post("/vessels/create", response_class=HTMLResponse)
async def vessel_create_submit(
    request: Request,
    name: str = Form(...),
    code: str = Form(...),
    imo_number: str = Form(""),
    flag: str = Form(""),
    dwt: str = Form(""),
    capacity_palettes: str = Form("0"),
    default_speed: str = Form("8"),
    default_elongation: str = Form("1.25"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    code_int = int(pf(code, 0))
    existing = await db.execute(select(Vessel).where(Vessel.code == code_int))
    if existing.scalar_one_or_none():
        return templates.TemplateResponse("admin/vessel_form.html", {
            "request": request, "user": user, "vessel": None,
            "error": f"Le code navire {code_int} existe déjà.",
        })
    vessel = Vessel(
        code=code_int,
        name=name.strip(),
        imo_number=imo_number.strip() or None,
        flag=flag.strip() or None,
        dwt=pf(dwt) or None,
        capacity_palettes=int(pf(capacity_palettes, 0)),
        default_speed=pf(default_speed, 8),
        default_elongation=pf(default_elongation, 1.25),
    )
    db.add(vessel)
    await db.flush()
    await log_activity(db, user, "admin", "create", "Vessel", vessel.id, f"Création navire {vessel.name}")
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/admin/settings"})
    return RedirectResponse(url="/admin/settings", status_code=303)


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
    imo_number: str = Form(""),
    flag: str = Form(""),
    dwt: str = Form(""),
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
    vessel.imo_number = imo_number.strip() or None
    vessel.flag = flag.strip() or None
    vessel.dwt = pf(dwt) or None
    vessel.capacity_palettes = int(pf(capacity_palettes, 0))
    vessel.default_speed = pf(default_speed, 8)
    vessel.default_elongation = pf(default_elongation, 1.25)
    await db.flush()
    await log_activity(db, user, "admin", "update", "Vessel", vid, f"Modification navire {vessel.name}")
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/admin/settings"})
    return RedirectResponse(url="/admin/settings", status_code=303)


@router.delete("/vessels/{vid}", response_class=HTMLResponse)
async def vessel_delete(
    vid: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Vessel).where(Vessel.id == vid))
    vessel = result.scalar_one_or_none()
    if not vessel:
        raise HTTPException(status_code=404)
    leg_count_result = await db.execute(select(func.count(Leg.id)).where(Leg.vessel_id == vid))
    leg_count = leg_count_result.scalar() or 0
    if leg_count > 0:
        return HTMLResponse(
            content=f"<div class='toast toast-error'>Impossible : {leg_count} legs associés</div>",
            status_code=400,
        )
    vname = vessel.name
    await db.delete(vessel)
    await db.flush()
    await log_activity(db, user, "admin", "delete", "Vessel", vid, f"Suppression navire {vname}")
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
    await log_activity(db, user, "admin", "update_opex", "OpexParameter", None, f"OPEX → {pf(opex_daily_rate, 11600)} €/j")
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
    await log_activity(db, user, "admin", "lock_legs", None, None, f"Verrouillage {count} legs terminés")
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
        await log_activity(db, user, "admin", "unlock_leg", "Leg", lid, f"Déverrouillage leg {leg.leg_code}")
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
        await log_activity(db, user, "admin", "update_language", "User", user.id, f"Langue → {language}")
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
    await log_activity(db, user, "admin", "create", "CabinPricing", entry.id, f"Tarif cabine {cabin_type} {origin_locode}→{destination_locode}")
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
        await log_activity(db, user, "admin", "update", "CabinPricing", price_id, f"Modification tarif cabine")
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
        await log_activity(db, user, "admin", "delete", "CabinPricing", price_id, "Suppression tarif cabine")
    return HTMLResponse("", status_code=200)


# ─── PORT IMPORT ──────────────────────────────────────────────
@router.post("/ports/import", response_class=HTMLResponse)
async def import_ports(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import httpx
    url = "https://service.unece.org/trade/locode/loc242csv.zip"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return RedirectResponse(url="/admin/settings?port_msg=Erreur téléchargement UN/LOCODE", status_code=303)

        import zipfile
        zip_buffer = io.BytesIO(resp.content)
        with zipfile.ZipFile(zip_buffer) as zf:
            csv_files = [n for n in zf.namelist() if n.endswith(".csv")]
            if not csv_files:
                return RedirectResponse(url="/admin/settings?port_msg=Aucun CSV dans le ZIP", status_code=303)

            imported = 0
            for csv_name in csv_files:
                with zf.open(csv_name) as f:
                    import codecs
                    reader = csv.reader(codecs.iterdecode(f, "latin-1"))
                    for row in reader:
                        if len(row) < 8:
                            continue
                        country = row[1].strip() if row[1] else ""
                        location = row[2].strip() if row[2] else ""
                        name = row[3].strip() if row[3] else ""
                        if not country or not location or not name:
                            continue
                        locode = f"{country}{location}"
                        func_code = row[6].strip() if len(row) > 6 else ""
                        if "1" not in func_code and "2" not in func_code and "3" not in func_code:
                            continue
                        existing = await db.execute(select(Port).where(Port.locode == locode))
                        if existing.scalar_one_or_none():
                            continue
                        coords = row[10].strip() if len(row) > 10 else ""
                        lat, lon = None, None
                        if coords:
                            parts = coords.split()
                            if len(parts) == 2:
                                try:
                                    lat_str, lon_str = parts
                                    lat_deg = float(lat_str[:2]) + float(lat_str[2:4]) / 60
                                    if lat_str[-1] == "S":
                                        lat_deg = -lat_deg
                                    lon_deg = float(lon_str[:3]) + float(lon_str[3:5]) / 60
                                    if lon_str[-1] == "W":
                                        lon_deg = -lon_deg
                                    lat, lon = round(lat_deg, 4), round(lon_deg, 4)
                                except (ValueError, IndexError):
                                    pass
                        port = Port(
                            locode=locode,
                            name=name,
                            country=country,
                            latitude=lat,
                            longitude=lon,
                        )
                        db.add(port)
                        imported += 1
            await db.flush()
            await log_activity(db, user, "admin", "import_ports", None, None, f"Import {imported} ports UN/LOCODE")
            msg = f"Import terminé : {imported} nouveaux ports ajoutés"
    except Exception as e:
        msg = f"Erreur import : {str(e)}"

    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": f"/admin/settings?port_msg={msg}"})
    return RedirectResponse(url=f"/admin/settings?port_msg={msg}", status_code=303)


# ─── CO2 DECARBONATION VARIABLES ─────────────────────────────
@router.post("/co2/update", response_class=HTMLResponse)
async def co2_update(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    from datetime import date as _date

    for var_name, defaults in CO2_DEFAULTS.items():
        val_str = form.get(f"co2_{var_name}", "")
        val = pf(val_str, defaults["value"])

        # Get current entry
        result = await db.execute(
            select(Co2Variable).where(
                Co2Variable.variable_name == var_name,
                Co2Variable.is_current == True
            )
        )
        current = result.scalar_one_or_none()

        if current:
            # For towt_co2_ef, historize: keep old entry, create new
            if var_name == "towt_co2_ef" and abs(current.variable_value - val) > 0.0001:
                current.is_current = False
                new_entry = Co2Variable(
                    variable_name=var_name,
                    variable_value=val,
                    unit=defaults["unit"],
                    description=defaults["description"],
                    effective_date=_date.today(),
                    is_current=True,
                )
                db.add(new_entry)
            else:
                current.variable_value = val
        else:
            entry = Co2Variable(
                variable_name=var_name,
                variable_value=val,
                unit=defaults["unit"],
                description=defaults["description"],
                effective_date=_date.today(),
                is_current=True,
            )
            db.add(entry)

    await db.flush()
    await log_activity(db, user, "admin", "update_co2", None, None, "Mise à jour variables décarbonation")
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/admin/settings"})
    return RedirectResponse(url="/admin/settings", status_code=303)


# ─── MRV PARAMETERS ─────────────────────────────────────────
@router.post("/mrv/update", response_class=HTMLResponse)
async def mrv_params_update(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()

    for param_name, defaults in MRV_DEFAULTS.items():
        val_str = form.get(f"mrv_{param_name}", "")
        val = pf(val_str, defaults["value"])

        result = await db.execute(
            select(MrvParameter).where(MrvParameter.parameter_name == param_name)
        )
        param = result.scalar_one_or_none()
        if param:
            param.parameter_value = val
        else:
            param = MrvParameter(
                parameter_name=param_name,
                parameter_value=val,
                unit=defaults["unit"],
                description=defaults["description"],
            )
            db.add(param)

    await db.flush()
    await log_activity(db, user, "admin", "update_mrv", None, None, "Mise à jour paramètres MRV")
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/admin/settings"})
    return RedirectResponse(url="/admin/settings", status_code=303)


# ─── EMISSION PARAMETERS UPDATE ──────────────────────────────
@router.post("/emissions/update", response_class=HTMLResponse)
async def emissions_update(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    from app.routers.kpi_router import DEFAULTS as KPI_DEFAULTS

    for param_name, default_val in KPI_DEFAULTS.items():
        val_str = form.get(f"em_{param_name}", "")
        val = pf(val_str, default_val)

        result = await db.execute(
            select(EmissionParameter).where(EmissionParameter.parameter_name == param_name)
        )
        param = result.scalar_one_or_none()
        if param:
            param.parameter_value = val
        else:
            param = EmissionParameter(
                parameter_name=param_name,
                parameter_value=val,
                unit="",
                description=param_name,
            )
            db.add(param)

    await db.flush()
    await log_activity(db, user, "admin", "update_emissions", None, None, "Mise à jour paramètres émissions KPI")
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/admin/settings"})
    return RedirectResponse(url="/admin/settings", status_code=303)


# ─── ACTIVITY LOG ───────────────────────────────────────────
@router.get("/activity-log", response_class=HTMLResponse)
async def activity_log_page(
    request: Request,
    module: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    page: int = Query(1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.activity import ActivityLog
    PAGE_SIZE = 50
    query = select(ActivityLog).order_by(ActivityLog.timestamp.desc())
    if module:
        query = query.where(ActivityLog.module == module)
    if username:
        query = query.where(ActivityLog.username.ilike(f"%{username}%"))

    count_q = select(func.count(ActivityLog.id))
    if module:
        count_q = count_q.where(ActivityLog.module == module)
    if username:
        count_q = count_q.where(ActivityLog.username.ilike(f"%{username}%"))
    total = (await db.execute(count_q)).scalar() or 0

    offset = (page - 1) * PAGE_SIZE
    result = await db.execute(query.offset(offset).limit(PAGE_SIZE))
    entries = result.scalars().all()
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    modules_result = await db.execute(
        select(ActivityLog.module).distinct().order_by(ActivityLog.module)
    )
    modules = [r[0] for r in modules_result.all()]

    return templates.TemplateResponse("admin/activity_log.html", {
        "request": request, "user": user,
        "entries": entries,
        "modules": modules,
        "selected_module": module,
        "search_username": username or "",
        "page": page, "total_pages": total_pages, "total": total,
        "active_module": "settings",
    })


@router.get("/activity-log/export/csv", response_class=StreamingResponse)
async def activity_log_export(
    module: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.activity import ActivityLog
    query = select(ActivityLog).order_by(ActivityLog.timestamp.desc())
    if module:
        query = query.where(ActivityLog.module == module)
    result = await db.execute(query.limit(5000))
    entries = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Date/Heure", "Utilisateur", "Module", "Action", "Type", "ID", "Détail"])
    for e in entries:
        writer.writerow([
            e.timestamp.strftime("%d/%m/%Y %H:%M") if e.timestamp else "",
            e.username or "", e.module or "", e.action or "",
            e.resource_type or "", e.resource_id or "", e.detail or "",
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=activity_log_towt.csv"},
    )
