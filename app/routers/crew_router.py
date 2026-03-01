from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from app.templating import templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime, date, timedelta

from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.vessel import Vessel
from app.models.leg import Leg
from app.models.crew import CrewMember, CrewAssignment, CREW_ROLES, REQUIRED_ROLES
from app.utils.activity import log_activity

router = APIRouter(prefix="/crew", tags=["crew"])


def parse_date(val):
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return None
    try:
        return date.fromisoformat(val)
    except:
        return None


# ─── CREW LIST ───────────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def crew_list(
    request: Request,
    role: Optional[str] = Query(None),
    vessel: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(CrewMember).options(
        selectinload(CrewMember.assignments).selectinload(CrewAssignment.vessel)
    )
    if role:
        query = query.where(CrewMember.role == role)
    query = query.order_by(CrewMember.role, CrewMember.last_name)
    result = await db.execute(query)
    members = result.scalars().all()

    vessels_result = await db.execute(select(Vessel).where(Vessel.is_active == True).order_by(Vessel.code))
    vessels = vessels_result.scalars().all()

    today = date.today()

    # Compute status for each member
    member_data = []
    for m in members:
        current_assignment = None
        for a in m.assignments:
            if a.embark_date <= today and (a.disembark_date is None or a.disembark_date >= today):
                current_assignment = a
                break
        status = "repos"
        location = ""
        if current_assignment:
            status = "active"
            location = current_assignment.vessel.name if current_assignment.vessel else ""
        member_data.append({
            "member": m,
            "status": status,
            "location": location,
            "current_assignment": current_assignment,
            "total_days_year": sum(
                ((a.disembark_date or today) - a.embark_date).days
                for a in m.assignments
                if a.embark_date.year == today.year
            ),
        })

    # Bordée par navire
    bordees = {}
    for v in vessels:
        crew_on_board = []
        for md in member_data:
            if md["current_assignment"] and md["current_assignment"].vessel_id == v.id:
                crew_on_board.append(md)
        bordees[v.name] = {
            "vessel": v,
            "crew": crew_on_board,
            "missing": [r for r in REQUIRED_ROLES if not any(
                md["member"].role == r for md in crew_on_board
            )],
        }

    stats = {
        "total": len(members),
        "active": sum(1 for md in member_data if md["status"] == "active"),
        "repos": sum(1 for md in member_data if md["status"] == "repos"),
    }

    return templates.TemplateResponse("crew/index.html", {
        "request": request, "user": user,
        "member_data": member_data,
        "bordees": bordees,
        "vessels": vessels,
        "stats": stats,
        "crew_roles": CREW_ROLES,
        "current_role": role,
        "active_module": "crew",
    })


# ─── CREATE MEMBER ───────────────────────────────────────────
@router.get("/members/create", response_class=HTMLResponse)
async def member_create_form(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse("crew/member_form.html", {
        "request": request, "user": user,
        "edit_member": None, "crew_roles": CREW_ROLES, "error": None,
    })


@router.post("/members/create", response_class=HTMLResponse)
async def member_create_submit(
    request: Request,
    first_name: str = Form(...), last_name: str = Form(...),
    role: str = Form(...),
    phone: Optional[str] = Form(None), email: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    member = CrewMember(
        first_name=first_name.strip(), last_name=last_name.strip(),
        role=role, phone=phone, email=email,
        notes=notes.strip() if notes else None,
    )
    db.add(member)
    await db.flush()
    await log_activity(db, user, "crew", "create", "CrewMember", member.id, f"Marin {member.first_name} {member.last_name}")
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/crew"})
    return RedirectResponse(url="/crew", status_code=303)


# ─── EDIT MEMBER ─────────────────────────────────────────────
@router.get("/members/{mid}/edit", response_class=HTMLResponse)
async def member_edit_form(
    mid: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CrewMember).where(CrewMember.id == mid))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("crew/member_form.html", {
        "request": request, "user": user,
        "edit_member": member, "crew_roles": CREW_ROLES, "error": None,
    })


@router.post("/members/{mid}/edit", response_class=HTMLResponse)
async def member_edit_submit(
    mid: int, request: Request,
    first_name: str = Form(...), last_name: str = Form(...),
    role: str = Form(...),
    phone: Optional[str] = Form(None), email: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CrewMember).where(CrewMember.id == mid))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404)
    member.first_name = first_name.strip()
    member.last_name = last_name.strip()
    member.role = role
    member.phone = phone
    member.email = email
    member.notes = notes.strip() if notes else None
    await db.flush()
    await log_activity(db, user, "crew", "update", "CrewMember", mid, f"Modification marin {member.first_name} {member.last_name}")
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/crew"})
    return RedirectResponse(url="/crew", status_code=303)


