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
import math

from app.database import get_db
from app.auth import get_current_user, AuthRequired
from app.permissions import require_permission
from app.models.user import User
from app.models.vessel import Vessel
from app.models.leg import Leg
from app.models.kpi import LegKPI
from app.models.emission_parameter import EmissionParameter
from app.models.co2_variable import Co2Variable, CO2_DEFAULTS
from app.utils.activity import log_activity

router = APIRouter(prefix="/kpi", tags=["kpi"])

# ─── EMISSION FACTORS ────────────────────────────────────────
# Default factors (overridable via EmissionParameter table)
DEFAULTS = {
    "conventional_co2_per_ton_nm": 0.0152,   # kg CO2 per ton per NM (conventional cargo)
    "sail_co2_per_ton_nm": 0.00198,           # kg CO2 per ton per NM (TOWT sail cargo)
    "conventional_nox_per_ton_nm": 0.000406,  # kg NOx per ton per NM
    "sail_nox_per_ton_nm": 0.0000528,         # kg NOx per ton per NM
    "conventional_sox_per_ton_nm": 0.0000812,  # kg SOx per ton per NM
    "sail_sox_per_ton_nm": 0.00001056,         # kg SOx per ton per NM
    "co2_reduction_pct": 87,                   # % reduction vs conventional
    # Equivalences
    "co2_per_flight_paris_nyc": 525,           # tonnes CO2 for 1 Paris-NYC flight (plane, ~300 pax)
    "co2_per_container_asia_eu": 2.5,          # tonnes CO2 for 1 container Asia-Europe conventional
}


async def get_co2_variables(db: AsyncSession) -> dict:
    """Get current CO2 decarbonation variables from DB, fallback to defaults."""
    result = await db.execute(
        select(Co2Variable).where(Co2Variable.is_current == True)
    )
    stored = {v.variable_name: v.variable_value for v in result.scalars().all()}
    return {k: stored.get(k, info["value"]) for k, info in CO2_DEFAULTS.items()}


def compute_decarbonation(cargo_tons: float, distance_nm: float, co2_vars: dict) -> dict:
    """Compute decarbonation for given cargo and distance.

    Formula: (Conv EF - TOWT EF) * fill_rate * capacity * distance * nm_to_km
    Simplified: (Conv EF - TOWT EF) * cargo_tons * distance * nm_to_km (gCO2)
    """
    towt_ef = co2_vars.get("towt_co2_ef", 1.5)
    conv_ef = co2_vars.get("conventional_co2_ef", 13.7)
    capacity = co2_vars.get("sailing_cargo_capacity", 1100)
    nm_to_km = co2_vars.get("nm_to_km", 1.852)

    if not cargo_tons or not distance_nm:
        return {"decarb_g": 0, "decarb_kg": 0, "decarb_t": 0, "fill_rate_pct": 0}

    fill_rate = min(cargo_tons / capacity, 1.0) if capacity > 0 else 0
    decarb_g = (conv_ef - towt_ef) * fill_rate * capacity * distance_nm * nm_to_km
    decarb_kg = decarb_g / 1000
    decarb_t = decarb_kg / 1000

    return {
        "decarb_g": round(decarb_g, 1),
        "decarb_kg": round(decarb_kg, 2),
        "decarb_t": round(decarb_t, 3),
        "fill_rate_pct": round(fill_rate * 100, 1),
    }


async def get_emission_params(db: AsyncSession) -> dict:
    """Get emission parameters from DB, fallback to defaults."""
    result = await db.execute(select(EmissionParameter))
    params = {p.parameter_name: p.parameter_value for p in result.scalars().all()}
    merged = {**DEFAULTS, **{k: float(v) for k, v in params.items() if v}}
    return merged


