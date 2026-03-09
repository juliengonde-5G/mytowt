"""External passenger portal — accessible by token, no authentication."""
import os
import uuid
from datetime import datetime, date, timezone as tz
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
from app.models.portal_message import PortalMessage
from app.utils.portal_security import check_token_rate_limit, record_token_attempt, log_portal_access

ext_router = APIRouter(prefix="/passenger", tags=["passenger-external"])

# Legacy /boarding/ redirect — old links sent to passengers
boarding_redirect_router = APIRouter(prefix="/boarding", tags=["passenger-external"])


@boarding_redirect_router.get("/{token}")
async def boarding_redirect(token: str, request: Request):
    """Redirect legacy /boarding/{token} URLs to /passenger/{token}."""
    lang = request.query_params.get("lang", "fr")
    return RedirectResponse(url=f"/passenger/{token}?lang={lang}", status_code=301)


@boarding_redirect_router.get("/{token}/{path:path}")
async def boarding_redirect_subpage(token: str, path: str, request: Request):
    """Redirect legacy /boarding/{token}/xxx URLs to /passenger/{token}/xxx."""
    qs = f"?{request.query_params}" if request.query_params else ""
    return RedirectResponse(url=f"/passenger/{token}/{path}{qs}", status_code=301)


UPLOAD_DIR = "/app/uploads/passenger_docs"


async def _get_booking_by_token(token: str, db: AsyncSession, request: Request = None) -> PassengerBooking:
    if request:
        check_token_rate_limit(request)
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
        if request:
            record_token_attempt(request)
        raise HTTPException(404, "Réservation introuvable.")
    # Check token expiration
    if booking.token_expires_at and booking.token_expires_at < datetime.now(tz.utc):
        raise HTTPException(404, "Lien expiré.")
    # Audit trail
    if request:
        await log_portal_access(db, request, "passenger", token, booking_id=booking.id)
    return booking


async def _get_unread_count(booking_id: int, db: AsyncSession) -> int:
    from sqlalchemy import func
    result = await db.execute(
        select(func.count(PortalMessage.id)).where(
            PortalMessage.booking_id == booking_id,
            PortalMessage.sender_type == "company",
            PortalMessage.is_read == False,
        )
    )
    return result.scalar() or 0


def _lang(request, query_lang):
    lang = query_lang or request.query_params.get('lang', 'fr')
    return lang if lang in ('fr', 'en') else 'fr'