# ─── DELETE MEMBER ───────────────────────────────────────────
@router.delete("/members/{mid}", response_class=HTMLResponse)
async def member_delete(
    mid: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CrewMember).where(CrewMember.id == mid))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404)
    name = f"{member.first_name} {member.last_name}"
    await db.delete(member)
    await db.flush()
    await log_activity(db, user, "crew", "delete", "CrewMember", mid, f"Suppression marin {name}")
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/crew"})
    return RedirectResponse(url="/crew", status_code=303)


# ─── ASSIGNMENTS ─────────────────────────────────────────────
@router.get("/members/{mid}/assign", response_class=HTMLResponse)
async def assign_form(
    mid: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CrewMember).where(CrewMember.id == mid))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404)
    vessels_result = await db.execute(select(Vessel).where(Vessel.is_active == True).order_by(Vessel.code))
    vessels = vessels_result.scalars().all()
    return templates.TemplateResponse("crew/assign_form.html", {
        "request": request, "user": user,
        "member": member, "vessels": vessels, "error": None,
    })


@router.post("/members/{mid}/assign", response_class=HTMLResponse)
async def assign_submit(
    mid: int, request: Request,
    vessel_id: str = Form(...),
    embark_date: str = Form(...),
    disembark_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assignment = CrewAssignment(
        member_id=mid, vessel_id=int(vessel_id),
        embark_date=parse_date(embark_date),
        disembark_date=parse_date(disembark_date),
        status="active" if not parse_date(disembark_date) else "planned",
        notes=notes.strip() if notes else None,
    )
    db.add(assignment)
    await db.flush()
    await log_activity(db, user, "crew", "assign", "CrewAssignment", assignment.id, f"Affectation marin")
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/crew"})
    return RedirectResponse(url="/crew", status_code=303)


@router.delete("/assignments/{aid}", response_class=HTMLResponse)
async def assignment_delete(
    aid: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CrewAssignment).where(CrewAssignment.id == aid))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404)
    await db.delete(assignment)
    await db.flush()
    await log_activity(db, user, "crew", "delete", "CrewAssignment", aid, "Suppression affectation")
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/crew"})
    return RedirectResponse(url="/crew", status_code=303)


# ─── API: Get crew members for a vessel (for operation forms) ──
@router.get("/api/vessel/{vessel_id}", response_class=HTMLResponse)
async def crew_for_vessel_api(
    vessel_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return crew members currently on board a vessel (for embark/disembark selection)."""
    from fastapi.responses import JSONResponse
    today = date.today()
    result = await db.execute(
        select(CrewAssignment).options(selectinload(CrewAssignment.member))
        .where(
            CrewAssignment.vessel_id == vessel_id,
            CrewAssignment.embark_date <= today,
            (CrewAssignment.disembark_date == None) | (CrewAssignment.disembark_date >= today),
        )
    )
    assignments = result.scalars().all()
    members = [
        {"id": a.member.id, "name": a.member.full_name, "role": a.member.role_label}
        for a in assignments if a.member
    ]
    # Also get all active members not on board (for embarkation)
    all_result = await db.execute(
        select(CrewMember).where(CrewMember.is_active == True).order_by(CrewMember.role, CrewMember.last_name)
    )
    all_members = all_result.scalars().all()
    on_board_ids = {a.member_id for a in assignments}
    available = [
        {"id": m.id, "name": m.full_name, "role": m.role_label}
        for m in all_members if m.id not in on_board_ids
    ]
    return JSONResponse({"on_board": members, "available": available})


# ─── MEMBER CALENDAR ─────────────────────────────────────────
@router.get("/members/{mid}/calendar", response_class=HTMLResponse)
async def member_calendar(
    mid: int, request: Request,
    year: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_year = year or date.today().year
    result = await db.execute(
        select(CrewMember).options(
            selectinload(CrewMember.assignments).selectinload(CrewAssignment.vessel)
        ).where(CrewMember.id == mid)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404)

    # Filter assignments for the year
    year_assignments = [
        a for a in member.assignments
        if a.embark_date.year == current_year or
           (a.disembark_date and a.disembark_date.year == current_year) or
           (a.embark_date.year <= current_year and (a.disembark_date is None or a.disembark_date.year >= current_year))
    ]
    year_assignments.sort(key=lambda a: a.embark_date)

    today = date.today()
    total_days = sum(
        ((min(a.disembark_date or today, date(current_year, 12, 31)) -
          max(a.embark_date, date(current_year, 1, 1))).days + 1)
        for a in year_assignments
        if a.embark_date <= date(current_year, 12, 31) and
           (a.disembark_date is None or a.disembark_date >= date(current_year, 1, 1))
    )
    days_in_year = 366 if current_year % 4 == 0 else 365
    rest_days = days_in_year - total_days

    return templates.TemplateResponse("crew/calendar.html", {
        "request": request, "user": user,
        "member": member, "assignments": year_assignments,
        "current_year": current_year,
        "total_days": total_days, "rest_days": rest_days,
        "days_in_year": days_in_year,
        "active_module": "crew",
    })