def compute_leg_kpi(leg, cargo_tons: float, params: dict) -> dict:
    """Compute all KPIs for a single leg."""
    distance = leg.computed_distance or (leg.distance_nm * (leg.elongation_coeff or 1.25) if leg.distance_nm else 0)
    if not distance or not cargo_tons:
        return {
            "co2_conventional_kg": 0, "co2_sail_kg": 0, "co2_avoided_kg": 0,
            "nox_conventional_kg": 0, "nox_sail_kg": 0, "nox_avoided_kg": 0,
            "sox_conventional_kg": 0, "sox_sail_kg": 0, "sox_avoided_kg": 0,
            "co2_per_ton_kg": 0, "occupation_pct": 0, "distance_nm": distance,
            "equiv_flights_paris_nyc": 0, "equiv_containers_asia_eu": 0,
        }

    # CO2
    co2_conv = cargo_tons * distance * params["conventional_co2_per_ton_nm"]
    co2_sail = cargo_tons * distance * params["sail_co2_per_ton_nm"]
    co2_avoided = co2_conv - co2_sail

    # NOx
    nox_conv = cargo_tons * distance * params["conventional_nox_per_ton_nm"]
    nox_sail = cargo_tons * distance * params["sail_nox_per_ton_nm"]
    nox_avoided = nox_conv - nox_sail

    # SOx
    sox_conv = cargo_tons * distance * params["conventional_sox_per_ton_nm"]
    sox_sail = cargo_tons * distance * params["sail_sox_per_ton_nm"]
    sox_avoided = sox_conv - sox_sail

    # Per ton
    co2_per_ton = co2_sail / cargo_tons if cargo_tons > 0 else 0

    # Occupation (from vessel capacity)
    vessel_capacity = leg.vessel.dwt if leg.vessel and leg.vessel.dwt else 1000
    occupation = min(100, (cargo_tons / vessel_capacity) * 100)

    # Equivalences
    co2_avoided_tons = co2_avoided / 1000
    equiv_flights = co2_avoided_tons / params["co2_per_flight_paris_nyc"] if params["co2_per_flight_paris_nyc"] > 0 else 0
    equiv_containers = co2_avoided_tons / params["co2_per_container_asia_eu"] if params["co2_per_container_asia_eu"] > 0 else 0

    return {
        "co2_conventional_kg": round(co2_conv, 1),
        "co2_sail_kg": round(co2_sail, 1),
        "co2_avoided_kg": round(co2_avoided, 1),
        "nox_conventional_kg": round(nox_conv, 2),
        "nox_sail_kg": round(nox_sail, 2),
        "nox_avoided_kg": round(nox_avoided, 2),
        "sox_conventional_kg": round(sox_conv, 2),
        "sox_sail_kg": round(sox_sail, 2),
        "sox_avoided_kg": round(sox_avoided, 2),
        "co2_per_ton_kg": round(co2_per_ton, 3),
        "occupation_pct": round(occupation, 1),
        "distance_nm": round(distance, 1),
        "equiv_flights_paris_nyc": round(equiv_flights, 2),
        "equiv_containers_asia_eu": round(equiv_containers, 1),
    }


