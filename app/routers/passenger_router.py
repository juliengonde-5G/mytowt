"""Passenger module router — booking-centric, leg+cabin mandatory."""
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
from app.models.user import User
from app.models.vessel import Vessel
from app.models.leg import Leg
from app.models.passenger import (
    Passenger, PassengerBooking, PassengerPayment, PassengerDocument,
    CabinPriceGrid,
    CABIN_CONFIG, BOOKING_STATUSES, PAYMENT_METHODS, PAYMENT_TYPES,
    PAYMENT_STATUSES, DOCUMENT_TYPES, DOCUMENT_STATUSES,
)

router = APIRouter(prefix="/passengers", tags=["passengers"])


def _gen_ref():
    d = date.today().strftime("%Y%m%d")
    r = secrets.token_hex(2).upper()
    return f"PAX-{d}-{r}"


# ═══════════════════════════════════════════════════════════════
#  LIST
# ═══════════════════════════════════════════════════════════════
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def passenger_list(
    request: Request,
    status: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(PassengerBooking)
        .options(
            selectinload(PassengerBooking.passengers),
            selectinload(PassengerBooking.leg).selectinload(Leg.departure_port),
            selectinload(PassengerBooking.leg).selectinload(Leg.arrival_port),
            selectinload(PassengerBooking.leg).selectinload(Leg.vessel),
            selectinload(PassengerBooking.vessel),
            selectinload(PassengerBooking.payments),
        )
        .order_by(PassengerBooking.created_at.desc())
    )
    if status:
        query = query.where(PassengerBooking.status == status)

    result = await db.execute(query)
    bookings = result.scalars().all()

    stats = {"total": len(bookings), "confirmed": 0, "paid": 0, "embarked": 0}
    for b in bookings:
        if b.status in stats:
            stats[b.status] += 1

    return templates.TemplateResponse("passengers/index.html", {
        "request": request, "user": user,
        "bookings": bookings, "stats": stats,
        "selected_status": status,
        "booking_statuses": BOOKING_STATUSES,
        "active_module": "passengers",
    })


