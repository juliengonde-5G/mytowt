from fastapi import APIRouter, Request, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from app.templating import templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.leg import Leg
from app.models.vessel import Vessel
from app.models.order import Order
from app.models.finance import LegFinance
from app.models.operation import EscaleOperation
from app.models.packing_list import PackingList
from app.utils.activity import log_activity

router = APIRouter(tags=["dashboard"])


# ─── ALERTS ENGINE ───────────────────────────────────────────
async def compute_alerts(db: AsyncSession, current_year: int):
    """Compute all active alerts for the dashboard."""
    now = datetime.now(timezone.utc)
    alerts = []

    all_legs_result = await db.execute(
        select(Leg).options(
            selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port)
        ).where(Leg.year == current_year, Leg.status != "cancelled")
        .order_by(Leg.vessel_id, Leg.sequence)
    )
    all_legs = all_legs_result.scalars().all()

    for leg in all_legs:
        # 1. ETA delay: ATA > ETA by more than 24h
        if leg.ata and leg.eta:
            delay_h = (leg.ata - leg.eta).total_seconds() / 3600
            if delay_h > 24:
                alerts.append({
                    "type": "retard",
                    "severity": "warning" if delay_h < 72 else "danger",
                    "icon": "clock",
                    "title": f"Retard {leg.leg_code}",
                    "message": f"{leg.vessel.name} — arrivée {leg.arrival_port.name} avec {int(delay_h)}h de retard (ETA {leg.eta.strftime('%d/%m')} → ATA {leg.ata.strftime('%d/%m')})",
                    "link": f"/escale?vessel={leg.vessel.code}&year={leg.year}&leg_id={leg.id}",
                })

        # 2. ETA overdue: ETA passed by >24h, no ATA
        if leg.eta and not leg.ata and not leg.atd:
            overdue_h = (now - leg.eta).total_seconds() / 3600
            if overdue_h > 24:
                alerts.append({
                    "type": "retard",
                    "severity": "danger",
                    "icon": "alert-triangle",
                    "title": f"ETA dépassée {leg.leg_code}",
                    "message": f"{leg.vessel.name} → {leg.arrival_port.name} — ETA {leg.eta.strftime('%d/%m %H:%M')} dépassée de {int(overdue_h)}h, ATA non renseignée",
                    "link": f"/escale?vessel={leg.vessel.code}&year={leg.year}&leg_id={leg.id}",
                })

        # 3. Escale non verrouillée: ATD set but status != completed
        if leg.atd and leg.status != "completed":
            alerts.append({
                "type": "verrouillage",
                "severity": "info",
                "icon": "unlock",
                "title": f"Escale non verrouillée {leg.leg_code}",
                "message": f"{leg.vessel.name} — ATD renseigné ({leg.atd.strftime('%d/%m')}) mais escale non verrouillée",
                "link": f"/escale?vessel={leg.vessel.code}&year={leg.year}&leg_id={leg.id}",
            })

        # 4. Departure imminent: ETD within 48h and no operations planned
        if leg.etd and not leg.atd:
            hours_to_dep = (leg.etd - now).total_seconds() / 3600
            if 0 < hours_to_dep < 48:
                ops_result = await db.execute(
                    select(func.count(EscaleOperation.id)).where(EscaleOperation.leg_id == leg.id)
                )
                ops_count = ops_result.scalar() or 0
                if ops_count == 0:
                    alerts.append({
                        "type": "preparation",
                        "severity": "warning",
                        "icon": "alert-circle",
                        "title": f"Départ imminent {leg.leg_code}",
                        "message": f"{leg.vessel.name} — départ {leg.departure_port.name} dans {int(hours_to_dep)}h, aucune opération planifiée",
                        "link": f"/escale?vessel={leg.vessel.code}&year={leg.year}&leg_id={leg.id}",
                    })

    # 5. Port conflicts: multiple vessels at same port within 48h
    port_legs = {}
    for leg in all_legs:
        if leg.eta:
            port = leg.arrival_port_locode
            if port not in port_legs:
                port_legs[port] = []
            port_legs[port].append(leg)

    for port, plegs in port_legs.items():
        for i in range(len(plegs)):
            for j in range(i + 1, len(plegs)):
                if plegs[i].vessel_id == plegs[j].vessel_id:
                    continue
                diff_h = abs((plegs[i].eta - plegs[j].eta).total_seconds()) / 3600
                if diff_h < 48:
                    key = f"conflict-{port}-{min(plegs[i].id, plegs[j].id)}-{max(plegs[i].id, plegs[j].id)}"
                    if not any(a.get("_key") == key for a in alerts):
                        alerts.append({
                            "_key": key,
                            "type": "conflit",
                            "severity": "warning",
                            "icon": "alert-triangle",
                            "title": f"Conflit port {port}",
                            "message": f"{plegs[i].vessel.name} ({plegs[i].leg_code}) et {plegs[j].vessel.name} ({plegs[j].leg_code}) — ETA < 48h d'écart",
                            "link": f"/planning/ports?port={port}",
                        })

    # 6. Unassigned orders
    unassigned_result = await db.execute(
        select(func.count(Order.id)).where(Order.status == "non_affecte")
    )
    unassigned = unassigned_result.scalar() or 0
    if unassigned > 0:
        alerts.append({
            "type": "commercial",
            "severity": "info",
            "icon": "package",
            "title": f"{unassigned} commande{'s' if unassigned > 1 else ''} non affectée{'s' if unassigned > 1 else ''}",
            "message": "Des commandes sont en attente d'affectation à un leg",
            "link": "/commercial?status=non_affecte",
        })

    # Sort: danger first, then warning, then info
    severity_order = {"danger": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: severity_order.get(a["severity"], 3))

    return alerts