@ext_router.get("/{token}", response_class=HTMLResponse)
async def passenger_portal(token: str, request: Request, lang: str = Query("fr"), db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    lang = _lang(request, lang)
    unread = await _get_unread_count(booking.id, db)
    pax_forms = {}
    for pax in booking.passengers:
        form_result = await db.execute(select(PreBoardingForm).where(PreBoardingForm.passenger_id == pax.id))
        pax_forms[pax.id] = form_result.scalar_one_or_none()
    return templates.TemplateResponse("passengers/portal_home.html", {
        "request": request, "booking": booking, "document_types": DOCUMENT_TYPES,
        "cabin_type_labels": CABIN_TYPE_LABELS,
        "pax_forms": pax_forms, "token": token, "lang": lang,
        "active_page": "home", "unread_messages": unread,
    })


@ext_router.get("/{token}/admin", response_class=HTMLResponse)
async def passenger_admin(token: str, request: Request, lang: str = Query("fr"), db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    lang = _lang(request, lang)
    unread = await _get_unread_count(booking.id, db)
    pax_forms = {}
    for pax in booking.passengers:
        form_result = await db.execute(select(PreBoardingForm).where(PreBoardingForm.passenger_id == pax.id))
        pax_forms[pax.id] = form_result.scalar_one_or_none()
    return templates.TemplateResponse("passengers/portal_admin.html", {
        "request": request, "booking": booking, "document_types": DOCUMENT_TYPES,
        "document_statuses": DOCUMENT_STATUSES, "cabin_type_labels": CABIN_TYPE_LABELS,
        "pax_forms": pax_forms, "token": token, "lang": lang,
        "active_page": "admin", "unread_messages": unread,
    })


@ext_router.get("/{token}/vessel", response_class=HTMLResponse)
async def passenger_vessel(token: str, request: Request, lang: str = Query("fr"), db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    lang = _lang(request, lang)
    unread = await _get_unread_count(booking.id, db)
    vessel = booking.vessel or (booking.leg.vessel if booking.leg else None)
    return templates.TemplateResponse("passengers/portal_vessel.html", {
        "request": request, "booking": booking, "vessel": vessel,
        "token": token, "lang": lang, "active_page": "vessel", "unread_messages": unread,
    })


@ext_router.get("/{token}/voyage", response_class=HTMLResponse)
async def passenger_voyage(token: str, request: Request, lang: str = Query("fr"), db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    lang = _lang(request, lang)
    unread = await _get_unread_count(booking.id, db)
    leg = booking.leg
    vessel = booking.vessel or (leg.vessel if leg else None)
    crew_list = []
    if vessel:
        from app.models.crew import CrewAssignment
        crew_result = await db.execute(
            select(CrewAssignment).options(selectinload(CrewAssignment.member))
            .where(CrewAssignment.vessel_id == vessel.id, CrewAssignment.status == "active"))
        crew_list = crew_result.scalars().all()
    legs_voyage = []
    if leg:
        lv_result = await db.execute(
            select(Leg).options(selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
            .where(Leg.vessel_id == leg.vessel_id, Leg.year == leg.year, Leg.status != "cancelled")
            .order_by(Leg.etd.asc().nulls_last(), Leg.leg_code.asc()))
        legs_voyage = lv_result.scalars().all()
    return templates.TemplateResponse("passengers/portal_voyage.html", {
        "request": request, "booking": booking, "leg": leg, "vessel": vessel,
        "crew_list": crew_list, "legs_voyage": legs_voyage,
        "token": token, "lang": lang, "active_page": "voyage", "unread_messages": unread,
    })


@ext_router.get("/{token}/life", response_class=HTMLResponse)
async def passenger_life(token: str, request: Request, lang: str = Query("fr"), db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    lang = _lang(request, lang)
    unread = await _get_unread_count(booking.id, db)
    return templates.TemplateResponse("passengers/portal_life.html", {
        "request": request, "booking": booking,
        "token": token, "lang": lang, "active_page": "life", "unread_messages": unread,
    })


@ext_router.get("/{token}/safety", response_class=HTMLResponse)
async def passenger_safety(token: str, request: Request, lang: str = Query("fr"), db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    lang = _lang(request, lang)
    unread = await _get_unread_count(booking.id, db)
    vessel = booking.vessel or (booking.leg.vessel if booking.leg else None)
    return templates.TemplateResponse("passengers/portal_safety.html", {
        "request": request, "booking": booking, "vessel": vessel,
        "token": token, "lang": lang, "active_page": "safety", "unread_messages": unread,
    })


@ext_router.get("/{token}/passenger-docs", response_class=HTMLResponse)
async def passenger_docs_page(token: str, request: Request, lang: str = Query("fr"), db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    lang = _lang(request, lang)
    unread = await _get_unread_count(booking.id, db)
    return templates.TemplateResponse("passengers/portal_passenger_docs.html", {
        "request": request, "booking": booking, "document_types": DOCUMENT_TYPES,
        "token": token, "lang": lang, "active_page": "passenger-docs", "unread_messages": unread,
    })


@ext_router.get("/{token}/questionnaire", response_class=HTMLResponse)
async def passenger_questionnaire(token: str, request: Request, lang: str = Query("fr"), db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    lang = _lang(request, lang)
    unread = await _get_unread_count(booking.id, db)
    pax_forms = {}
    for pax in booking.passengers:
        form_result = await db.execute(select(PreBoardingForm).where(PreBoardingForm.passenger_id == pax.id))
        pax_forms[pax.id] = form_result.scalar_one_or_none()
    return templates.TemplateResponse("passengers/portal_questionnaire.html", {
        "request": request, "booking": booking, "pax_forms": pax_forms,
        "token": token, "lang": lang, "active_page": "questionnaire", "unread_messages": unread,
    })


@ext_router.get("/{token}/destination", response_class=HTMLResponse)
async def passenger_destination(token: str, request: Request, lang: str = Query("fr"), db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    lang = _lang(request, lang)
    unread = await _get_unread_count(booking.id, db)
    # Future: load destination_info from a port_info table or CMS
    destination_info = None
    return templates.TemplateResponse("passengers/portal_destination.html", {
        "request": request, "booking": booking, "destination_info": destination_info,
        "token": token, "lang": lang, "active_page": "destination", "unread_messages": unread,
    })


@ext_router.get("/{token}/privacy", response_class=HTMLResponse)
async def passenger_privacy(token: str, request: Request, lang: str = Query("fr"), db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    lang = _lang(request, lang)
    unread = await _get_unread_count(booking.id, db)
    return templates.TemplateResponse("passengers/portal_privacy.html", {
        "request": request, "booking": booking,
        "token": token, "lang": lang, "active_page": "privacy", "unread_messages": unread,
    })


@ext_router.get("/{token}/documents", response_class=HTMLResponse)
async def passenger_documents(token: str, request: Request, lang: str = Query("fr"), db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    lang = _lang(request, lang)
    unread = await _get_unread_count(booking.id, db)
    return templates.TemplateResponse("passengers/portal_docs.html", {
        "request": request, "booking": booking,
        "token": token, "lang": lang, "active_page": "docs", "unread_messages": unread,
    })


@ext_router.get("/{token}/messages", response_class=HTMLResponse)
async def passenger_messages(token: str, request: Request, lang: str = Query("fr"), db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    lang = _lang(request, lang)
    msg_result = await db.execute(
        select(PortalMessage).where(PortalMessage.booking_id == booking.id)
        .order_by(PortalMessage.created_at.asc()))
    messages = msg_result.scalars().all()
    for msg in messages:
        if msg.sender_type == "company" and not msg.is_read:
            msg.is_read = True
    await db.flush()
    return templates.TemplateResponse("passengers/portal_messages.html", {
        "request": request, "booking": booking, "messages": messages,
        "token": token, "lang": lang, "active_page": "messages", "unread_messages": 0,
    })


@ext_router.post("/{token}/messages/send", response_class=HTMLResponse)
async def send_message(token: str, request: Request, message: str = Form(...), lang: str = Query("fr"), db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    lang = _lang(request, lang)
    sender_name = booking.passengers[0].full_name if booking.passengers else "Passenger"
    db.add(PortalMessage(booking_id=booking.id, sender_type="client", sender_name=sender_name, message=message.strip()))
    # Notification
    from app.models.notification import Notification
    db.add(Notification(
        type="new_passenger_message",
        title=f"Message passager — {booking.reference}",
        detail=f"{sender_name}: {message.strip()[:100]}",
        link=f"/passengers/{booking.id}#messages",
        booking_id=booking.id,
    ))
    await db.flush()
    return RedirectResponse(url=f"/passenger/{token}/messages?lang={lang}", status_code=303)


# ═══════════════════════════════════════════════════════════════
#  PAYMENT RETURN — redirect from Revolut after payment
# ═══════════════════════════════════════════════════════════════
@ext_router.get("/{token}/payment-return", response_class=HTMLResponse)
async def payment_return(token: str, request: Request, payment_id: int = Query(0), lang: str = Query("fr"), db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    lang = _lang(request, lang)
    unread = await _get_unread_count(booking.id, db)

    payment = None
    payment_success = False
    if payment_id:
        from app.models.passenger import PassengerPayment
        payment = await db.get(PassengerPayment, payment_id)
        if payment and payment.booking_id == booking.id:
            # Try to refresh status from Revolut
            if payment.revolut_order_id:
                try:
                    from app.utils.revolut import get_order, map_revolut_state
                    order = await get_order(payment.revolut_order_id)
                    revolut_state = order.get("state", "")
                    payment.revolut_state = revolut_state
                    new_status = map_revolut_state(revolut_state)
                    payment.status = new_status
                    if new_status == "received" and not payment.paid_date:
                        from datetime import date as date_cls
                        payment.paid_date = date_cls.today()
                    await db.commit()
                    payment_success = (new_status == "received")
                except Exception:
                    payment_success = (payment.status == "received")
            else:
                payment_success = (payment.status == "received")

    return templates.TemplateResponse("passengers/portal_payment_return.html", {
        "request": request, "booking": booking, "payment": payment,
        "payment_success": payment_success,
        "token": token, "lang": lang, "active_page": "home", "unread_messages": unread,
    })


@ext_router.get("/{token}/payments", response_class=HTMLResponse)
async def portal_payments_page(token: str, request: Request, lang: str = Query("fr"), db: AsyncSession = Depends(get_db)):
    """Portal payments overview — shows pending payments with pay buttons."""
    booking = await _get_booking_by_token(token, db, request)
    lang = _lang(request, lang)
    unread = await _get_unread_count(booking.id, db)
    return templates.TemplateResponse("passengers/portal_payments.html", {
        "request": request, "booking": booking,
        "token": token, "lang": lang, "active_page": "payments", "unread_messages": unread,
    })


# ═══════════════════════════════════════════════════════════════
#  UPLOAD / UPDATE / QUESTIONNAIRE / BOOK (unchanged)
# ═══════════════════════════════════════════════════════════════
@ext_router.post("/{token}/doc/{doc_id}/upload", response_class=HTMLResponse)
async def upload_document(token: str, doc_id: int, request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    doc = await db.get(PassengerDocument, doc_id)
    if not doc: raise HTTPException(404)
    if doc.passenger_id not in [p.id for p in booking.passengers]: raise HTTPException(403)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename)[1] if file.filename else ".pdf"
    safe_name = f"{doc.doc_type}_{doc.passenger_id}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    content = await file.read()
    with open(file_path, "wb") as f: f.write(content)
    doc.filename = file.filename; doc.file_path = file_path; doc.status = "uploaded"
    await db.flush()
    return RedirectResponse(url=f"/passenger/{token}#docs", status_code=303)


@ext_router.post("/{token}/pax/{pax_id}/update", response_class=HTMLResponse)
async def external_pax_update(token: str, pax_id: int, request: Request,
    first_name: str = Form(...), last_name: str = Form(...),
    email: str = Form(""), phone: str = Form(""),
    date_of_birth: str = Form(""), nationality: str = Form(""),
    passport_number: str = Form(""),
    emergency_contact_name: str = Form(""), emergency_contact_phone: str = Form(""),
    db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    if pax_id not in [p.id for p in booking.passengers]: raise HTTPException(403)
    pax = await db.get(Passenger, pax_id)
    pax.first_name = first_name.strip(); pax.last_name = last_name.strip()
    pax.email = email.strip() or None; pax.phone = phone.strip() or None
    pax.date_of_birth = datetime.strptime(date_of_birth, "%Y-%m-%d").date() if date_of_birth.strip() else pax.date_of_birth
    pax.nationality = nationality.strip() or None; pax.passport_number = passport_number.strip() or None
    pax.emergency_contact_name = emergency_contact_name.strip() or None
    pax.emergency_contact_phone = emergency_contact_phone.strip() or None
    await db.flush()
    return RedirectResponse(url=f"/passenger/{token}", status_code=303)


@ext_router.get("/{token}/book")
async def external_crossing_book(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    from fastapi.responses import Response
    from app.models.crew import CrewAssignment
    from app.utils.crossing_book import generate_crossing_book
    booking = await _get_booking_by_token(token, db, request)
    leg = booking.leg; vessel = booking.vessel or (leg.vessel if leg else None)
    crew_result = await db.execute(
        select(CrewAssignment).options(selectinload(CrewAssignment.member))
        .where(CrewAssignment.vessel_id == vessel.id, CrewAssignment.status == "active")) if vessel else None
    crew_list = crew_result.scalars().all() if crew_result else []
    legs_voyage = []
    if leg:
        lv_result = await db.execute(
            select(Leg).options(selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
            .where(Leg.vessel_id == leg.vessel_id, Leg.year == leg.year, Leg.status != "cancelled")
            .order_by(Leg.etd.asc().nulls_last(), Leg.leg_code.asc()))
        legs_voyage = lv_result.scalars().all()
    content = generate_crossing_book(leg, vessel, crew_list, [booking], legs_voyage)
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=Book_Traversee_{booking.reference}.pdf"})


@ext_router.get("/{token}/book/en")
async def external_crossing_book_en(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    from fastapi.responses import Response
    from app.models.crew import CrewAssignment
    from app.utils.crossing_book import generate_crossing_book
    booking = await _get_booking_by_token(token, db, request)
    leg = booking.leg; vessel = booking.vessel or (leg.vessel if leg else None)
    crew_result = await db.execute(
        select(CrewAssignment).options(selectinload(CrewAssignment.member))
        .where(CrewAssignment.vessel_id == vessel.id, CrewAssignment.status == "active")) if vessel else None
    crew_list = crew_result.scalars().all() if crew_result else []
    legs_voyage = []
    if leg:
        lv_result = await db.execute(
            select(Leg).options(selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
            .where(Leg.vessel_id == leg.vessel_id, Leg.year == leg.year, Leg.status != "cancelled")
            .order_by(Leg.etd.asc().nulls_last(), Leg.leg_code.asc()))
        legs_voyage = lv_result.scalars().all()
    content = generate_crossing_book(leg, vessel, crew_list, [booking], legs_voyage, lang="en")
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=Crossing_Book_{booking.reference}.pdf"})


@ext_router.post("/{token}/pax/{pax_id}/questionnaire", response_class=HTMLResponse)
async def submit_questionnaire(token: str, pax_id: int, request: Request,
    sailed_before: str = Form(""), seasick: str = Form(""), willing_maneuvers: str = Form(""),
    chronic_conditions: str = Form(""), allergies: str = Form(""),
    daily_medication: str = Form(""), can_swim_50m: str = Form(""),
    dietary_requirements: str = Form(""), intolerances: str = Form(""),
    gdpr_consent: str = Form(""),
    db: AsyncSession = Depends(get_db)):
    booking = await _get_booking_by_token(token, db, request)
    if pax_id not in [p.id for p in booking.passengers]: raise HTTPException(403)
    existing = await db.execute(select(PreBoardingForm).where(PreBoardingForm.passenger_id == pax_id))
    form = existing.scalar_one_or_none()
    kwargs = dict(sailed_before=sailed_before or None, seasick=seasick or None,
        willing_maneuvers=willing_maneuvers or None, chronic_conditions=chronic_conditions.strip() or None,
        allergies=allergies.strip() or None, daily_medication=daily_medication.strip() or None,
        can_swim_50m=can_swim_50m or None, dietary_requirements=dietary_requirements.strip() or None,
        intolerances=intolerances.strip() or None, signed=True, signed_at=datetime.now())
    # Record GDPR consent on PreBoardingForm
    if gdpr_consent:
        kwargs["gdpr_consent"] = True
        kwargs["gdpr_consent_at"] = datetime.now(tz.utc)
        kwargs["gdpr_consent_version"] = "1.0"
    if form:
        for k, v in kwargs.items(): setattr(form, k, v)
    else:
        db.add(PreBoardingForm(passenger_id=pax_id, **kwargs))
    await db.flush()
    return RedirectResponse(url=f"/passenger/{token}#questionnaire", status_code=303)
