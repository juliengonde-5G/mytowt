"""External passenger portal — accessible by token, no authentication."""
import os
import uuid
from datetime import datetime, date
from fastapi import APIRouter, Request, Depends, Form, HTTPException, UploadFile, File, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.templating import templates
from app.database import get_db
from app.models.leg import Leg
from app.models.passenger import (
    PassengerBooking, Passenger, PassengerDocument, PreBoardingForm,
    DOCUMENT_TYPES, DOCUMENT_STATUSES, CABIN_TYPE_LABELS,
)

ext_router = APIRouter(prefix="/passenger", tags=["passenger-external"])

UPLOAD_DIR = "/app/uploads/passenger_docs"


async def _get_booking_by_token(token: str, db: AsyncSession) -> PassengerBooking:
    result = await db.execute(
        select(PassengerBooking).options(
            selectinload(PassengerBooking.passengers).selectinload(Passenger.documents),
            selectinload(PassengerBooking.leg).selectinload(Leg.departure_port),
            selectinload(PassengerBooking.leg).selectinload(Leg.arrival_port),
            selectinload(PassengerBooking.leg).selectinload(Leg.vessel),
            selectinload(PassengerBooking.vessel),
            selectinload(PassengerBooking.payments),
        ).where(PassengerBooking.token == token)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "Réservation introuvable.")
    return booking


# ═══════════════════════════════════════════════════════════════
#  MAIN PAGE
# ═══════════════════════════════════════════════════════════════
@ext_router.get("/{token}", response_class=HTMLResponse)
async def passenger_portal(
    token: str, request: Request,
    lang: str = Query("fr"),
    db: AsyncSession = Depends(get_db),
):
    booking = await _get_booking_by_token(token, db)

    # Load questionnaire forms for each passenger
    pax_forms = {}
    for pax in booking.passengers:
        form_result = await db.execute(
            select(PreBoardingForm).where(PreBoardingForm.passenger_id == pax.id)
        )
        pax_forms[pax.id] = form_result.scalar_one_or_none()

    return templates.TemplateResponse("passengers/external.html", {
        "request": request,
        "booking": booking,
        "document_types": DOCUMENT_TYPES,
        "document_statuses": DOCUMENT_STATUSES,
        "cabin_type_labels": CABIN_TYPE_LABELS,
        "pax_forms": pax_forms,
        "token": token,
        "lang": lang if lang in ("fr", "en") else "fr",
    })


# ═══════════════════════════════════════════════════════════════
#  UPLOAD DOCUMENT
# ═══════════════════════════════════════════════════════════════
@ext_router.post("/{token}/doc/{doc_id}/upload", response_class=HTMLResponse)
async def upload_document(
    token: str, doc_id: int, request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    booking = await _get_booking_by_token(token, db)

    doc = await db.get(PassengerDocument, doc_id)
    if not doc:
        raise HTTPException(404)

    # Verify doc belongs to a passenger in this booking
    pax_ids = [p.id for p in booking.passengers]
    if doc.passenger_id not in pax_ids:
        raise HTTPException(403, "Document non autorisé.")

    # Save file
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename)[1] if file.filename else ".pdf"
    safe_name = f"{doc.doc_type}_{doc.passenger_id}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    doc.filename = file.filename
    doc.file_path = file_path
    doc.status = "uploaded"
    await db.flush()

    return RedirectResponse(url=f"/passenger/{token}#docs", status_code=303)