# ─── DASHBOARD ───────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    current_year = now.year

    vessels_result = await db.execute(select(Vessel).where(Vessel.is_active == True).order_by(Vessel.code))
    vessels = vessels_result.scalars().all()

    vessel_statuses = []
    for v in vessels:
        legs_result = await db.execute(
            select(Leg).options(selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
            .where(Leg.vessel_id == v.id, Leg.year == current_year)
            .order_by(Leg.sequence)
        )
        legs = legs_result.scalars().all()

        status = "unknown"
        location = ""
        current_leg = None

        for leg in legs:
            if leg.ata and not leg.atd:
                status = "a_quai"
                location = leg.arrival_port.name if leg.arrival_port else leg.arrival_port_locode
                current_leg = leg
                break
            elif leg.eta and leg.eta > now and not leg.ata:
                status = "en_mer"
                current_leg = leg
                location = f"→ {leg.arrival_port.name}"
                break

        if status == "unknown" and legs:
            last = legs[-1]
            if last.atd:
                status = "en_mer"
                location = f"→ suite"
            elif last.ata:
                status = "a_quai"
                location = last.arrival_port.name if last.arrival_port else ""
            else:
                first = legs[0]
                if first.etd and first.etd > now:
                    status = "a_quai"
                    location = first.departure_port.name if first.departure_port else ""

        vessel_statuses.append({
            "vessel": v, "status": status,
            "location": location, "current_leg": current_leg,
        })

    # Stats
    total_legs = (await db.execute(select(func.count(Leg.id)).where(Leg.year == current_year))).scalar() or 0
    total_orders = (await db.execute(select(func.count(Order.id)).where(Order.status.in_(["non_affecte", "reserve", "confirme"])))).scalar() or 0

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month < 12:
        month_end = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        month_end = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    escales_month = (await db.execute(
        select(func.count(Leg.id)).where(Leg.year == current_year, Leg.eta >= month_start, Leg.eta < month_end)
    )).scalar() or 0

    fin_row = (await db.execute(
        select(func.sum(LegFinance.revenue_forecast), func.sum(LegFinance.result_forecast))
        .join(Leg, Leg.id == LegFinance.leg_id).where(Leg.year == current_year)
    )).one_or_none()
    ca_forecast = (fin_row[0] or 0) if fin_row else 0

    # CO2 avoided + fill rate
    from app.models.kpi import LegKPI
    kpi_legs_result = await db.execute(
        select(Leg).options(selectinload(Leg.vessel), selectinload(Leg.kpi))
        .where(Leg.year == current_year, Leg.status != "cancelled")
    )
    kpi_legs = kpi_legs_result.scalars().all()
    co2_avoided_total = 0.0
    fill_rates = []
    for kl in kpi_legs:
        cargo = kl.kpi.cargo_tons if kl.kpi else 0
        distance = kl.computed_distance or 0
        if cargo and distance:
            co2_conv = cargo * distance * 0.0152
            co2_sail = cargo * distance * 0.00198
            co2_avoided_total += (co2_conv - co2_sail)
        if kl.vessel and kl.vessel.dwt and cargo:
            fill_rates.append(min(100, (cargo / kl.vessel.dwt) * 100))
    avg_fill_rate = round(sum(fill_rates) / len(fill_rates), 1) if fill_rates else 0

    upcoming_result = await db.execute(
        select(Leg).options(selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
        .where(Leg.year == current_year, Leg.etd != None, Leg.atd == None)
        .order_by(Leg.etd).limit(5)
    )
    upcoming_legs = upcoming_result.scalars().all()

    # Alerts
    alerts = await compute_alerts(db, current_year)

    # Cargo notifications (submitted packing lists not yet locked)
    notif_result = await db.execute(
        select(PackingList).options(
            selectinload(PackingList.order),
            selectinload(PackingList.batches),
        ).where(PackingList.status == "submitted")
        .order_by(PackingList.updated_at.desc())
    )
    cargo_notifications = notif_result.scalars().all()

    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user,
        "vessel_statuses": vessel_statuses,
        "total_legs": total_legs, "total_orders": total_orders,
        "escales_month": escales_month, "ca_forecast": ca_forecast,
        "co2_avoided_kg": co2_avoided_total, "avg_fill_rate": avg_fill_rate,
        "upcoming_legs": upcoming_legs, "alerts": alerts,
        "cargo_notifications": cargo_notifications,
        "current_year": current_year, "active_module": "dashboard",
    })


