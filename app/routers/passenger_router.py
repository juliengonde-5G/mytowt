"""Passenger module router — booking-centric, leg+cabin mandatory."""
import secrets
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Request, Depends, Query, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.activity import log_activity, get_client_ip
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.templating import templates
from app.database import get_db
from app.auth import get_current_user
from app.permissions import require_permission
from app.models.user import User
from app.models.vessel import Vessel
from app.models.leg import Leg
from app.models.passenger import (
    Passenger, PassengerBooking, PassengerPayment, PassengerDocument,
    CabinPriceGrid, PassengerAuditLog,
    CABIN_CONFIG, CABIN_CONFIG_BY_VESSEL, get_cabin_config, get_cabin_label,
    BOOKING_STATUSES, PAYMENT_METHODS, PAYMENT_TYPES,
    PAYMENT_STATUSES, DOCUMENT_TYPES, DOCUMENT_STATUSES,
)
from app.models.portal_message import PortalMessage

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
    user: User = Depends(require_permission("passengers", "C")),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(PassengerBooking)
        .join(Leg, PassengerBooking.leg_id == Leg.id)
        .options(
            selectinload(PassengerBooking.passengers),
            selectinload(PassengerBooking.leg).selectinload(Leg.departure_port),
            selectinload(PassengerBooking.leg).selectinload(Leg.arrival_port),
            selectinload(PassengerBooking.leg).selectinload(Leg.vessel),
            selectinload(PassengerBooking.vessel),
            selectinload(PassengerBooking.payments),
        )
        .order_by(Leg.etd.asc().nulls_last(), PassengerBooking.created_at.desc())
    )
    if status:
        query = query.where(PassengerBooking.status == status)

    result = await db.execute(query)
    bookings = result.scalars().all()

    stats = {"total": len(bookings), "confirmed": 0, "paid": 0, "embarked": 0}
    for b in bookings:
        if b.status in stats:
            stats[b.status] += 1

    # Build cabin labels per booking
    cabin_labels = {}
    for b in bookings:
        vc = b.vessel.code if b.vessel else None
        cabin_labels[b.id] = get_cabin_label(vc, b.cabin_number)

    return templates.TemplateResponse("passengers/index.html", {
        "request": request, "user": user,
        "bookings": bookings, "stats": stats,
        "cabin_labels": cabin_labels,
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
    user: User = Depends(require_permission("passengers", "M")),
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

    # Build cabin data per vessel for JS
    cabins_by_vessel = {"default": [{"number": c["number"], "ref": c["ref"], "name": c["name"]} for c in CABIN_CONFIG]}
    for vc, cabs in CABIN_CONFIG_BY_VESSEL.items():
        cabins_by_vessel[str(vc)] = [{"number": c["number"], "ref": c["ref"], "name": c["name"]} for c in cabs]
    # Map leg_id → vessel_code
    leg_vessel_map = {str(l.id): str(l.vessel.code) for l in legs}

    # Build booked cabins per leg (for disabling already-taken cabins)
    booked_result = await db.execute(
        select(PassengerBooking.leg_id, PassengerBooking.cabin_number, PassengerBooking.cabin_numbers)
        .where(PassengerBooking.status != "cancelled")
    )
    booked_cabins = {}  # { "leg_id": [cabin_number, ...] }
    for row in booked_result.all():
        lid = str(row[0])
        if lid not in booked_cabins:
            booked_cabins[lid] = []
        if row[2]:  # cabin_numbers (comma-separated)
            for cn in row[2].split(","):
                cn = cn.strip()
                if cn:
                    booked_cabins[lid].append(int(cn))
        elif row[1]:  # legacy cabin_number
            booked_cabins[lid].append(row[1])

    return templates.TemplateResponse("passengers/booking_form.html", {
        "request": request, "user": user,
        "legs": legs,
        "cabin_config": CABIN_CONFIG,
        "pricing_json": pricing_json,
        "cabins_by_vessel_json": cabins_by_vessel,
        "leg_vessel_map_json": leg_vessel_map,
        "booked_cabins_json": booked_cabins,
        "active_module": "passengers",
    })


@router.post("/create", response_class=HTMLResponse)
async def booking_create_submit(
    request: Request,
    leg_id: int = Form(...),
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
    user: User = Depends(require_permission("passengers", "M")),
    db: AsyncSession = Depends(get_db),
):
    # Get cabin_numbers from form (checkboxes)
    form = await request.form()
    cabin_nums = form.getlist("cabin_numbers")
    if not cabin_nums:
        raise HTTPException(400, "Veuillez sélectionner au moins une cabine.")
    cabin_nums_int = [int(c) for c in cabin_nums]
    cabin_numbers_str = ",".join(str(c) for c in cabin_nums_int)

    # Get leg and vessel
    leg = await db.get(Leg, leg_id)
    if not leg:
        raise HTTPException(400, "Leg introuvable")

    # Check cabins not already booked on this leg
    existing_result = await db.execute(
        select(PassengerBooking).where(
            PassengerBooking.leg_id == leg_id,
            PassengerBooking.status != "cancelled",
        )
    )
    existing_bookings = existing_result.scalars().all()
    already_booked = set()
    for eb in existing_bookings:
        already_booked.update(eb.cabin_list)
    conflicts = [c for c in cabin_nums_int if c in already_booked]
    if conflicts:
        raise HTTPException(400, f"Cabine(s) {', '.join(str(c) for c in conflicts)} déjà réservée(s) sur ce leg.")

    # Auto-price from grid (sum per cabin type)
    price_total = 0.0
    deposit_total = 0.0
    has_price = False
    for cn in cabin_nums_int:
        cabin_type = "double" if cn <= 2 else "twin"
        price_result = await db.execute(
            select(CabinPriceGrid).where(
                CabinPriceGrid.origin_locode == leg.departure_port_locode,
                CabinPriceGrid.destination_locode == leg.arrival_port_locode,
                CabinPriceGrid.cabin_type == cabin_type,
                CabinPriceGrid.is_active == True,
            )
        )
        price_entry = price_result.scalar_one_or_none()
        if price_entry:
            has_price = True
            p = float(price_entry.price)
            price_total += p
            deposit_total += round(p * price_entry.deposit_pct / 100, 2)

    price_deposit = round(deposit_total, 2) if has_price else None
    price_balance = round(price_total - deposit_total, 2) if has_price else None
    price_total_final = round(price_total, 2) if has_price else None

    booking = PassengerBooking(
        leg_id=leg_id,
        vessel_id=leg.vessel_id,
        cabin_number=cabin_nums_int[0],  # legacy compat
        cabin_numbers=cabin_numbers_str,
        reference=_gen_ref(),
        status="draft",
        booking_date=date.today(),
        price_total=price_total_final,
        price_deposit=price_deposit,
        price_balance=price_balance,
        contact_email=contact_email.strip() or None,
        contact_phone=contact_phone.strip() or None,
        notes=notes.strip() or None,
    )
    db.add(booking)
    await db.flush()
    await log_activity(db, user=user, action="create", module="passengers",
                       entity_type="booking", entity_id=booking.id,
                       entity_label=booking.reference,
                       ip_address=get_client_ip(request))

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

    # Notification
    from app.models.notification import Notification
    db.add(Notification(
        type="new_passenger_booking",
        title=f"Nouvelle réservation {booking.reference}",
        detail=f"{pax1_first.strip()} {pax1_last.strip()} — Cabine(s) {cabin_numbers_str}",
        link=f"/passengers/{booking.id}",
        booking_id=booking.id,
    ))
    await db.flush()

    return RedirectResponse(url=f"/passengers/{booking.id}", status_code=303)


# ═══════════════════════════════════════════════════════════════
#  DETAIL
# ═══════════════════════════════════════════════════════════════
@router.get("/{booking_id}", response_class=HTMLResponse)
async def booking_detail(
    booking_id: int, request: Request,
    user: User = Depends(require_permission("passengers", "C")),
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

    # Get real cabin label(s)
    vessel_code = booking.vessel.code if booking.vessel else None
    cabin_labels_list = [get_cabin_label(vessel_code, cn) for cn in booking.cabin_list]
    cabin_full_label = " / ".join(cabin_labels_list) if cabin_labels_list else "—"

    # Load portal messages
    msg_result = await db.execute(
        select(PortalMessage)
        .where(PortalMessage.booking_id == booking_id)
        .order_by(PortalMessage.created_at)
    )
    portal_messages = msg_result.scalars().all()
    unread_client_msgs = sum(1 for m in portal_messages if m.sender_type == "client" and not m.is_read)

    return templates.TemplateResponse("passengers/detail.html", {
        "request": request, "user": user,
        "booking": booking,
        "pax_forms": pax_forms,
        "cabin_full_label": cabin_full_label,
        "cabin_config": get_cabin_config(vessel_code),
        "booking_statuses": BOOKING_STATUSES,
        "payment_methods": PAYMENT_METHODS,
        "payment_types": PAYMENT_TYPES,
        "document_types": DOCUMENT_TYPES,
        "document_statuses": DOCUMENT_STATUSES,
        "active_module": "passengers",
        "portal_messages": portal_messages,
        "unread_client_msgs": unread_client_msgs,
    })


# ═══════════════════════════════════════════════════════════════
#  UPDATE STATUS
# ═══════════════════════════════════════════════════════════════
@router.post("/{booking_id}/status", response_class=HTMLResponse)
async def booking_update_status(
    booking_id: int, request: Request,
    status: str = Form(...),
    user: User = Depends(require_permission("passengers", "M")),
    db: AsyncSession = Depends(get_db),
):
    booking = await db.get(PassengerBooking, booking_id)
    if not booking:
        raise HTTPException(404)
    old_status = booking.status
    booking.status = status
    db.add(PassengerAuditLog(
        booking_id=booking_id, action="status_change",
        field_name="status", old_value=old_status, new_value=status,
        changed_by=user.full_name,
    ))
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
    user: User = Depends(require_permission("passengers", "M")),
    db: AsyncSession = Depends(get_db),
):
    pax = await db.get(Passenger, pax_id)
    if not pax:
        raise HTTPException(404)
    # Track changes for audit
    changes = []
    for field, new_val in [
        ("first_name", first_name.strip()), ("last_name", last_name.strip()),
        ("email", email.strip() or None), ("phone", phone.strip() or None),
        ("nationality", nationality.strip() or None), ("passport_number", passport_number.strip() or None),
        ("emergency_contact_name", emergency_contact_name.strip() or None),
        ("emergency_contact_phone", emergency_contact_phone.strip() or None),
    ]:
        old_val = getattr(pax, field, None)
        if str(old_val or '') != str(new_val or ''):
            changes.append((field, str(old_val or ''), str(new_val or '')))
    pax.first_name = first_name.strip()
    pax.last_name = last_name.strip()
    pax.email = email.strip() or None
    pax.phone = phone.strip() or None
    pax.date_of_birth = datetime.strptime(date_of_birth, "%Y-%m-%d").date() if date_of_birth.strip() else pax.date_of_birth
    pax.nationality = nationality.strip() or None
    pax.passport_number = passport_number.strip() or None
    pax.emergency_contact_name = emergency_contact_name.strip() or None
    pax.emergency_contact_phone = emergency_contact_phone.strip() or None
    for field, old_val, new_val in changes:
        db.add(PassengerAuditLog(
            booking_id=pax.booking_id, passenger_id=pax.id,
            action="pax_updated", field_name=field,
            old_value=old_val, new_value=new_val,
            changed_by=user.full_name,
        ))
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
    user: User = Depends(require_permission("passengers", "M")),
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
    user: User = Depends(require_permission("passengers", "M")),
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

    # Audit log
    db.add(PassengerAuditLog(
        booking_id=booking_id, action="payment_added",
        field_name=payment_type, old_value=None,
        new_value=f"{amount}€ ({payment_method})",
        changed_by=user.full_name,
    ))

    # Auto-update booking status to confirmed if draft
    if booking.status == "draft":
        booking.status = "confirmed"

    await db.flush()
    return RedirectResponse(url=f"/passengers/{booking_id}#payments", status_code=303)


@router.post("/payment/{payment_id}/status", response_class=HTMLResponse)
async def update_payment_status(
    payment_id: int, request: Request,
    status: str = Form(...),
    user: User = Depends(require_permission("passengers", "M")),
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
    user: User = Depends(require_permission("passengers", "M")),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(PassengerDocument, doc_id)
    if not doc:
        raise HTTPException(404)
    old_status = doc.status
    doc.status = status
    if notes.strip():
        doc.notes = notes.strip()
    if status == "validated":
        doc.reviewed_by = user.full_name
        doc.reviewed_at = func.now()
    await db.flush()
    pax = await db.get(Passenger, doc.passenger_id)
    db.add(PassengerAuditLog(
        booking_id=pax.booking_id, passenger_id=pax.id,
        action="doc_status_change", field_name=doc.doc_type,
        old_value=old_status, new_value=status,
        changed_by=user.full_name,
    ))
    await db.flush()
    return RedirectResponse(url=f"/passengers/{pax.booking_id}#documents", status_code=303)


# ═══════════════════════════════════════════════════════════════
#  DOCUMENT UPLOAD FROM BACKOFFICE
# ═══════════════════════════════════════════════════════════════
@router.post("/doc/{doc_id}/upload", response_class=HTMLResponse)
async def backoffice_upload_doc(
    doc_id: int, request: Request,
    file: UploadFile = File(...),
    user: User = Depends(require_permission("passengers", "M")),
    db: AsyncSession = Depends(get_db),
):
    import os, uuid
    doc = await db.get(PassengerDocument, doc_id)
    if not doc:
        raise HTTPException(404)

    upload_dir = "/app/uploads/passenger_docs"
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename)[1] if file.filename else ".pdf"
    safe_name = f"{doc.doc_type}_{doc.passenger_id}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(upload_dir, safe_name)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    doc.filename = file.filename
    doc.file_path = file_path
    doc.status = "uploaded"
    await db.flush()

    pax = await db.get(Passenger, doc.passenger_id)
    db.add(PassengerAuditLog(
        booking_id=pax.booking_id, passenger_id=pax.id,
        action="doc_uploaded_backoffice", field_name=doc.doc_type,
        old_value=None, new_value=file.filename,
        changed_by=user.full_name,
    ))
    await db.flush()
    return RedirectResponse(url=f"/passengers/{pax.booking_id}#documents", status_code=303)


# ═══════════════════════════════════════════════════════════════
#  DOCUMENT DOWNLOAD
# ═══════════════════════════════════════════════════════════════
@router.get("/doc/{doc_id}/download")
async def download_doc(
    doc_id: int, request: Request,
    user: User = Depends(require_permission("passengers", "C")),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import FileResponse
    doc = await db.get(PassengerDocument, doc_id)
    if not doc or not doc.file_path:
        raise HTTPException(404, "Document non trouvé")
    return FileResponse(doc.file_path, filename=doc.filename or f"document_{doc_id}")


# ═══════════════════════════════════════════════════════════════
#  PAYMENT EDIT (non-Revolut only)
# ═══════════════════════════════════════════════════════════════
@router.post("/payment/{payment_id}/edit", response_class=HTMLResponse)
async def edit_payment(
    payment_id: int, request: Request,
    payment_type: str = Form(...),
    payment_method: str = Form("virement"),
    amount: float = Form(...),
    due_date: str = Form(""),
    notes: str = Form(""),
    user: User = Depends(require_permission("passengers", "M")),
    db: AsyncSession = Depends(get_db),
):
    payment = await db.get(PassengerPayment, payment_id)
    if not payment:
        raise HTTPException(404)
    if payment.payment_method == "revolut":
        raise HTTPException(403, "Impossible de modifier un paiement CB Revolut")

    old_amount = float(payment.amount)
    payment.payment_type = payment_type
    payment.payment_method = payment_method
    payment.amount = amount
    payment.due_date = datetime.strptime(due_date, "%Y-%m-%d").date() if due_date.strip() else None
    payment.notes = notes.strip() or None
    await db.flush()

    db.add(PassengerAuditLog(
        booking_id=payment.booking_id, action="payment_edited",
        field_name=payment_type,
        old_value=f"{old_amount}€",
        new_value=f"{amount}€ ({payment_method})",
        changed_by=user.full_name,
    ))
    await db.flush()
    return RedirectResponse(url=f"/passengers/{payment.booking_id}#payments", status_code=303)


# ═══════════════════════════════════════════════════════════════
#  PAYMENT DELETE (non-Revolut only)
# ═══════════════════════════════════════════════════════════════
@router.post("/payment/{payment_id}/delete", response_class=HTMLResponse)
async def delete_payment(
    payment_id: int, request: Request,
    user: User = Depends(require_permission("passengers", "S")),
    db: AsyncSession = Depends(get_db),
):
    payment = await db.get(PassengerPayment, payment_id)
    if not payment:
        raise HTTPException(404)
    if payment.payment_method == "revolut":
        raise HTTPException(403, "Impossible de supprimer un paiement CB Revolut")

    booking_id = payment.booking_id
    db.add(PassengerAuditLog(
        booking_id=booking_id, action="payment_deleted",
        field_name=payment.payment_type,
        old_value=f"{float(payment.amount)}€ ({payment.payment_method})",
        new_value=None,
        changed_by=user.full_name,
    ))
    await db.delete(payment)
    await db.flush()
    return RedirectResponse(url=f"/passengers/{booking_id}#payments", status_code=303)


# ═══════════════════════════════════════════════════════════════
#  AUDIT HISTORY
# ═══════════════════════════════════════════════════════════════
@router.get("/{booking_id}/history", response_class=HTMLResponse)
async def booking_history(
    booking_id: int, request: Request,
    user: User = Depends(require_permission("passengers", "C")),
    db: AsyncSession = Depends(get_db),
):
    booking = await db.get(PassengerBooking, booking_id)
    if not booking:
        raise HTTPException(404)

    logs_result = await db.execute(
        select(PassengerAuditLog)
        .where(PassengerAuditLog.booking_id == booking_id)
        .order_by(PassengerAuditLog.changed_at.desc())
    )
    logs = logs_result.scalars().all()

    # Load passenger names for display
    pax_result = await db.execute(
        select(Passenger).where(Passenger.booking_id == booking_id)
    )
    pax_map = {p.id: p.full_name for p in pax_result.scalars().all()}

    return templates.TemplateResponse("passengers/history.html", {
        "request": request, "user": user,
        "booking": booking, "logs": logs, "pax_map": pax_map,
        "active_module": "passengers",
    })


# ═══════════════════════════════════════════════════════════════
#  CROSSING BOOK PDF
# ═══════════════════════════════════════════════════════════════
@router.get("/{booking_id}/book", response_class=HTMLResponse)
async def crossing_book_pdf(
    booking_id: int, request: Request,
    lang: str = Query("fr"),
    user: User = Depends(require_permission("passengers", "C")),
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


# ═══════════════════════════════════════════════════════════════
# BACKOFFICE MESSAGING
# ═══════════════════════════════════════════════════════════════

@router.post("/{booking_id}/messages/send", response_class=HTMLResponse)
async def backoffice_send_message(
    booking_id: int, request: Request,
    user: User = Depends(require_permission("passengers", "M")),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    message_text = form.get("message", "").strip()
    if message_text:
        msg = PortalMessage(
            booking_id=booking_id,
            sender_type="company",
            sender_name=user.username or "TOWT",
            message=message_text,
        )
        db.add(msg)
        await db.flush()
    return RedirectResponse(url=f"/passengers/{booking_id}#messaging", status_code=303)


@router.post("/{booking_id}/messages/read", response_class=HTMLResponse)
async def backoffice_mark_messages_read(
    booking_id: int, request: Request,
    user: User = Depends(require_permission("passengers", "M")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PortalMessage).where(
            PortalMessage.booking_id == booking_id,
            PortalMessage.sender_type == "client",
            PortalMessage.is_read == False,
        )
    )
    for msg in result.scalars().all():
        msg.is_read = True
    await db.flush()
    return RedirectResponse(url=f"/passengers/{booking_id}#messaging", status_code=303)