# ═══════════════════════════════════════════════════════════════
#  UPDATE PASSENGER INFO (by passenger themselves)
# ═══════════════════════════════════════════════════════════════
@ext_router.post("/{token}/pax/{pax_id}/update", response_class=HTMLResponse)
async def external_pax_update(
    token: str, pax_id: int, request: Request,
    first_name: str = Form(...), last_name: str = Form(...),
    email: str = Form(""), phone: str = Form(""),
    date_of_birth: str = Form(""), nationality: str = Form(""),
    passport_number: str = Form(""),
    emergency_contact_name: str = Form(""), emergency_contact_phone: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    booking = await _get_booking_by_token(token, db)

    pax_ids = [p.id for p in booking.passengers]
    if pax_id not in pax_ids:
        raise HTTPException(403)

    pax = await db.get(Passenger, pax_id)
    pax.first_name = first_name.strip()
    pax.last_name = last_name.strip()
    pax.email = email.strip() or None
    pax.phone = phone.strip() or None
    pax.date_of_birth = datetime.strptime(date_of_birth, "%Y-%m-%d").date() if date_of_birth.strip() else pax.date_of_birth
    pax.nationality = nationality.strip() or None
    pax.passport_number = passport_number.strip() or None
    pax.emergency_contact_name = emergency_contact_name.strip() or None
    pax.emergency_contact_phone = emergency_contact_phone.strip() or None
    await db.flush()

    return RedirectResponse(url=f"/passenger/{token}", status_code=303)


# ═══════════════════════════════════════════════════════════════
#  CROSSING BOOK PDF (external)
# ═══════════════════════════════════════════════════════════════
@ext_router.get("/{token}/book")
async def external_crossing_book(
    token: str, request: Request,
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response
    from app.models.crew import CrewAssignment
    from sqlalchemy.orm import selectinload as sl
    from app.utils.crossing_book import generate_crossing_book

    booking = await _get_booking_by_token(token, db)
    leg = booking.leg
    vessel = booking.vessel or (leg.vessel if leg else None)

    crew_result = await db.execute(
        select(CrewAssignment).options(selectinload(CrewAssignment.member))
        .where(CrewAssignment.vessel_id == vessel.id, CrewAssignment.status == "active")
    ) if vessel else None
    crew_list = crew_result.scalars().all() if crew_result else []

    legs_voyage = []
    if leg:
        lv_result = await db.execute(
            select(Leg).options(selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
            .where(Leg.vessel_id == leg.vessel_id, Leg.year == leg.year, Leg.status != "cancelled")
            .order_by(Leg.etd.asc().nulls_last(), Leg.leg_code.asc())
        )
        legs_voyage = lv_result.scalars().all()

    content = generate_crossing_book(leg, vessel, crew_list, [booking], legs_voyage)

    fname = f"Book_Traversee_{booking.reference}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ═══════════════════════════════════════════════════════════════
#  CROSSING BOOK - ENGLISH
# ═══════════════════════════════════════════════════════════════
@ext_router.get("/{token}/book/en")
async def external_crossing_book_en(
    token: str, request: Request,
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response
    from app.models.crew import CrewAssignment
    from app.utils.crossing_book import generate_crossing_book

    booking = await _get_booking_by_token(token, db)
    leg = booking.leg
    vessel = booking.vessel or (leg.vessel if leg else None)

    crew_result = await db.execute(
        select(CrewAssignment).options(selectinload(CrewAssignment.member))
        .where(CrewAssignment.vessel_id == vessel.id, CrewAssignment.status == "active")
    ) if vessel else None
    crew_list = crew_result.scalars().all() if crew_result else []

    legs_voyage = []
    if leg:
        lv_result = await db.execute(
            select(Leg).options(selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
            .where(Leg.vessel_id == leg.vessel_id, Leg.year == leg.year, Leg.status != "cancelled")
            .order_by(Leg.etd.asc().nulls_last(), Leg.leg_code.asc())
        )
        legs_voyage = lv_result.scalars().all()

    content = generate_crossing_book(leg, vessel, crew_list, [booking], legs_voyage, lang="en")

    fname = f"Crossing_Book_{booking.reference}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ═══════════════════════════════════════════════════════════════
#  PRE-BOARDING QUESTIONNAIRE
# ═══════════════════════════════════════════════════════════════
@ext_router.post("/{token}/pax/{pax_id}/questionnaire", response_class=HTMLResponse)
async def submit_questionnaire(
    token: str, pax_id: int, request: Request,
    sailed_before: str = Form(""),
    seasick: str = Form(""),
    willing_maneuvers: str = Form(""),
    chronic_conditions: str = Form(""),
    allergies: str = Form(""),
    daily_medication: str = Form(""),
    can_swim_50m: str = Form(""),
    dietary_requirements: str = Form(""),
    intolerances: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    booking = await _get_booking_by_token(token, db)
    pax_ids = [p.id for p in booking.passengers]
    if pax_id not in pax_ids:
        raise HTTPException(403)

    # Check if form exists
    existing = await db.execute(
        select(PreBoardingForm).where(PreBoardingForm.passenger_id == pax_id)
    )
    form = existing.scalar_one_or_none()

    if form:
        form.sailed_before = sailed_before or None
        form.seasick = seasick or None
        form.willing_maneuvers = willing_maneuvers or None
        form.chronic_conditions = chronic_conditions.strip() or None
        form.allergies = allergies.strip() or None
        form.daily_medication = daily_medication.strip() or None
        form.can_swim_50m = can_swim_50m or None
        form.dietary_requirements = dietary_requirements.strip() or None
        form.intolerances = intolerances.strip() or None
        form.signed = True
        form.signed_at = datetime.now()
    else:
        form = PreBoardingForm(
            passenger_id=pax_id,
            sailed_before=sailed_before or None,
            seasick=seasick or None,
            willing_maneuvers=willing_maneuvers or None,
            chronic_conditions=chronic_conditions.strip() or None,
            allergies=allergies.strip() or None,
            daily_medication=daily_medication.strip() or None,
            can_swim_50m=can_swim_50m or None,
            dietary_requirements=dietary_requirements.strip() or None,
            intolerances=intolerances.strip() or None,
            signed=True,
            signed_at=datetime.now(),
        )
        db.add(form)

    await db.flush()
    return RedirectResponse(url=f"/passenger/{token}#questionnaire", status_code=303)
