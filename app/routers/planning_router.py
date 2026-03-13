from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from app.templating import templates
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.activity import log_activity, get_client_ip
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime, timedelta, timezone
import csv
import io
import math

from app.database import get_db
from app.auth import get_current_user, AuthRequired
from app.permissions import require_permission
from app.models.user import User
from app.models.vessel import Vessel
from app.models.leg import Leg, LegStatus
from app.models.port import Port

router = APIRouter(prefix="/planning", tags=["planning"])

# ─── DEFAULTS ─────────────────────────────────────────────────
DEFAULT_SPEED = 8.0        # knots
DEFAULT_ELONGATION = 1.25
DEFAULT_PORT_STAY_DAYS = 3  # days between arrival and next departure


def parse_float(val, default=None):
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def parse_int(val, default=None):
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def parse_datetime(val):
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return None
    try:
        return datetime.fromisoformat(val)
    except (ValueError, TypeError):
        return None


def haversine_nm(lat1, lon1, lat2, lon2):
    """Calculate orthodromic distance in nautical miles."""
    if not all([lat1, lon1, lat2, lon2]):
        return None
    R_nm = 3440.065
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return round(R_nm * c, 1)


def compute_eta(etd, distance_nm, speed, elongation):
    """Compute ETA from ETD + navigation parameters."""
    if not etd or not distance_nm or not speed or speed <= 0:
        return None
    real_distance = distance_nm * elongation
    duration_hours = real_distance / speed
    return etd + timedelta(hours=duration_hours)


def compute_navigation_duration(distance_nm, speed, elongation):
    """Return duration in hours."""
    if not distance_nm or not speed or speed <= 0:
        return None
    return round((distance_nm * elongation) / speed, 1)


async def get_next_sequence(db: AsyncSession, vessel_id: int, year: int) -> int:
    result = await db.execute(
        select(func.max(Leg.sequence)).where(Leg.vessel_id == vessel_id, Leg.year == year)
    )
    return (result.scalar() or 0) + 1


async def get_previous_leg(db: AsyncSession, vessel_id: int, year: int, current_sequence: int):
    """Get the leg just before this sequence."""
    result = await db.execute(
        select(Leg)
        .where(Leg.vessel_id == vessel_id, Leg.year == year, Leg.sequence < current_sequence)
        .order_by(Leg.sequence.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def resequence_and_recalc(db: AsyncSession, vessel_id: int, year: int):
    """Resequence all legs for a vessel/year by ETD, update codes, and recalculate dates chain."""
    result = await db.execute(
        select(Leg)
        .options(selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
        .where(Leg.vessel_id == vessel_id, Leg.year == year)
        .order_by(Leg.etd.asc().nulls_last(), Leg.id.asc())
    )
    legs = result.scalars().all()

    # First pass: set temporary unique codes to avoid UNIQUE constraint violations
    # when reordering causes leg_code swaps (e.g. leg A gets B's old code before B is updated)
    for leg in legs:
        leg.leg_code = f"_RESEQ_{leg.id}"
    await db.flush()

    for i, leg in enumerate(legs):
        leg.sequence = i + 1
        # Update leg code
        leg.leg_code = leg.generate_leg_code(
            vessel_code=leg.vessel.code,
            dep_country=leg.departure_port.country_code,
            arr_country=leg.arrival_port.country_code,
        )
        # Recalculate dates chain (skip first leg - its ETD is manual)
        if i > 0:
            prev_leg = legs[i - 1]
            prev_eta = prev_leg.ata or prev_leg.eta  # Use actual if available
            if prev_eta and not leg.atd:
                # ETD = previous ETA + port stay duration
                leg.etd = prev_eta + timedelta(days=leg.port_stay_days or DEFAULT_PORT_STAY_DAYS)

        # Recalculate ETA from ETD
        if leg.etd and leg.distance_nm and not leg.ata:
            speed = leg.speed_knots or DEFAULT_SPEED
            elong = leg.elongation_coeff or DEFAULT_ELONGATION
            leg.eta = compute_eta(leg.etd, leg.distance_nm, speed, elong)
            leg.computed_distance = round(leg.distance_nm * elong, 1)
            leg.estimated_duration_hours = compute_navigation_duration(leg.distance_nm, speed, elong)

    await db.flush()


async def propagate_delays(db: AsyncSession, vessel_id: int, year: int):
    """When actual dates set, propagate to subsequent legs."""
    await resequence_and_recalc(db, vessel_id, year)


# ─── PLANNING HOME ────────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
async def planning_home(
    request: Request,
    vessel: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    user: User = Depends(require_permission("planning", "C")),
    db: AsyncSession = Depends(get_db),
):
    current_year = year or datetime.now().year
    years = list(range(2025, datetime.now().year + 2))

    vessels_result = await db.execute(select(Vessel).where(Vessel.is_active == True).order_by(Vessel.code))
    vessels = vessels_result.scalars().all()

    selected_vessel = vessel or (vessels[0].code if vessels else None)

    vessel_obj = None
    if selected_vessel:
        v_result = await db.execute(select(Vessel).where(Vessel.code == selected_vessel))
        vessel_obj = v_result.scalar_one_or_none()

    legs = []
    if vessel_obj:
        legs_result = await db.execute(
            select(Leg)
            .options(selectinload(Leg.departure_port), selectinload(Leg.arrival_port), selectinload(Leg.vessel))
            .where(Leg.vessel_id == vessel_obj.id, Leg.year == current_year)
            .order_by(Leg.sequence.asc())
        )
        legs = legs_result.scalars().all()

    # Auto-update status based on dates
    now = datetime.now(timezone.utc)
    status_changed = False
    for leg in legs:
        if leg.status == "completed":
            continue  # locked
        if leg.atd:
            # Departed = completed
            if leg.status != "completed":
                leg.status = "completed"
                status_changed = True
        elif leg.ata or (leg.eta and leg.eta <= now and not leg.atd):
            # Arrived or ETA passed = in_progress
            if leg.status != "in_progress":
                leg.status = "in_progress"
                status_changed = True
        elif leg.etd and leg.etd <= now and not leg.ata:
            # Departed (ETD passed) but no ATA = in_progress (en mer)
            if leg.status != "in_progress":
                leg.status = "in_progress"
                status_changed = True
        else:
            if leg.status not in ("planned", "in_progress"):
                leg.status = "planned"
                status_changed = True
    if status_changed:
        await db.flush()

    return templates.TemplateResponse("planning/index.html", {
        "request": request,
        "user": user,
        "vessels": vessels,
        "selected_vessel": selected_vessel,
        "vessel_obj": vessel_obj,
        "current_year": current_year,
        "years": years,
        "legs": legs,
        "active_module": "planning",
    })


# ─── PORT CONFLICTS ───────────────────────────────────────────
@router.get("/ports", response_class=HTMLResponse)
async def port_conflicts(
    request: Request,
    port: Optional[str] = Query(None),
    user: User = Depends(require_permission("planning", "C")),
    db: AsyncSession = Depends(get_db),
):
    port_obj = None
    legs_at_port = []
    if port:
        p_result = await db.execute(select(Port).where(Port.locode == port.upper()))
        port_obj = p_result.scalar_one_or_none()
        if port_obj:
            legs_result = await db.execute(
                select(Leg)
                .options(selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
                .where(or_(
                    Leg.departure_port_locode == port_obj.locode,
                    Leg.arrival_port_locode == port_obj.locode,
                ))
                .order_by(Leg.eta.asc().nulls_last())
            )
            legs_at_port = legs_result.scalars().all()

    return templates.TemplateResponse("planning/port_conflicts.html", {
        "request": request,
        "user": user,
        "port": port_obj,
        "port_code": port or "",
        "legs_at_port": legs_at_port,
        "active_module": "planning",
    })


# ─── CREATE LEG FORM ─────────────────────────────────────────
@router.get("/legs/create", response_class=HTMLResponse)
async def leg_create_form(
    request: Request,
    vessel: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    user: User = Depends(require_permission("planning", "M")),
    db: AsyncSession = Depends(get_db),
):
    vessels_result = await db.execute(select(Vessel).where(Vessel.is_active == True).order_by(Vessel.code))
    shortcuts_result = await db.execute(select(Port).where(Port.is_shortcut == True).order_by(Port.locode))

    # Check if this is the first leg (needs manual ETD)
    vessel_obj = None
    is_first_leg = True
    prev_eta_str = ""
    if vessel:
        v_r = await db.execute(select(Vessel).where(Vessel.code == vessel))
        vessel_obj = v_r.scalar_one_or_none()
        if vessel_obj:
            yr = year or datetime.now().year
            count = await db.execute(
                select(func.count(Leg.id)).where(Leg.vessel_id == vessel_obj.id, Leg.year == yr)
            )
            is_first_leg = (count.scalar() or 0) == 0
            if not is_first_leg:
                # Get last leg's ETA to show as info
                last = await db.execute(
                    select(Leg).where(Leg.vessel_id == vessel_obj.id, Leg.year == yr)
                    .order_by(Leg.sequence.desc()).limit(1)
                )
                last_leg = last.scalar_one_or_none()
                if last_leg and (last_leg.ata or last_leg.eta):
                    prev_date = last_leg.ata or last_leg.eta
                    prev_eta_str = prev_date.strftime('%d/%m/%Y %H:%M')

    # Get last leg info for pre-fill
    last_arr_locode = ""
    last_arr_name = ""
    computed_etd_str = ""
    if vessel_obj:
        yr = year or datetime.now().year
        last_result = await db.execute(
            select(Leg).options(selectinload(Leg.arrival_port))
            .where(Leg.vessel_id == vessel_obj.id, Leg.year == yr)
            .order_by(Leg.sequence.desc()).limit(1)
        )
        last_leg = last_result.scalar_one_or_none()
        if last_leg:
            last_arr_locode = last_leg.arrival_port_locode
            last_arr_name = last_leg.arrival_port.name if last_leg.arrival_port else ""
            prev_date = last_leg.ata or last_leg.eta
            if prev_date:
                prev_eta_str = prev_date.strftime('%d/%m/%Y %H:%M')
                computed_etd = prev_date + timedelta(days=DEFAULT_PORT_STAY_DAYS)
                computed_etd_str = computed_etd.strftime('%Y-%m-%dT%H:%M')

    return templates.TemplateResponse("planning/leg_form.html", {
        "request": request,
        "user": user,
        "vessels": vessels_result.scalars().all(),
        "shortcuts": shortcuts_result.scalars().all(),
        "edit_leg": None,
        "selected_vessel": vessel,
        "current_year": year or datetime.now().year,
        "is_first_leg": is_first_leg,
        "prev_eta_str": prev_eta_str,
        "last_arr_locode": last_arr_locode,
        "last_arr_name": last_arr_name,
        "computed_etd_str": computed_etd_str,
        "default_speed": DEFAULT_SPEED,
        "default_elongation": DEFAULT_ELONGATION,
        "default_port_stay": DEFAULT_PORT_STAY_DAYS,
        "error": None,
    })


# ─── CREATE LEG SUBMIT ───────────────────────────────────────
@router.post("/legs/create", response_class=HTMLResponse)
async def leg_create_submit(
    request: Request,
    vessel_id: str = Form(...),
    year: str = Form(...),
    departure_port: str = Form(...),
    arrival_port: str = Form(...),
    etd: Optional[str] = Form(None),
    speed_knots: Optional[str] = Form(None),
    elongation_coeff: Optional[str] = Form(None),
    port_stay_days: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    user: User = Depends(require_permission("planning", "M")),
    db: AsyncSession = Depends(get_db),
):
    _vessel_id = parse_int(vessel_id)
    _year = parse_int(year, datetime.now().year)
    _speed = parse_float(speed_knots, DEFAULT_SPEED)
    _elongation = parse_float(elongation_coeff, DEFAULT_ELONGATION)
    _port_stay = parse_int(port_stay_days, DEFAULT_PORT_STAY_DAYS)
    _etd = parse_datetime(etd)

    # Validate ports
    dep_result = await db.execute(select(Port).where(Port.locode == departure_port.strip().upper()))
    dep_port = dep_result.scalar_one_or_none()
    arr_result = await db.execute(select(Port).where(Port.locode == arrival_port.strip().upper()))
    arr_port = arr_result.scalar_one_or_none()

    if not dep_port or not arr_port:
        vessels_result = await db.execute(select(Vessel).where(Vessel.is_active == True))
        shortcuts_result = await db.execute(select(Port).where(Port.is_shortcut == True))
        return templates.TemplateResponse("planning/leg_form.html", {
            "request": request, "user": user,
            "vessels": vessels_result.scalars().all(),
            "shortcuts": shortcuts_result.scalars().all(),
            "edit_leg": None, "selected_vessel": _vessel_id, "current_year": _year,
            "is_first_leg": True, "prev_eta_str": "",
            "default_speed": DEFAULT_SPEED, "default_elongation": DEFAULT_ELONGATION,
            "default_port_stay": DEFAULT_PORT_STAY_DAYS,
            "error": f"Port invalide: {departure_port if not dep_port else arrival_port}",
        })

    # Get vessel
    v_result = await db.execute(select(Vessel).where(Vessel.id == _vessel_id))
    vessel_obj = v_result.scalar_one_or_none()
    if not vessel_obj:
        raise HTTPException(status_code=404, detail="Navire non trouvé")

    # Get sequence
    sequence = await get_next_sequence(db, _vessel_id, _year)

    # Calculate distance
    distance = haversine_nm(dep_port.latitude, dep_port.longitude, arr_port.latitude, arr_port.longitude)

    # If not first leg, compute ETD from previous leg's ETA + port stay
    if not _etd and sequence > 1:
        prev_leg = await get_previous_leg(db, _vessel_id, _year, sequence)
        if prev_leg:
            prev_eta = prev_leg.ata or prev_leg.eta
            if prev_eta:
                _etd = prev_eta + timedelta(days=_port_stay)

    # Compute ETA
    _eta = compute_eta(_etd, distance, _speed, _elongation) if _etd and distance else None
    _computed_dist = round(distance * _elongation, 1) if distance else None
    _duration = compute_navigation_duration(distance, _speed, _elongation) if distance else None

    leg = Leg(
        vessel_id=_vessel_id,
        year=_year,
        sequence=sequence,
        departure_port_locode=dep_port.locode,
        arrival_port_locode=arr_port.locode,
        etd=_etd,
        eta=_eta,
        distance_nm=distance,
        speed_knots=_speed,
        elongation_coeff=_elongation,
        computed_distance=_computed_dist,
        estimated_duration_hours=_duration,
        port_stay_days=_port_stay,
        notes=notes if notes and notes.strip() else None,
        leg_code="TEMP",
    )
    leg.leg_code = leg.generate_leg_code(
        vessel_code=vessel_obj.code,
        dep_country=dep_port.country_code,
        arr_country=arr_port.country_code,
    )

    db.add(leg)
    await db.flush()

    await log_activity(db, user=user, action="create", module="planning",
                       entity_type="leg", entity_id=leg.id,
                       entity_label=leg.leg_code,
                       detail=f"{leg.departure_port_locode} → {leg.arrival_port_locode}",
                       ip_address=get_client_ip(request))

    # Resequence all legs
    await resequence_and_recalc(db, _vessel_id, _year)

    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": f"/planning?vessel={vessel_obj.code}&year={_year}"})
    return RedirectResponse(url=f"/planning?vessel={vessel_obj.code}&year={_year}", status_code=303)


# ─── EDIT LEG FORM ───────────────────────────────────────────
@router.get("/legs/{leg_id}/edit", response_class=HTMLResponse)
async def leg_edit_form(
    leg_id: int,
    request: Request,
    user: User = Depends(require_permission("planning", "M")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Leg).options(selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
        .where(Leg.id == leg_id)
    )
    leg = result.scalar_one_or_none()
    if not leg:
        raise HTTPException(status_code=404)

    vessels_result = await db.execute(select(Vessel).where(Vessel.is_active == True).order_by(Vessel.code))
    shortcuts_result = await db.execute(select(Port).where(Port.is_shortcut == True).order_by(Port.locode))

    return templates.TemplateResponse("planning/leg_form.html", {
        "request": request, "user": user,
        "vessels": vessels_result.scalars().all(),
        "shortcuts": shortcuts_result.scalars().all(),
        "edit_leg": leg,
        "selected_vessel": leg.vessel.code,
        "current_year": leg.year,
        "is_first_leg": leg.sequence == 1,
        "prev_eta_str": "",
        "default_speed": DEFAULT_SPEED, "default_elongation": DEFAULT_ELONGATION,
        "default_port_stay": DEFAULT_PORT_STAY_DAYS,
        "error": None,
    })


# ─── EDIT LEG SUBMIT ────────────────────────────────────────
@router.post("/legs/{leg_id}/edit", response_class=HTMLResponse)
async def leg_edit_submit(
    leg_id: int,
    request: Request,
    vessel_id: str = Form(...),
    year: str = Form(...),
    departure_port: str = Form(...),
    arrival_port: str = Form(...),
    etd: Optional[str] = Form(None),
    eta: Optional[str] = Form(None),
    ata: Optional[str] = Form(None),
    atd: Optional[str] = Form(None),
    speed_knots: Optional[str] = Form(None),
    elongation_coeff: Optional[str] = Form(None),
    port_stay_days: Optional[str] = Form(None),
    status: str = Form("planned"),
    notes: Optional[str] = Form(None),
    user: User = Depends(require_permission("planning", "M")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Leg).where(Leg.id == leg_id))
    leg = result.scalar_one_or_none()
    if not leg:
        raise HTTPException(status_code=404)

    _vessel_id = parse_int(vessel_id)
    _year = parse_int(year)

    dep_result = await db.execute(select(Port).where(Port.locode == departure_port.strip().upper()))
    dep_port = dep_result.scalar_one_or_none()
    arr_result = await db.execute(select(Port).where(Port.locode == arrival_port.strip().upper()))
    arr_port = arr_result.scalar_one_or_none()

    if not dep_port or not arr_port:
        vessels_result = await db.execute(select(Vessel).where(Vessel.is_active == True))
        shortcuts_result = await db.execute(select(Port).where(Port.is_shortcut == True))
        return templates.TemplateResponse("planning/leg_form.html", {
            "request": request, "user": user,
            "vessels": vessels_result.scalars().all(),
            "shortcuts": shortcuts_result.scalars().all(),
            "edit_leg": leg, "selected_vessel": _vessel_id, "current_year": _year,
            "is_first_leg": leg.sequence == 1, "prev_eta_str": "",
            "default_speed": DEFAULT_SPEED, "default_elongation": DEFAULT_ELONGATION,
            "default_port_stay": DEFAULT_PORT_STAY_DAYS,
            "error": "Port invalide.",
        })

    v_result = await db.execute(select(Vessel).where(Vessel.id == _vessel_id))
    vessel_obj = v_result.scalar_one_or_none()

    old_vessel_id = leg.vessel_id
    old_year = leg.year

    _speed = parse_float(speed_knots, DEFAULT_SPEED)
    _elongation = parse_float(elongation_coeff, DEFAULT_ELONGATION)
    _port_stay = parse_int(port_stay_days, DEFAULT_PORT_STAY_DAYS)

    leg.vessel_id = _vessel_id
    leg.year = _year
    leg.departure_port_locode = dep_port.locode
    leg.arrival_port_locode = arr_port.locode
    leg.etd = parse_datetime(etd)
    leg.eta = parse_datetime(eta)
    leg.ata = parse_datetime(ata)
    leg.atd = parse_datetime(atd)
    leg.speed_knots = _speed
    leg.elongation_coeff = _elongation
    leg.port_stay_days = _port_stay
    leg.status = status
    leg.notes = notes if notes and notes.strip() else None

    # Recalculate distance
    leg.distance_nm = haversine_nm(dep_port.latitude, dep_port.longitude, arr_port.latitude, arr_port.longitude)
    if leg.distance_nm:
        leg.computed_distance = round(leg.distance_nm * _elongation, 1)
        leg.estimated_duration_hours = compute_navigation_duration(leg.distance_nm, _speed, _elongation)

    # If ETD set but not ETA, recalculate
    if leg.etd and not leg.eta and leg.distance_nm:
        leg.eta = compute_eta(leg.etd, leg.distance_nm, _speed, _elongation)

    await db.flush()

    # Resequence and recalculate chain
    await resequence_and_recalc(db, _vessel_id, _year)
    if old_vessel_id != _vessel_id or old_year != _year:
        await resequence_and_recalc(db, old_vessel_id, old_year)

    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": f"/planning?vessel={vessel_obj.code}&year={_year}"})
    return RedirectResponse(url=f"/planning?vessel={vessel_obj.code}&year={_year}", status_code=303)


# ─── DELETE LEG ──────────────────────────────────────────────
@router.delete("/legs/{leg_id}", response_class=HTMLResponse)
async def leg_delete(
    leg_id: int,
    request: Request,
    user: User = Depends(require_permission("planning", "S")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Leg).options(selectinload(Leg.vessel)).where(Leg.id == leg_id))
    leg = result.scalar_one_or_none()
    if not leg:
        raise HTTPException(status_code=404)

    vessel_code = leg.vessel.code
    vessel_id = leg.vessel_id
    year = leg.year
    leg_code = leg.leg_code

    await log_activity(db, user=user, action="delete", module="planning",
                       entity_type="leg", entity_id=leg_id, entity_label=leg_code,
                       ip_address=get_client_ip(request))

    await db.delete(leg)
    await db.flush()
    await resequence_and_recalc(db, vessel_id, year)

    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": f"/planning?vessel={vessel_code}&year={year}"})
    return RedirectResponse(url=f"/planning?vessel={vessel_code}&year={year}", status_code=303)


# ─── EXPORT CSV ──────────────────────────────────────────────
@router.get("/export/csv", response_class=StreamingResponse)
async def export_csv(
    vessel: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    user: User = Depends(require_permission("planning", "C")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Leg).options(
        selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port)
    )
    if vessel:
        v_result = await db.execute(select(Vessel).where(Vessel.code == vessel))
        v = v_result.scalar_one_or_none()
        if v:
            query = query.where(Leg.vessel_id == v.id)
    if year:
        query = query.where(Leg.year == year)

    result = await db.execute(query.order_by(Leg.vessel_id, Leg.sequence))
    legs = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Leg Code", "Navire", "Départ LOCODE", "Port Départ", "Arrivée LOCODE", "Port Arrivée",
        "ETD", "ETA", "ATD (réel)", "ATA (réel)",
        "Distance Ortho (NM)", "Distance Réelle (NM)", "Vitesse (nds)", "Durée Est. (h)", "Statut"
    ])
    for leg in legs:
        writer.writerow([
            leg.leg_code, leg.vessel.name,
            leg.departure_port.locode, leg.departure_port.name,
            leg.arrival_port.locode, leg.arrival_port.name,
            leg.etd.strftime("%d/%m/%Y %H:%M") if leg.etd else "",
            leg.eta.strftime("%d/%m/%Y %H:%M") if leg.eta else "",
            leg.atd.strftime("%d/%m/%Y %H:%M") if leg.atd else "",
            leg.ata.strftime("%d/%m/%Y %H:%M") if leg.ata else "",
            leg.distance_nm or "", leg.computed_distance or "",
            leg.speed_knots or "", leg.estimated_duration_hours or "", leg.status,
        ])

    output.seek(0)
    filename = f"planning_towt_{vessel or 'all'}_{year or 'all'}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─── GANTT DATA (JSON) ──────────────────────────────────────
@router.get("/api/gantt")
async def gantt_data(
    vessel: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    user: User = Depends(require_permission("planning", "C")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Leg).options(
        selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port)
    )
    if vessel:
        v_result = await db.execute(select(Vessel).where(Vessel.code == vessel))
        v = v_result.scalar_one_or_none()
        if v:
            query = query.where(Leg.vessel_id == v.id)
    if year:
        query = query.where(Leg.year == year)

    result = await db.execute(query.order_by(Leg.vessel_id, Leg.sequence))
    legs = result.scalars().all()

    return [
        {
            "id": leg.id,
            "code": leg.leg_code,
            "vessel": leg.vessel.name,
            "vessel_code": leg.vessel.code,
            "dep_port": leg.departure_port.name,
            "dep_locode": leg.departure_port.locode,
            "arr_port": leg.arrival_port.name,
            "arr_locode": leg.arrival_port.locode,
            "etd": leg.etd.isoformat() if leg.etd else None,
            "eta": leg.eta.isoformat() if leg.eta else None,
            "atd": leg.atd.isoformat() if leg.atd else None,
            "ata": leg.ata.isoformat() if leg.ata else None,
            "status": leg.status,
            "duration_hours": leg.estimated_duration_hours,
        }
        for leg in legs
    ]


# ─── MAP DATA (JSON with port coordinates) ───────────────────
@router.get("/api/map")
async def map_data(
    vessel: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    user: User = Depends(require_permission("planning", "C")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Leg).options(
        selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port)
    )
    if vessel:
        v_result = await db.execute(select(Vessel).where(Vessel.code == vessel))
        v = v_result.scalar_one_or_none()
        if v:
            query = query.where(Leg.vessel_id == v.id)
    if year:
        query = query.where(Leg.year == year)

    result = await db.execute(query.order_by(Leg.vessel_id, Leg.sequence))
    legs = result.scalars().all()

    return [
        {
            "id": leg.id,
            "code": leg.leg_code,
            "vessel": leg.vessel.name,
            "vessel_code": leg.vessel.code,
            "dep_locode": leg.departure_port.locode,
            "dep_lat": leg.departure_port.latitude,
            "dep_lon": leg.departure_port.longitude,
            "arr_locode": leg.arrival_port.locode,
            "arr_lat": leg.arrival_port.latitude,
            "arr_lon": leg.arrival_port.longitude,
            "status": leg.status,
        }
        for leg in legs
        if leg.departure_port.latitude and leg.arrival_port.latitude
    ]


# ─── PDF COMMERCIAL ──────────────────────────────────────────
@router.get("/pdf/commercial", response_class=HTMLResponse)
async def pdf_commercial(
    request: Request,
    template: Optional[str] = Query("all"),
    vessel: Optional[str] = Query(None),
    destination: Optional[str] = Query(None),
    origin: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    lang: Optional[str] = Query("fr"),
    legs_ids: Optional[str] = Query(None),
    user: User = Depends(require_permission("planning", "C")),
    db: AsyncSession = Depends(get_db),
):
    """Generate printable commercial support PDF (HTML → print)."""
    from datetime import timezone as tz
    current_year = year or datetime.now().year
    # Parse vessel code (can be int code or empty string)
    vessel_code = int(vessel) if vessel and vessel.strip() else None

    vessels_result = await db.execute(select(Vessel).where(Vessel.is_active == True).order_by(Vessel.code))
    vessels = vessels_result.scalars().all()

    # Build query
    query = (
        select(Leg)
        .options(selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
        .where(Leg.year == current_year, Leg.status != "cancelled")
    )

    # Apply filters — can be combined
    if vessel_code:
        v_result = await db.execute(select(Vessel).where(Vessel.code == vessel_code))
        v = v_result.scalar_one_or_none()
        if v:
            query = query.where(Leg.vessel_id == v.id)

    if destination:
        query = query.where(Leg.arrival_port_locode == destination.upper())

    if origin:
        query = query.where(Leg.departure_port_locode == origin.upper())

    result = await db.execute(query.order_by(Leg.vessel_id, Leg.sequence))
    legs = result.scalars().all()

    # If custom leg selection, filter down further
    selected_leg_ids = set()
    if legs_ids:
        selected_leg_ids = set(int(x) for x in legs_ids.split(",") if x.strip().isdigit())
        legs = [l for l in legs if l.id in selected_leg_ids]

    # Always load all legs for selectors
    all_q = await db.execute(
        select(Leg)
        .options(selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
        .where(Leg.year == current_year, Leg.status != "cancelled")
        .order_by(Leg.vessel_id, Leg.sequence)
    )
    all_legs_for_selector = all_q.scalars().all()

    # Group by vessel
    legs_by_vessel = {}
    for leg in legs:
        vname = leg.vessel.name
        if vname not in legs_by_vessel:
            legs_by_vessel[vname] = []
        legs_by_vessel[vname].append(leg)

    # Group by route (dep → arr)
    legs_by_route = {}
    for leg in legs:
        route = f"{leg.departure_port.name} → {leg.arrival_port.name}"
        if route not in legs_by_route:
            legs_by_route[route] = []
        legs_by_route[route].append(leg)

    # Group by destination port
    legs_by_dest = {}
    for leg in legs:
        dest = leg.arrival_port.name
        if dest not in legs_by_dest:
            legs_by_dest[dest] = []
        legs_by_dest[dest].append(leg)

    # All unique ports for the selectors
    all_destinations = sorted(set(
        (leg.arrival_port_locode, leg.arrival_port.name) for leg in (all_legs_for_selector or legs)
    ), key=lambda x: x[1])

    all_origins = sorted(set(
        (leg.departure_port_locode, leg.departure_port.name) for leg in (all_legs_for_selector or legs)
    ), key=lambda x: x[1])

    # Build title
    title_parts = []
    if vessel_code:
        vname = next((v.name for v in vessels if v.code == vessel_code), "")
        title_parts.append(vname)
    if origin:
        oname = next((o[1] for o in all_origins if o[0] == origin.upper()), origin)
        if lang == "en":
            title_parts.append(f"from {oname}")
        else:
            title_parts.append(f"au départ de {oname}")
    if destination:
        dname = next((d[1] for d in all_destinations if d[0] == destination.upper()), destination)
        if lang == "en":
            title_parts.append(f"to {dname}")
        else:
            title_parts.append(f"vers {dname}")
    if selected_leg_ids:
        if lang == "en":
            title_parts.append(f"({len(selected_leg_ids)} legs selected)")
        else:
            title_parts.append(f"({len(selected_leg_ids)} legs sélectionnés)")

    if title_parts:
        prefix = "Commercial support" if lang == "en" else "Support commercial"
        title = f"{prefix} — {' · '.join(title_parts)}"
    else:
        title = "Commercial support — All departures" if lang == "en" else "Support commercial — Tous les départs"

    return templates.TemplateResponse("planning/pdf_commercial.html", {
        "request": request,
        "title": title,
        "template_type": template,
        "legs": legs,
        "legs_by_vessel": legs_by_vessel,
        "legs_by_route": legs_by_route,
        "legs_by_dest": legs_by_dest,
        "vessels": vessels,
        "all_destinations": all_destinations,
        "all_origins": all_origins,
        "all_legs_for_selector": all_legs_for_selector,
        "selected_leg_ids": selected_leg_ids,
        "current_year": current_year,
        "selected_vessel": vessel_code,
        "selected_destination": destination,
        "selected_origin": origin,
        "lang": lang or "fr",
        "now": datetime.now(tz.utc),
    })