# ─── KPI DASHBOARD ───────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
async def kpi_dashboard(
    request: Request,
    vessel: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    user: User = Depends(require_permission("kpi", "C")),
    db: AsyncSession = Depends(get_db),
):
    current_year = year or datetime.now().year
    years = list(range(2025, datetime.now().year + 2))

    vessels_result = await db.execute(select(Vessel).where(Vessel.is_active == True).order_by(Vessel.code))
    vessels = vessels_result.scalars().all()

    params = await get_emission_params(db)
    co2_vars = await get_co2_variables(db)

    # Get all legs (optionally filtered)
    query = (
        select(Leg)
        .options(selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
        .where(Leg.year == current_year)
    )
    vessel_obj = None
    if vessel:
        v_result = await db.execute(select(Vessel).where(Vessel.code == vessel))
        vessel_obj = v_result.scalar_one_or_none()
        if vessel_obj:
            query = query.where(Leg.vessel_id == vessel_obj.id)

    result = await db.execute(query.order_by(Leg.vessel_id, Leg.sequence))
    legs = result.scalars().all()

    # Get stored KPI data (cargo_tons per leg)
    kpi_data = {}
    kpi_result = await db.execute(select(LegKPI))
    for k in kpi_result.scalars().all():
        kpi_data[k.leg_id] = k

    # Compute KPIs for each leg
    leg_kpis = []
    totals = {
        "co2_avoided_kg": 0, "nox_avoided_kg": 0, "sox_avoided_kg": 0,
        "distance_nm": 0, "cargo_tons": 0, "co2_sail_kg": 0,
        "equiv_flights": 0, "equiv_containers": 0, "occupation_sum": 0,
        "leg_count": 0, "decarb_t": 0,
    }

    for leg in legs:
        stored = kpi_data.get(leg.id)
        cargo_tons = stored.cargo_tons if stored else 0
        kpi = compute_leg_kpi(leg, cargo_tons, params)
        decarb = compute_decarbonation(cargo_tons, kpi["distance_nm"], co2_vars)
        kpi["leg"] = leg
        kpi["cargo_tons"] = cargo_tons
        kpi["decarb_t"] = decarb["decarb_t"]
        kpi["decarb_kg"] = decarb["decarb_kg"]
        kpi["fill_rate_pct"] = decarb["fill_rate_pct"]
        leg_kpis.append(kpi)

        totals["co2_avoided_kg"] += kpi["co2_avoided_kg"]
        totals["nox_avoided_kg"] += kpi["nox_avoided_kg"]
        totals["sox_avoided_kg"] += kpi["sox_avoided_kg"]
        totals["distance_nm"] += kpi["distance_nm"]
        totals["cargo_tons"] += cargo_tons
        totals["co2_sail_kg"] += kpi["co2_sail_kg"]
        totals["equiv_flights"] += kpi["equiv_flights_paris_nyc"]
        totals["equiv_containers"] += kpi["equiv_containers_asia_eu"]
        totals["occupation_sum"] += kpi["occupation_pct"]
        totals["leg_count"] += 1
        totals["decarb_t"] += decarb["decarb_t"]

    totals["occupation_avg"] = round(totals["occupation_sum"] / totals["leg_count"], 1) if totals["leg_count"] > 0 else 0
    totals["co2_per_ton_avg"] = round(totals["co2_sail_kg"] / totals["cargo_tons"], 3) if totals["cargo_tons"] > 0 else 0

    # ── Claims statistics for KPI dashboard ──
    from app.models.claim import Claim
    claims_query = select(Claim).join(Leg, Claim.leg_id == Leg.id).where(Leg.year == current_year)
    if vessel_obj:
        claims_query = claims_query.where(Claim.vessel_id == vessel_obj.id)
    claims_result = await db.execute(claims_query)
    all_claims = claims_result.scalars().all()
    claims_stats = {
        "total": len(all_claims),
        "open": sum(1 for c in all_claims if c.status in ("open", "declared", "instruction")),
        "closed": sum(1 for c in all_claims if c.status in ("accepted", "refused", "closed")),
        "cargo": sum(1 for c in all_claims if c.claim_type == "cargo"),
        "crew": sum(1 for c in all_claims if c.claim_type == "crew"),
        "hull": sum(1 for c in all_claims if c.claim_type == "hull"),
        "total_provision": sum(float(c.provision_amount or 0) for c in all_claims),
        "total_indemnity": sum(float(c.indemnity_amount or 0) for c in all_claims),
    }
    claims_per_leg = round(claims_stats["total"] / totals["leg_count"], 2) if totals["leg_count"] > 0 else 0

    return templates.TemplateResponse("kpi/index.html", {
        "request": request,
        "user": user,
        "vessels": vessels,
        "selected_vessel": vessel,
        "current_year": current_year,
        "years": years,
        "leg_kpis": leg_kpis,
        "totals": totals,
        "params": params,
        "co2_vars": co2_vars,
        "claims_stats": claims_stats,
        "claims_per_leg": claims_per_leg,
        "active_module": "kpi",
    })


# ─── UPDATE CARGO TONS (inline edit) ─────────────────────────
@router.post("/legs/{leg_id}/cargo", response_class=HTMLResponse)
async def update_cargo(
    leg_id: int,
    request: Request,
    cargo_tons: str = Form(...),
    user: User = Depends(require_permission("kpi", "M")),
    db: AsyncSession = Depends(get_db),
):
    _tons = 0
    try:
        _tons = float(cargo_tons) if cargo_tons.strip() else 0
    except ValueError:
        _tons = 0

    # Get or create LegKPI
    result = await db.execute(select(LegKPI).where(LegKPI.leg_id == leg_id))
    kpi = result.scalar_one_or_none()
    if kpi:
        kpi.cargo_tons = _tons
    else:
        kpi = LegKPI(leg_id=leg_id, cargo_tons=_tons)
        db.add(kpi)

    await db.flush()
    await log_activity(db, user, "kpi", "update_cargo", "LegKPI", leg_id, f"Tonnage cargo → {_tons}t")

    # Redirect back
    leg_result = await db.execute(select(Leg).options(selectinload(Leg.vessel)).where(Leg.id == leg_id))
    leg = leg_result.scalar_one_or_none()
    year = leg.year if leg else datetime.now().year
    vessel_code = leg.vessel.code if leg and leg.vessel else ""

    url = f"/kpi?year={year}" + (f"&vessel={vessel_code}" if vessel_code else "")
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


# ─── EXPORT KPI CSV ──────────────────────────────────────────
@router.get("/export/csv", response_class=StreamingResponse)
async def export_kpi_csv(
    user: User = Depends(require_permission("kpi", "C")),
    db: AsyncSession = Depends(get_db),
):
    params = await get_emission_params(db)
    co2_vars = await get_co2_variables(db)

    legs_result = await db.execute(
        select(Leg)
        .options(selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
        .order_by(Leg.year, Leg.vessel_id, Leg.sequence)
    )
    legs = legs_result.scalars().all()

    kpi_result = await db.execute(select(LegKPI))
    kpi_data = {k.leg_id: k for k in kpi_result.scalars().all()}

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Leg", "Navire", "Année", "Départ", "Arrivée", "Distance (NM)",
        "Tonnes transportées", "Occupation (%)",
        "CO2 conventionnel (kg)", "CO2 voile (kg)", "CO2 évité (kg)",
        "NOx évité (kg)", "SOx évité (kg)",
        "CO2/tonne (kg)", "Equiv. vols Paris-NYC", "Equiv. containers Asie-EU",
        "Décarbonation (t CO2)"
    ])

    for leg in legs:
        stored = kpi_data.get(leg.id)
        cargo = stored.cargo_tons if stored else 0
        kpi = compute_leg_kpi(leg, cargo, params)
        decarb = compute_decarbonation(cargo, kpi["distance_nm"], co2_vars)
        writer.writerow([
            leg.leg_code, leg.vessel.name, leg.year,
            leg.departure_port.locode, leg.arrival_port.locode,
            kpi["distance_nm"], cargo, kpi["occupation_pct"],
            kpi["co2_conventional_kg"], kpi["co2_sail_kg"], kpi["co2_avoided_kg"],
            kpi["nox_avoided_kg"], kpi["sox_avoided_kg"],
            kpi["co2_per_ton_kg"], kpi["equiv_flights_paris_nyc"], kpi["equiv_containers_asia_eu"],
            decarb["decarb_t"],
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=kpi_towt.csv"},
    )
