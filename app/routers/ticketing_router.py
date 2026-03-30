"""Ticketing module router — crew requests for port calls."""
import secrets
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Request, Depends, Query, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.templating import templates
from app.database import get_db
from app.auth import get_current_user
from app.permissions import can_edit, can_delete
from app.models.user import User
from app.models.vessel import Vessel
from app.models.leg import Leg
from app.models.ticket import (
    Ticket, TicketComment,
    TICKET_CATEGORIES, TICKET_PRIORITIES, TICKET_STATUSES,
)

router = APIRouter(prefix="/ticketing", tags=["ticketing"])


def _gen_ticket_ref():
    return f"TKT-{date.today().strftime('%y%m')}-{secrets.token_hex(2).upper()}"


# === LIST ===
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def ticket_list(
    request: Request,
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    vessel: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Ticket)
        .options(
            selectinload(Ticket.vessel),
            selectinload(Ticket.leg),
            selectinload(Ticket.created_by),
            selectinload(Ticket.assigned_to),
        )
        .order_by(Ticket.created_at.desc())
    )
    if category:
        query = query.where(Ticket.category == category)
    if status:
        query = query.where(Ticket.status == status)
    if priority:
        query = query.where(Ticket.priority == priority)
    if vessel:
        query = query.where(Ticket.vessel_id == vessel)

    result = await db.execute(query)
    tickets = result.scalars().all()

    stats = {
        "total": len(tickets),
        "open": sum(1 for t in tickets if t.status == "open"),
        "in_progress": sum(1 for t in tickets if t.status == "in_progress"),
        "waiting": sum(1 for t in tickets if t.status == "waiting"),
        "resolved": sum(1 for t in tickets if t.status in ("resolved", "closed")),
    }

    vessels_result = await db.execute(
        select(Vessel).where(Vessel.is_active == True).order_by(Vessel.code)
    )
    vessels = vessels_result.scalars().all()

    return templates.TemplateResponse("ticketing/index.html", {
        "request": request, "user": user,
        "tickets": tickets, "stats": stats,
        "vessels": vessels,
        "ticket_categories": TICKET_CATEGORIES,
        "ticket_priorities": TICKET_PRIORITIES,
        "ticket_statuses": TICKET_STATUSES,
        "selected_category": category,
        "selected_status": status,
        "selected_priority": priority,
        "selected_vessel": vessel,
        "active_module": "ticketing",
    })


# === CREATE FORM ===
@router.get("/create", response_class=HTMLResponse)
async def ticket_create_form(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    vessels = (await db.execute(
        select(Vessel).where(Vessel.is_active == True).order_by(Vessel.code)
    )).scalars().all()
    legs = (await db.execute(
        select(Leg).order_by(Leg.etd.desc()).limit(50)
    )).scalars().all()
    users_result = (await db.execute(
        select(User).where(User.is_active == True).order_by(User.full_name)
    )).scalars().all()

    return templates.TemplateResponse("ticketing/ticket_form.html", {
        "request": request, "user": user,
        "ticket": None,
        "vessels": vessels, "legs": legs, "all_users": users_result,
        "ticket_categories": TICKET_CATEGORIES,
        "ticket_priorities": TICKET_PRIORITIES,
        "active_module": "ticketing",
    })


# === CREATE POST ===
@router.post("/create", response_class=HTMLResponse)
async def ticket_create(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    priority: str = Form("normal"),
    vessel_id: int = Form(...),
    leg_id: Optional[int] = Form(None),
    assigned_to_id: Optional[int] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not can_edit(user, "ticketing"):
        raise HTTPException(status_code=403)

    ticket = Ticket(
        reference=_gen_ticket_ref(),
        title=title,
        description=description,
        category=category,
        priority=priority,
        vessel_id=vessel_id,
        leg_id=leg_id or None,
        created_by_id=user.id,
        assigned_to_id=assigned_to_id or None,
    )
    db.add(ticket)
    await db.flush()

    if request.headers.get("HX-Request"):
        return HTMLResponse(headers={"HX-Redirect": "/ticketing"})
    return RedirectResponse("/ticketing", status_code=303)


# === DETAIL ===
@router.get("/{ticket_id}", response_class=HTMLResponse)
async def ticket_detail(
    request: Request,
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.vessel),
            selectinload(Ticket.leg),
            selectinload(Ticket.created_by),
            selectinload(Ticket.assigned_to),
            selectinload(Ticket.comments).selectinload(TicketComment.author),
        )
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404)

    users_result = (await db.execute(
        select(User).where(User.is_active == True).order_by(User.full_name)
    )).scalars().all()

    return templates.TemplateResponse("ticketing/ticket_detail.html", {
        "request": request, "user": user,
        "ticket": ticket, "all_users": users_result,
        "ticket_statuses": TICKET_STATUSES,
        "ticket_priorities": TICKET_PRIORITIES,
        "active_module": "ticketing",
    })


# === UPDATE STATUS ===
@router.post("/{ticket_id}/status", response_class=HTMLResponse)
async def ticket_update_status(
    request: Request,
    ticket_id: int,
    status: str = Form(...),
    resolution_notes: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not can_edit(user, "ticketing"):
        raise HTTPException(status_code=403)

    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404)

    ticket.status = status
    if resolution_notes:
        ticket.resolution_notes = resolution_notes
    if status == "resolved":
        ticket.resolved_at = datetime.utcnow()
    if status == "closed":
        ticket.closed_at = datetime.utcnow()

    await db.flush()

    if request.headers.get("HX-Request"):
        return HTMLResponse(headers={"HX-Redirect": f"/ticketing/{ticket_id}"})
    return RedirectResponse(f"/ticketing/{ticket_id}", status_code=303)


# === ASSIGN ===
@router.post("/{ticket_id}/assign", response_class=HTMLResponse)
async def ticket_assign(
    request: Request,
    ticket_id: int,
    assigned_to_id: Optional[int] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not can_edit(user, "ticketing"):
        raise HTTPException(status_code=403)

    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404)

    ticket.assigned_to_id = assigned_to_id or None
    if assigned_to_id and ticket.status == "open":
        ticket.status = "in_progress"
    await db.flush()

    if request.headers.get("HX-Request"):
        return HTMLResponse(headers={"HX-Redirect": f"/ticketing/{ticket_id}"})
    return RedirectResponse(f"/ticketing/{ticket_id}", status_code=303)


# === ADD COMMENT ===
@router.post("/{ticket_id}/comment", response_class=HTMLResponse)
async def ticket_add_comment(
    request: Request,
    ticket_id: int,
    content: str = Form(...),
    is_internal: bool = Form(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404)

    comment = TicketComment(
        ticket_id=ticket_id,
        author_id=user.id,
        content=content,
        is_internal=is_internal,
    )
    db.add(comment)
    await db.flush()

    if request.headers.get("HX-Request"):
        return HTMLResponse(headers={"HX-Redirect": f"/ticketing/{ticket_id}"})
    return RedirectResponse(f"/ticketing/{ticket_id}", status_code=303)


# === DELETE ===
@router.post("/{ticket_id}/delete", response_class=HTMLResponse)
async def ticket_delete(
    request: Request,
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not can_delete(user, "ticketing"):
        raise HTTPException(status_code=403)

    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404)

    await db.delete(ticket)
    await db.flush()

    if request.headers.get("HX-Request"):
        return HTMLResponse(headers={"HX-Redirect": "/ticketing"})
    return RedirectResponse("/ticketing", status_code=303)