# ═══════════════════════════════════════════════════════════════
#  CREATE BOOKING (step 1: leg + cabin → auto price)
# ═══════════════════════════════════════════════════════════════
@router.get("/create", response_class=HTMLResponse)
async def booking_create_form(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    legs_result = await db.execute(
        select(Leg).options(selectinload(Leg.departure_port), selectinload(Leg.arrival_port), selectinload(Leg.vessel))
        .where(Leg.status != "cancelled")
        .order_by(Leg.etd.asc().nulls_last(), Leg.leg_code.asc())
    )
    legs = legs_result.scalars().all()

    pricing_result = await db.execute(select(CabinPriceGrid).where(CabinPriceGrid.is_active == True))
    pricing_entries = pricing_result.scalars().all()
    pricing_json = [
        {"origin": p.origin_locode, "dest": p.destination_locode, "cabin": p.cabin_type,
         "price": float(p.price), "deposit_pct": p.deposit_pct}
        for p in pricing_entries
    ]

    return templates.TemplateResponse("passengers/booking_form.html", {
        "request": request, "user": user,
        "legs": legs,
        "cabin_config": CABIN_CONFIG,
        "pricing_json": pricing_json,
        "active_module": "passengers",
    })


@router.post("/create", response_class=HTMLResponse)
async def booking_create_submit(
    request: Request,
    leg_id: int = Form(...),
    cabin_number: int = Form(...),
    contact_email: str = Form(""),
    contact_phone: str = Form(""),
    pax1_first: str = Form(...), pax1_last: str = Form(...),
    pax1_email: str = Form(""), pax1_phone: str = Form(""),
    pax1_dob: str = Form(""), pax1_nationality: str = Form(""),
    pax1_passport: str = Form(""),
    pax1_emergency_name: str = Form(""), pax1_emergency_phone: str = Form(""),
    pax2_first: str = Form(""), pax2_last: str = Form(""),
    pax2_email: str = Form(""), pax2_phone: str = Form(""),
    pax2_dob: str = Form(""), pax2_nationality: str = Form(""),
    pax2_passport: str = Form(""),
    pax2_emergency_name: str = Form(""), pax2_emergency_phone: str = Form(""),
    notes: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get leg and vessel
    leg = await db.get(Leg, leg_id)
    if not leg:
        raise HTTPException(400, "Leg introuvable")

    # Auto-price from grid
    cabin_type = "double" if cabin_number <= 2 else "twin"
    price_result = await db.execute(
        select(CabinPriceGrid).where(
            CabinPriceGrid.origin_locode == leg.departure_port_locode,
            CabinPriceGrid.destination_locode == leg.arrival_port_locode,
            CabinPriceGrid.cabin_type == cabin_type,
            CabinPriceGrid.is_active == True,
        )
    )
    price_entry = price_result.scalar_one_or_none()

    price_total = float(price_entry.price) if price_entry else None
    deposit_pct = price_entry.deposit_pct if price_entry else 30
    price_deposit = round(price_total * deposit_pct / 100, 2) if price_total else None
    price_balance = round(price_total - price_deposit, 2) if price_total and price_deposit else None

    booking = PassengerBooking(
        leg_id=leg_id,
        vessel_id=leg.vessel_id,
        cabin_number=cabin_number,
        reference=_gen_ref(),
        status="draft",
        booking_date=date.today(),
        price_total=price_total,
        price_deposit=price_deposit,
        price_balance=price_balance,
        contact_email=contact_email.strip() or None,
        contact_phone=contact_phone.strip() or None,
        notes=notes.strip() or None,
    )
    db.add(booking)
    await db.flush()

    # Add passenger 1 (mandatory)
    pax1 = Passenger(
        booking_id=booking.id,
        first_name=pax1_first.strip(), last_name=pax1_last.strip(),
        email=pax1_email.strip() or None, phone=pax1_phone.strip() or None,
        date_of_birth=datetime.strptime(pax1_dob, "%Y-%m-%d").date() if pax1_dob.strip() else None,
        nationality=pax1_nationality.strip() or None,
        passport_number=pax1_passport.strip() or None,
        emergency_contact_name=pax1_emergency_name.strip() or None,
        emergency_contact_phone=pax1_emergency_phone.strip() or None,
    )
    db.add(pax1)
    await db.flush()
    # Create docs for pax1
    for doc_code, _ in DOCUMENT_TYPES:
        db.add(PassengerDocument(passenger_id=pax1.id, doc_type=doc_code, status="missing"))

    # Add passenger 2 (optional)
    if pax2_first.strip() and pax2_last.strip():
        pax2 = Passenger(
            booking_id=booking.id,
            first_name=pax2_first.strip(), last_name=pax2_last.strip(),
            email=pax2_email.strip() or None, phone=pax2_phone.strip() or None,
            date_of_birth=datetime.strptime(pax2_dob, "%Y-%m-%d").date() if pax2_dob.strip() else None,
            nationality=pax2_nationality.strip() or None,
            passport_number=pax2_passport.strip() or None,
            emergency_contact_name=pax2_emergency_name.strip() or None,
            emergency_contact_phone=pax2_emergency_phone.strip() or None,
        )
        db.add(pax2)
        await db.flush()
        for doc_code, _ in DOCUMENT_TYPES:
            db.add(PassengerDocument(passenger_id=pax2.id, doc_type=doc_code, status="missing"))

    await db.flush()
    return RedirectResponse(url=f"/passengers/{booking.id}", status_code=303)


# ═══════════════════════════════════════════════════════════════
#  DETAIL
# ═══════════════════════════════════════════════════════════════
@router.get("/{booking_id}", response_class=HTMLResponse)
async def booking_detail(
    booking_id: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PassengerBooking).options(
            selectinload(PassengerBooking.passengers).selectinload(Passenger.documents),
            selectinload(PassengerBooking.leg).selectinload(Leg.departure_port),
            selectinload(PassengerBooking.leg).selectinload(Leg.arrival_port),
            selectinload(PassengerBooking.leg).selectinload(Leg.vessel),
            selectinload(PassengerBooking.vessel),
            selectinload(PassengerBooking.payments),
        ).where(PassengerBooking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404)

    # Load questionnaire forms
    from app.models.passenger import PreBoardingForm
    pax_forms = {}
    for pax in booking.passengers:
        form_result = await db.execute(
            select(PreBoardingForm).where(PreBoardingForm.passenger_id == pax.id)
        )
        pax_forms[pax.id] = form_result.scalar_one_or_none()

    return templates.TemplateResponse("passengers/detail.html", {
        "request": request, "user": user,
        "booking": booking,
        "pax_forms": pax_forms,
        "cabin_config": CABIN_CONFIG,
        "booking_statuses": BOOKING_STATUSES,
        "payment_methods": PAYMENT_METHODS,
        "payment_types": PAYMENT_TYPES,
        "document_types": DOCUMENT_TYPES,
        "document_statuses": DOCUMENT_STATUSES,
        "active_module": "passengers",
    })


# ═══════════════════════════════════════════════════════════════
#  UPDATE STATUS
# ═══════════════════════════════════════════════════════════════
@router.post("/{booking_id}/status", response_class=HTMLResponse)
async def booking_update_status(
    booking_id: int, request: Request,
    status: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    booking = await db.get(PassengerBooking, booking_id)
    if not booking:
        raise HTTPException(404)
    booking.status = status
    await db.flush()
    return RedirectResponse(url=f"/passengers/{booking_id}", status_code=303)


# ═══════════════════════════════════════════════════════════════
#  UPDATE PASSENGER
# ═══════════════════════════════════════════════════════════════
@router.post("/pax/{pax_id}/update", response_class=HTMLResponse)
async def passenger_update(
    pax_id: int, request: Request,
    first_name: str = Form(...), last_name: str = Form(...),
    email: str = Form(""), phone: str = Form(""),
    date_of_birth: str = Form(""), nationality: str = Form(""),
    passport_number: str = Form(""),
    emergency_contact_name: str = Form(""), emergency_contact_phone: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pax = await db.get(Passenger, pax_id)
    if not pax:
        raise HTTPException(404)
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
    return RedirectResponse(url=f"/passengers/{pax.booking_id}", status_code=303)


# ═══════════════════════════════════════════════════════════════
#  ADD SECOND PASSENGER
# ═══════════════════════════════════════════════════════════════
@router.post("/{booking_id}/add-passenger", response_class=HTMLResponse)
async def add_passenger(
    booking_id: int, request: Request,
    first_name: str = Form(...), last_name: str = Form(...),
    email: str = Form(""), phone: str = Form(""),
    date_of_birth: str = Form(""), nationality: str = Form(""),
    passport_number: str = Form(""),
    emergency_contact_name: str = Form(""), emergency_contact_phone: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    booking = await db.get(PassengerBooking, booking_id)
    if not booking:
        raise HTTPException(404)

    # Check capacity
    pax_count = await db.execute(
        select(func.count(Passenger.id)).where(Passenger.booking_id == booking_id)
    )
    if (pax_count.scalar() or 0) >= 2:
        raise HTTPException(400, "Cabine pleine (2 passagers maximum)")

    pax = Passenger(
        booking_id=booking_id,
        first_name=first_name.strip(), last_name=last_name.strip(),
        email=email.strip() or None, phone=phone.strip() or None,
        date_of_birth=datetime.strptime(date_of_birth, "%Y-%m-%d").date() if date_of_birth.strip() else None,
        nationality=nationality.strip() or None,
        passport_number=passport_number.strip() or None,
        emergency_contact_name=emergency_contact_name.strip() or None,
        emergency_contact_phone=emergency_contact_phone.strip() or None,
    )
    db.add(pax)
    await db.flush()
    for doc_code, _ in DOCUMENT_TYPES:
        db.add(PassengerDocument(passenger_id=pax.id, doc_type=doc_code, status="missing"))
    await db.flush()
    return RedirectResponse(url=f"/passengers/{booking_id}", status_code=303)


# ═══════════════════════════════════════════════════════════════
#  PAYMENTS
# ═══════════════════════════════════════════════════════════════
@router.post("/{booking_id}/payment", response_class=HTMLResponse)
async def add_payment(
    booking_id: int, request: Request,
    payment_type: str = Form(...),
    payment_method: str = Form("virement"),
    amount: float = Form(...),
    due_date: str = Form(""),
    notes: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    booking = await db.get(PassengerBooking, booking_id)
    if not booking:
        raise HTTPException(404)

    payment = PassengerPayment(
        booking_id=booking_id,
        payment_type=payment_type,
        payment_method=payment_method or "virement",
        amount=amount,
        status="sent",  # Auto "sent" for wire orders
        reference=booking.reference,
        due_date=datetime.strptime(due_date, "%Y-%m-%d").date() if due_date.strip() else None,
        notes=notes.strip() or None,
    )
    db.add(payment)

    # Auto-update booking status to confirmed if draft
    if booking.status == "draft":
        booking.status = "confirmed"

    await db.flush()
    return RedirectResponse(url=f"/passengers/{booking_id}#payments", status_code=303)


@router.post("/payment/{payment_id}/status", response_class=HTMLResponse)
async def update_payment_status(
    payment_id: int, request: Request,
    status: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payment = await db.get(PassengerPayment, payment_id)
    if not payment:
        raise HTTPException(404)
    payment.status = status
    if status == "received":
        payment.paid_date = date.today()
    await db.flush()

    # Auto-update booking status if all payments received
    if status == "received":
        booking = await db.get(PassengerBooking, payment.booking_id)
        if booking and booking.price_total:
            all_payments = await db.execute(
                select(PassengerPayment).where(PassengerPayment.booking_id == booking.id)
            )
            payments = all_payments.scalars().all()
            total_received = sum(float(p.amount) for p in payments if p.status == "received")
            if total_received >= float(booking.price_total) and booking.status in ("draft", "confirmed"):
                booking.status = "paid"
                await db.flush()

    return RedirectResponse(url=f"/passengers/{payment.booking_id}#payments", status_code=303)


# ═══════════════════════════════════════════════════════════════
#  DOCUMENT STATUS
# ═══════════════════════════════════════════════════════════════
@router.post("/doc/{doc_id}/status", response_class=HTMLResponse)
async def update_doc_status(
    doc_id: int, request: Request,
    status: str = Form(...),
    notes: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(PassengerDocument, doc_id)
    if not doc:
        raise HTTPException(404)
    doc.status = status
    if notes.strip():
        doc.notes = notes.strip()
    if status == "validated":
        doc.reviewed_by = user.full_name
        doc.reviewed_at = func.now()
    await db.flush()
    pax = await db.get(Passenger, doc.passenger_id)
    return RedirectResponse(url=f"/passengers/{pax.booking_id}#documents", status_code=303)


# ═══════════════════════════════════════════════════════════════
#  CROSSING BOOK PDF
# ═══════════════════════════════════════════════════════════════
@router.get("/{booking_id}/book", response_class=HTMLResponse)
async def crossing_book_pdf(
    booking_id: int, request: Request,
    lang: str = Query("fr"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response
    from app.models.crew import CrewAssignment
    from app.utils.crossing_book import generate_crossing_book

    result = await db.execute(
        select(PassengerBooking).options(
            selectinload(PassengerBooking.passengers),
            selectinload(PassengerBooking.leg).selectinload(Leg.departure_port),
            selectinload(PassengerBooking.leg).selectinload(Leg.arrival_port),
            selectinload(PassengerBooking.leg).selectinload(Leg.vessel),
            selectinload(PassengerBooking.vessel),
        ).where(PassengerBooking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404)

    leg = booking.leg
    vessel = booking.vessel or (leg.vessel if leg else None)

    # Crew
    crew_result = await db.execute(
        select(CrewAssignment).options(selectinload(CrewAssignment.member))
        .where(CrewAssignment.vessel_id == vessel.id, CrewAssignment.status == "active")
    ) if vessel else None
    crew_list = crew_result.scalars().all() if crew_result else []

    # Other legs for same vessel/year for itinerary
    legs_voyage = []
    if leg:
        lv_result = await db.execute(
            select(Leg).options(selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
            .where(Leg.vessel_id == leg.vessel_id, Leg.year == leg.year, Leg.status != "cancelled")
            .order_by(Leg.etd.asc().nulls_last(), Leg.leg_code.asc())
        )
        legs_voyage = lv_result.scalars().all()

    content = generate_crossing_book(leg, vessel, crew_list, [booking], legs_voyage, lang=lang if lang in ("fr", "en") else "fr")

    prefix = "Crossing_Book" if lang == "en" else "Book_Traversee"
    fname = f"{prefix}_{booking.reference}_{leg.leg_code if leg else ''}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )
