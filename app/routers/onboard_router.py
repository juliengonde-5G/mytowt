"""On Board module router — ex-Captain, renamed to On Board."""
import json
from datetime import datetime, timezone, date
from typing import Optional
from fastapi import APIRouter, Request, Depends, Query, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.templating import templates
from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.vessel import Vessel
from app.models.leg import Leg
from app.models.order import Order
from app.models.crew import CrewMember, CrewAssignment
from app.models.packing_list import PackingList, PackingListBatch
from app.models.onboard import (
    SofEvent, OnboardNotification, CargoDocument,
    SOF_EVENT_TYPES, CARGO_DOC_TYPES,
)
from app.utils.activity import log_activity

router = APIRouter(prefix="/onboard", tags=["onboard"])


# ═══════════════════════════════════════════════════════════════
#  MAIN PAGE
# ═══════════════════════════════════════════════════════════════
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def onboard_home(
    request: Request,
    vessel: Optional[int] = Query(None),
    leg_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.permissions import can_view
    if not can_view(user, "captain"):
        raise HTTPException(status_code=403)

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
    crew_onboard = []
    cargo_summary = {}
    pax_bookings = []
    sof_events = []
    notifications = []
    last_sof = None

    if vessel_obj:
        legs_result = await db.execute(
            select(Leg).options(
                selectinload(Leg.departure_port), selectinload(Leg.arrival_port),
            ).where(Leg.vessel_id == vessel_obj.id, Leg.year == current_year)
            .order_by(Leg.sequence)
        )
        legs = legs_result.scalars().all()

        # Select leg: explicit or auto-detect current
        if leg_id:
            current_leg = next((l for l in legs if l.id == leg_id), None)
        if not current_leg:
            for leg in legs:
                if leg.ata and not leg.atd:
                    current_leg = leg
                    break
            if not current_leg and legs:
                # Take next upcoming
                for leg in legs:
                    if not leg.ata:
                        current_leg = leg
                        break
                if not current_leg:
                    current_leg = legs[-1]

        if current_leg:
            # ─── CREW on board ───
            crew_result = await db.execute(
                select(CrewAssignment).options(selectinload(CrewAssignment.member))
                .where(
                    CrewAssignment.vessel_id == vessel_obj.id,
                    CrewAssignment.status == "active",
                ).order_by(CrewAssignment.member_id)
            )
            crew_onboard = crew_result.scalars().all()

            # ─── CARGO summary ───
            orders_result = await db.execute(
                select(Order).where(Order.leg_id == current_leg.id)
            )
            orders = orders_result.scalars().all()
            order_ids = [o.id for o in orders]

            total_palettes = sum(o.quantity_palettes or 0 for o in orders)
            total_orders = len(orders)

            batches = []
            if order_ids:
                pl_result = await db.execute(
                    select(PackingList).options(selectinload(PackingList.batches))
                    .where(PackingList.order_id.in_(order_ids))
                )
                pls = pl_result.scalars().all()
                for pl in pls:
                    batches.extend(pl.batches)

            total_weight = sum(b.weight_kg or 0 for b in batches)
            total_batch_palettes = sum(b.pallet_quantity or 0 for b in batches)
            goods_types = list(set(b.type_of_goods for b in batches if b.type_of_goods))

            cargo_summary = {
                "orders": total_orders,
                "palettes_ordered": total_palettes,
                "palettes_batches": total_batch_palettes,
                "weight_kg": total_weight,
                "goods_types": goods_types,
                "batches_count": len(batches),
            }

            # ─── SOF events ───
            sof_result = await db.execute(
                select(SofEvent).where(SofEvent.leg_id == current_leg.id)
                .order_by(SofEvent.event_date.asc().nulls_last(), SofEvent.event_time.asc().nulls_last(), SofEvent.id.asc())
            )
            sof_events = sof_result.scalars().all()
            last_sof = sof_events[-1] if sof_events else None

            # ─── Notifications ───
            notif_result = await db.execute(
                select(OnboardNotification).where(OnboardNotification.leg_id == current_leg.id)
                .order_by(OnboardNotification.created_at.desc())
            )
            notifications = notif_result.scalars().all()

            # ─── PASSENGERS for this leg ───
            from app.models.passenger import PassengerBooking, Passenger, PassengerDocument, DOCUMENT_TYPES, CABIN_CONFIG
            pax_result = await db.execute(
                select(PassengerBooking).options(
                    selectinload(PassengerBooking.passengers).selectinload(Passenger.documents),
                )
                .where(
                    PassengerBooking.leg_id == current_leg.id,
                    PassengerBooking.status.notin_(["cancelled"]),
                )
                .order_by(PassengerBooking.cabin_number)
            )
            pax_bookings = pax_result.scalars().all()

    return templates.TemplateResponse("onboard/index.html", {
        "request": request, "user": user,
        "vessels": vessels, "selected_vessel": selected_vessel, "vessel_obj": vessel_obj,
        "legs": legs, "current_leg": current_leg,
        "crew_onboard": crew_onboard,
        "cargo_summary": cargo_summary,
        "sof_events": sof_events, "last_sof": last_sof,
        "notifications": notifications,
        "pax_bookings": pax_bookings,
        "sof_event_types": SOF_EVENT_TYPES,
        "cargo_doc_types": CARGO_DOC_TYPES,
        "current_year": current_year,
        "active_module": "captain",
        "lang": user.language or "fr",
    })


# ═══════════════════════════════════════════════════════════════
#  SOF EVENTS
# ═══════════════════════════════════════════════════════════════
@router.post("/sof/add", response_class=HTMLResponse)
async def sof_add_event(
    request: Request,
    leg_id: int = Form(...),
    event_type: str = Form(...),
    event_label: str = Form(""),
    event_date: str = Form(""),
    event_time: str = Form(""),
    remarks: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Find label from type if not custom
    label = event_label.strip()
    if not label:
        label = next((l for c, l in SOF_EVENT_TYPES if c == event_type), event_type)

    evt = SofEvent(
        leg_id=leg_id,
        event_type=event_type,
        event_label=label,
        event_date=datetime.strptime(event_date, "%Y-%m-%d").date() if event_date else date.today(),
        event_time=event_time or None,
        remarks=remarks or None,
        created_by=user.full_name,
    )
    db.add(evt)
    await db.flush()
    await log_activity(db, user, "onboard", "create", "SofEvent", evt.id, f"SOF: {label}")

    # Find vessel for redirect
    leg = await db.get(Leg, leg_id)
    vessel_obj = await db.get(Vessel, leg.vessel_id) if leg else None
    vc = vessel_obj.code if vessel_obj else ""
    return RedirectResponse(url=f"/onboard?vessel={vc}&leg_id={leg_id}#sof", status_code=303)


@router.post("/sof/{event_id}/edit", response_class=HTMLResponse)
async def sof_edit_event(
    event_id: int, request: Request,
    event_label: str = Form(""),
    event_date: str = Form(""),
    event_time: str = Form(""),
    remarks: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    evt = await db.get(SofEvent, event_id)
    if not evt:
        raise HTTPException(404)
    if event_label.strip():
        evt.event_label = event_label.strip()
    if event_date:
        evt.event_date = datetime.strptime(event_date, "%Y-%m-%d").date()
    evt.event_time = event_time or evt.event_time
    evt.remarks = remarks if remarks is not None else evt.remarks
    await db.flush()
    await log_activity(db, user, "onboard", "update", "SofEvent", event_id, "Modification SOF")

    leg = await db.get(Leg, evt.leg_id)
    vessel_obj = await db.get(Vessel, leg.vessel_id) if leg else None
    vc = vessel_obj.code if vessel_obj else ""
    return RedirectResponse(url=f"/onboard?vessel={vc}&leg_id={evt.leg_id}#sof", status_code=303)


@router.delete("/sof/{event_id}", response_class=HTMLResponse)
async def sof_delete_event(
    event_id: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    evt = await db.get(SofEvent, event_id)
    if evt:
        await db.delete(evt)
        await db.flush()
        await log_activity(db, user, "onboard", "delete", "SofEvent", event_id, "Suppression SOF")
    return HTMLResponse(content="", status_code=200)


# ═══════════════════════════════════════════════════════════════
#  NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════
@router.post("/notifications/{notif_id}/dismiss", response_class=HTMLResponse)
async def dismiss_notification(
    notif_id: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    notif = await db.get(OnboardNotification, notif_id)
    if notif:
        notif.is_read = True
        await db.flush()
    return HTMLResponse(content="", status_code=200)


@router.post("/notifications/dismiss-all", response_class=HTMLResponse)
async def dismiss_all_notifications(
    request: Request,
    leg_id: int = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import update
    await db.execute(
        update(OnboardNotification)
        .where(OnboardNotification.leg_id == leg_id, OnboardNotification.is_read == False)
        .values(is_read=True)
    )
    await db.flush()
    leg = await db.get(Leg, leg_id)
    vessel_obj = await db.get(Vessel, leg.vessel_id) if leg else None
    vc = vessel_obj.code if vessel_obj else ""
    return RedirectResponse(url=f"/onboard?vessel={vc}&leg_id={leg_id}", status_code=303)


# ═══════════════════════════════════════════════════════════════
#  SOF EXPORT (Excel + PDF)
# ═══════════════════════════════════════════════════════════════
@router.get("/sof/{leg_id}/excel", response_class=StreamingResponse)
async def sof_export_excel(
    leg_id: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    leg = await db.get(Leg, leg_id)
    if not leg:
        raise HTTPException(404)
    vessel = await db.get(Vessel, leg.vessel_id)

    sof_result = await db.execute(
        select(SofEvent).where(SofEvent.leg_id == leg_id)
        .order_by(SofEvent.event_date.asc().nulls_last(), SofEvent.event_time.asc().nulls_last(), SofEvent.id.asc())
    )
    events = sof_result.scalars().all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Statement of Facts"

    # Header
    hdr_fill = PatternFill(start_color="095561", end_color="095561", fill_type="solid")
    hdr_font = Font(bold=True, color="FFFFFF", size=12)
    ws.merge_cells("A1:E1")
    ws["A1"] = "STATEMENT OF FACTS"
    ws["A1"].font = hdr_font
    ws["A1"].fill = hdr_fill
    ws["A1"].alignment = Alignment(horizontal="center")
    for c in ["B1", "C1", "D1", "E1"]:
        ws[c].fill = hdr_fill

    ws["A3"] = "Vessel:"
    ws["B3"] = vessel.name if vessel else ""
    ws["D3"] = "Voyage:"
    ws["E3"] = leg.leg_code

    # Table header
    headers = ["Event", "Date", "Time (LT)", "Remarks", "Recorded by"]
    row_font = Font(bold=True, color="FFFFFF", size=10)
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=5, column=col, value=h)
        cell.font = row_font
        cell.fill = PatternFill(start_color="095561", end_color="095561", fill_type="solid")

    for i, evt in enumerate(events, 6):
        ws.cell(row=i, column=1, value=evt.event_label)
        ws.cell(row=i, column=2, value=evt.event_date.strftime("%d/%m/%Y") if evt.event_date else "")
        ws.cell(row=i, column=3, value=evt.event_time or "")
        ws.cell(row=i, column=4, value=evt.remarks or "")
        ws.cell(row=i, column=5, value=evt.created_by or "")

    ws.column_dimensions["A"].width = 50
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 40
    ws.column_dimensions["E"].width = 20

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    fname = f"SOF_{leg.leg_code}_{date.today().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@router.get("/sof/{leg_id}/pdf", response_class=StreamingResponse)
async def sof_export_pdf(
    leg_id: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export SOF as PDF using reportlab."""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    leg_result = await db.execute(
        select(Leg).options(selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
        .where(Leg.id == leg_id)
    )
    leg = leg_result.scalar_one_or_none()
    if not leg:
        raise HTTPException(404)

    sof_result = await db.execute(
        select(SofEvent).where(SofEvent.leg_id == leg_id)
        .order_by(SofEvent.event_date.asc().nulls_last(), SofEvent.event_time.asc().nulls_last(), SofEvent.id.asc())
    )
    events = sof_result.scalars().all()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=15*mm, leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()
    elements = []

    # Title
    title_style = ParagraphStyle("SOFTitle", parent=styles["Heading1"], fontSize=16, textColor=colors.HexColor("#095561"), spaceAfter=6)
    elements.append(Paragraph("STATEMENT OF FACTS", title_style))

    # Header info
    info_style = ParagraphStyle("Info", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#555555"), spaceAfter=2)
    elements.append(Paragraph(f"<b>Vessel:</b> {leg.vessel.name if leg.vessel else ''} &nbsp;&nbsp; <b>Voyage:</b> {leg.leg_code}", info_style))
    elements.append(Paragraph(f"<b>From:</b> {leg.departure_port.name if leg.departure_port else ''} &nbsp;&nbsp; <b>To:</b> {leg.arrival_port.name if leg.arrival_port else ''}", info_style))
    elements.append(Spacer(1, 10*mm))

    # Table
    hdr_color = colors.HexColor("#095561")
    data = [["Event", "Date", "Time (LT)", "Remarks"]]
    for evt in events:
        data.append([
            evt.event_label,
            evt.event_date.strftime("%d/%m/%Y") if evt.event_date else "",
            evt.event_time or "",
            evt.remarks or "",
        ])

    if len(data) > 1:
        col_widths = [220, 70, 60, 180]
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), hdr_color),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(t)
    else:
        elements.append(Paragraph("No SOF events recorded.", info_style))

    # Footer
    elements.append(Spacer(1, 10*mm))
    footer_style = ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#aaaaaa"))
    elements.append(Paragraph(f"Generated on {date.today().strftime('%d/%m/%Y')} — TOWT Operations Platform", footer_style))

    doc.build(elements)
    buf.seek(0)

    fname = f"SOF_{leg.leg_code}_{date.today().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ═══════════════════════════════════════════════════════════════
#  CARGO DOCUMENT EXPORT (Word + PDF) + SOF historisation
# ═══════════════════════════════════════════════════════════════
def _build_doc_paragraphs(doc_data: dict, doc_type: str, prefill: dict) -> list:
    """Build a list of (label, value) pairs for document rendering."""
    # Common header fields
    rows = [
        ("Vessel", doc_data.get("vessel_name", prefill.get("vessel_name", ""))),
        ("Voyage No", doc_data.get("voyage_no", prefill.get("voyage_no", ""))),
    ]

    if doc_type == "NOR":
        rows += [
            ("To", doc_data.get("to_charterer", "")),
            ("Port", doc_data.get("port", "")),
            ("Date of Notice", doc_data.get("notice_date", "")),
            ("Time of Notice (LT)", doc_data.get("notice_time", "")),
            ("Cargo description", doc_data.get("cargo_desc", "")),
            ("Position", doc_data.get("position", "")),
            ("Remarks", doc_data.get("remarks", "")),
            ("Master", doc_data.get("master_name", "")),
        ]
    elif doc_type == "NOR_RT":
        rows += [
            ("To", doc_data.get("to_charterer", "")),
            ("Port", doc_data.get("port", "")),
            ("Reason for re-tendering", doc_data.get("reason", "")),
            ("Date", doc_data.get("notice_date", "")),
            ("Time (LT)", doc_data.get("notice_time", "")),
            ("Master", doc_data.get("master_name", "")),
        ]
    elif doc_type == "HOLDS_CERT":
        rows += [
            ("To", doc_data.get("to", "")),
            ("Port", doc_data.get("port", "")),
            ("Cargo to be loaded", doc_data.get("cargo", "")),
            ("Date of inspection", doc_data.get("inspection_date", "")),
            ("Holds inspected", doc_data.get("holds_list", "")),
            ("Result / Observations", doc_data.get("observations", "")),
            ("Chief Officer / Master", doc_data.get("officer_name", "")),
            ("Surveyor / Terminal", doc_data.get("surveyor", "")),
        ]
    elif doc_type in ("KEY_MEETING", "PRE_MEETING"):
        rows += [
            ("Port", doc_data.get("port", "")),
            ("Date", doc_data.get("meeting_date", "")),
            ("Attendees", doc_data.get("attendees", doc_data.get("terminal", ""))),
            ("Content", doc_data.get("key_points", doc_data.get("plan", ""))),
            ("Actions", doc_data.get("actions", doc_data.get("emergency", ""))),
        ]
    elif doc_type.startswith("LOP"):
        rows += [
            ("To", doc_data.get("to", "")),
            ("Port", doc_data.get("port", "")),
            ("Date", doc_data.get("lop_date", "")),
            ("Time", doc_data.get("lop_time", "")),
            ("Subject", doc_data.get("subject", "")),
            ("Details", doc_data.get("details", "")),
            ("Reserve", doc_data.get("reserve", "")),
            ("Master", doc_data.get("master_name", "")),
            ("Countersigned", doc_data.get("countersigned", "")),
        ]
    elif doc_type == "MATES_RECEIPT":
        rows += [
            ("Port of loading", doc_data.get("port_loading", "")),
            ("Date", doc_data.get("receipt_date", "")),
            ("Shipper", doc_data.get("shipper", "")),
            ("Cargo description", doc_data.get("cargo_desc", "")),
            ("Number of packages", doc_data.get("packages", "")),
            ("Gross weight (kg)", doc_data.get("weight", "")),
            ("Condition / Remarks", doc_data.get("condition", "")),
            ("Chief Officer", doc_data.get("officer_name", "")),
        ]
    else:
        rows += [
            ("Port", doc_data.get("port", "")),
            ("Date", doc_data.get("doc_date", "")),
            ("Content", doc_data.get("content", "")),
        ]

    return [(k, v) for k, v in rows if v]


@router.get("/doc/{doc_id}/export/word")
async def cargo_doc_export_word(
    doc_id: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export a cargo document as Word (.docx)."""
    from io import BytesIO
    from fastapi.responses import Response
    from docx import Document as DocxDocument
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    cargo_doc = await db.get(CargoDocument, doc_id)
    if not cargo_doc:
        raise HTTPException(404)

    leg_result = await db.execute(
        select(Leg).options(selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
        .where(Leg.id == cargo_doc.leg_id)
    )
    leg = leg_result.scalar_one_or_none()

    doc_data = json.loads(cargo_doc.data_json) if cargo_doc.data_json else {}
    prefill = {
        "vessel_name": leg.vessel.name if leg and leg.vessel else "",
        "voyage_no": leg.leg_code if leg else "",
    }
    rows = _build_doc_paragraphs(doc_data, cargo_doc.doc_type, prefill)
    doc_label = next((l for c, l in CARGO_DOC_TYPES if c == cargo_doc.doc_type), cargo_doc.doc_type)

    d = DocxDocument()

    title = d.add_heading(doc_label.upper(), level=1)
    for run in title.runs:
        run.font.color.rgb = RGBColor(0x09, 0x55, 0x61)

    d.add_paragraph(f"TOWT — {leg.vessel.name if leg and leg.vessel else ''} — {leg.leg_code if leg else ''}")

    if rows:
        table = d.add_table(rows=len(rows), cols=2)
        table.style = "Table Grid"
        for i, (label, value) in enumerate(rows):
            table.cell(i, 0).text = label
            table.cell(i, 1).text = str(value) if value else ""
            for p in table.cell(i, 0).paragraphs:
                for r in p.runs:
                    r.bold = True
                    r.font.size = Pt(10)

    d.add_paragraph("")
    sig = d.add_paragraph()
    sig.add_run("\n\nMaster signature: ____________________________").font.size = Pt(10)
    sig.add_run("\n\nDate: ____________________________").font.size = Pt(10)

    footer_p = d.add_paragraph()
    footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_run = footer_p.add_run(f"Generated {date.today().strftime('%d/%m/%Y')} — TOWT Operations Platform")
    footer_run.font.size = Pt(8)
    footer_run.font.color.rgb = RGBColor(0xAA, 0xAA, 0xAA)

    buf = BytesIO()
    d.save(buf)
    content = buf.getvalue()

    # Historize in SOF - do this BEFORE returning response
    sof_evt = SofEvent(
        leg_id=cargo_doc.leg_id,
        event_type="CUSTOM",
        event_label=f"Document generated: {doc_label} (Word)",
        event_date=date.today(),
        event_time=datetime.now().strftime("%H:%M"),
        remarks=f"Exported by {user.full_name}",
        created_by=user.full_name,
    )
    db.add(sof_evt)
    await db.flush()

    fname = f"{cargo_doc.doc_type}_{leg.leg_code}_{date.today().strftime('%Y%m%d')}.docx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@router.get("/doc/{doc_id}/export/pdf")
async def cargo_doc_export_pdf(
    doc_id: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export a cargo document as PDF."""
    from io import BytesIO
    from fastapi.responses import Response
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    cargo_doc = await db.get(CargoDocument, doc_id)
    if not cargo_doc:
        raise HTTPException(404)

    leg_result = await db.execute(
        select(Leg).options(selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
        .where(Leg.id == cargo_doc.leg_id)
    )
    leg = leg_result.scalar_one_or_none()

    doc_data = json.loads(cargo_doc.data_json) if cargo_doc.data_json else {}
    prefill = {
        "vessel_name": leg.vessel.name if leg and leg.vessel else "",
        "voyage_no": leg.leg_code if leg else "",
    }
    rows = _build_doc_paragraphs(doc_data, cargo_doc.doc_type, prefill)
    doc_label = next((l for c, l in CARGO_DOC_TYPES if c == cargo_doc.doc_type), cargo_doc.doc_type)

    buf = BytesIO()
    pdf_doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=15*mm, leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()
    elements = []

    hdr_color = colors.HexColor("#095561")
    title_style = ParagraphStyle("DocTitle", parent=styles["Heading1"], fontSize=16, textColor=hdr_color, spaceAfter=4)
    elements.append(Paragraph(doc_label.upper(), title_style))

    sub_style = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#555555"), spaceAfter=2)
    elements.append(Paragraph(f"TOWT — {leg.vessel.name if leg and leg.vessel else ''} — {leg.leg_code if leg else ''}", sub_style))
    elements.append(Spacer(1, 8*mm))

    data = [[k, str(v) if v else ""] for k, v in rows]
    if data:
        t = Table(data, colWidths=[130, 400])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f7f8")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(t)

    elements.append(Spacer(1, 15*mm))
    sig_style = ParagraphStyle("Sig", parent=styles["Normal"], fontSize=10, spaceAfter=8)
    elements.append(Paragraph("Master signature: ____________________________", sig_style))
    elements.append(Paragraph("Date: ____________________________", sig_style))

    elements.append(Spacer(1, 10*mm))
    footer_style = ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#aaaaaa"))
    elements.append(Paragraph(f"Generated on {date.today().strftime('%d/%m/%Y')} — TOWT Operations Platform", footer_style))

    pdf_doc.build(elements)
    content = buf.getvalue()

    # Historize in SOF - BEFORE returning
    sof_evt = SofEvent(
        leg_id=cargo_doc.leg_id,
        event_type="CUSTOM",
        event_label=f"Document generated: {doc_label} (PDF)",
        event_date=date.today(),
        event_time=datetime.now().strftime("%H:%M"),
        remarks=f"Exported by {user.full_name}",
        created_by=user.full_name,
    )
    db.add(sof_evt)
    await db.flush()

    fname = f"{cargo_doc.doc_type}_{leg.leg_code}_{date.today().strftime('%Y%m%d')}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ═══════════════════════════════════════════════════════════════
#  CARGO DOCUMENT GENERATION (form pages)
# ═══════════════════════════════════════════════════════════════
@router.get("/doc/{leg_id}/{doc_type}", response_class=HTMLResponse)
async def cargo_doc_form(
    leg_id: int, doc_type: str, request: Request,
    doc_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Show form page for filling a cargo document."""
    leg_result = await db.execute(
        select(Leg).options(
            selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port),
        ).where(Leg.id == leg_id)
    )
    leg = leg_result.scalar_one_or_none()
    if not leg:
        raise HTTPException(404)

    # Load existing doc if editing
    doc = None
    doc_data = {}
    if doc_id:
        doc = await db.get(CargoDocument, doc_id)
        if doc and doc.data_json:
            doc_data = json.loads(doc.data_json)

    # Pre-fill from leg data
    prefill = {
        "vessel_name": leg.vessel.name if leg.vessel else "",
        "voyage_no": leg.leg_code or "",
        "port": (leg.departure_port.name if leg.departure_port else "") + " / " + (leg.arrival_port.name if leg.arrival_port else ""),
        "port_dep": leg.departure_port.name if leg.departure_port else "",
        "port_dep_locode": leg.departure_port.locode if leg.departure_port else "",
        "port_arr": leg.arrival_port.name if leg.arrival_port else "",
        "port_arr_locode": leg.arrival_port.locode if leg.arrival_port else "",
        "etd": leg.etd.strftime("%Y-%m-%d") if leg.etd else "",
        "eta": leg.eta.strftime("%Y-%m-%d") if leg.eta else "",
        "date_today": date.today().strftime("%Y-%m-%d"),
    }

    # Load SOF events for this leg (for pre-filling)
    sof_result = await db.execute(
        select(SofEvent).where(SofEvent.leg_id == leg_id)
        .order_by(SofEvent.event_date.asc().nulls_last(), SofEvent.id.asc())
    )
    sof_events = sof_result.scalars().all()

    doc_label = next((l for c, l in CARGO_DOC_TYPES if c == doc_type), doc_type)

    return templates.TemplateResponse("onboard/doc_form.html", {
        "request": request, "user": user,
        "leg": leg, "doc_type": doc_type, "doc_label": doc_label,
        "doc": doc, "doc_data": doc_data, "prefill": prefill,
        "sof_events": sof_events,
        "active_module": "captain",
        "lang": user.language or "fr",
    })


@router.post("/doc/{leg_id}/{doc_type}/save", response_class=HTMLResponse)
async def cargo_doc_save(
    leg_id: int, doc_type: str, request: Request,
    doc_id: Optional[int] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save cargo document form data."""
    form = await request.form()
    data = {k: v for k, v in form.items() if k not in ("doc_id",)}

    doc_label = next((l for c, l in CARGO_DOC_TYPES if c == doc_type), doc_type)

    if doc_id:
        doc = await db.get(CargoDocument, doc_id)
        if doc:
            doc.data_json = json.dumps(data, default=str)
            doc.updated_at = func.now()
    else:
        doc = CargoDocument(
            leg_id=leg_id,
            doc_type=doc_type,
            title=doc_label,
            data_json=json.dumps(data, default=str),
            created_by=user.full_name,
        )
        db.add(doc)
    await db.flush()
    await log_activity(db, user, "onboard", "save_doc", "CargoDocument", doc.id if doc else None, f"Document {doc_type}")

    # Redirect back to the document form so export buttons become available
    saved_doc_id = doc.id if doc else None
    if not saved_doc_id:
        # Get the last inserted doc
        last = await db.execute(
            select(CargoDocument).where(
                CargoDocument.leg_id == leg_id, CargoDocument.doc_type == doc_type
            ).order_by(CargoDocument.id.desc())
        )
        saved = last.scalar_one_or_none()
        saved_doc_id = saved.id if saved else None

    return RedirectResponse(url=f"/onboard/doc/{leg_id}/{doc_type}?doc_id={saved_doc_id}", status_code=303)