# ─── DISMISS CARGO NOTIFICATION ──────────────────────────────
@router.post("/notifications/cargo/{pl_id}/dismiss", response_class=HTMLResponse)
async def dismiss_cargo_notification(
    pl_id: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PackingList).where(PackingList.id == pl_id))
    pl = result.scalar_one_or_none()
    if pl and pl.status == "submitted":
        pl.status = "reviewed"
    await db.flush()
    await log_activity(db, user, "dashboard", "dismiss", "PackingList", pl_id, "Notification cargo acquittée")
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/"})
    return RedirectResponse(url="/", status_code=303)


# ─── CAPTAIN DASHBOARD ──────────────────────────────────────
@router.get("/captain", response_class=HTMLResponse)
async def captain_dashboard(
    request: Request,
    vessel: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.permissions import can_view
    if not can_view(user, "captain"):
        raise HTTPException(status_code=403, detail="Accès non autorisé")
    now = datetime.now(timezone.utc)
    current_year = now.year

    vessels_result = await db.execute(select(Vessel).where(Vessel.is_active == True).order_by(Vessel.code))
    vessels = vessels_result.scalars().all()

    selected_vessel = vessel or (vessels[0].code if vessels else None)
    vessel_obj = None
    if selected_vessel:
        v_result = await db.execute(select(Vessel).where(Vessel.code == selected_vessel))
        vessel_obj = v_result.scalar_one_or_none()

    legs = []
    current_leg = None
    next_legs = []
    past_legs = []
    ops_current = []

    if vessel_obj:
        legs_result = await db.execute(
            select(Leg).options(
                selectinload(Leg.departure_port), selectinload(Leg.arrival_port),
                selectinload(Leg.operations), selectinload(Leg.docker_shifts),
            ).where(Leg.vessel_id == vessel_obj.id, Leg.year == current_year)
            .order_by(Leg.sequence)
        )
        legs = legs_result.scalars().all()

        for leg in legs:
            if leg.ata and not leg.atd:
                current_leg = leg
            elif leg.atd:
                past_legs.append(leg)
            elif leg.eta and leg.eta > now:
                next_legs.append(leg)
            elif not leg.ata and not leg.atd:
                next_legs.append(leg)

        if current_leg:
            ops_result = await db.execute(
                select(EscaleOperation).where(EscaleOperation.leg_id == current_leg.id)
                .order_by(EscaleOperation.planned_start.asc().nulls_last())
            )
            ops_current = ops_result.scalars().all()

    return templates.TemplateResponse("captain/index.html", {
        "request": request, "user": user,
        "vessels": vessels, "selected_vessel": selected_vessel, "vessel_obj": vessel_obj,
        "legs": legs, "current_leg": current_leg,
        "next_legs": next_legs[:5], "past_legs": past_legs[-3:],
        "ops_current": ops_current,
        "current_year": current_year, "active_module": "captain",
    })
