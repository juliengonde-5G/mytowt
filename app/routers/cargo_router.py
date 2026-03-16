from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from app.templating import templates
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.activity import log_activity, get_client_ip
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime, timezone
import io

from app.database import get_db
from app.auth import get_current_user
from app.permissions import require_permission
from app.models.user import User
from app.models.order import Order
from app.models.leg import Leg
from app.models.vessel import Vessel
from app.models.packing_list import PackingList, PackingListBatch, PackingListAudit
from app.models.portal_message import PortalMessage
from app.utils.notifications import notify_cargo_progress
from app.routers.kpi_router import compute_decarbonation, get_co2_variables
from app.models.crew import CrewAssignment, CrewMember
from app.i18n import get_lang_from_request

router = APIRouter(prefix="/cargo", tags=["cargo"])

IMO_CLASSES = [
    "Non-Dangerous Goods",
    "Class 1: Explosives",
    "Class 2: Gases",
    "Class 3: Flammable liquids",
    "Class 4: Flammable solids",
    "Class 5: Oxidizing substances",
    "Class 6: Toxic substances",
    "Class 7: Radioactive material",
    "Class 8: Corrosive substances",
    "Class 9: Miscellaneous",
]


def pf(val, default=None):
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return default
    try:
        s = val.replace(" ", "").replace("\u00a0", "")
        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return default


def pi(val, default=None):
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return default
    try:
        return int(val)
    except Exception:
        return default


# === EXPLOITATION VIEW ===
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def cargo_home(
    request: Request,
    status: Optional[str] = Query(None),
    user: User = Depends(require_permission("cargo", "C")),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(PackingList)
        .options(
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.vessel),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.departure_port),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.arrival_port),
            selectinload(PackingList.batches),
        )
        .order_by(PackingList.created_at.desc())
    )
    if status:
        query = query.where(PackingList.status == status)
    result = await db.execute(query)
    packing_lists = result.scalars().all()

    return templates.TemplateResponse("cargo/index.html", {
        "request": request, "user": user,
        "packing_lists": packing_lists,
        "selected_status": status,
        "active_module": "cargo",
    })


# === CREATE PACKING LIST FROM ORDER ===
@router.post("/create", response_class=HTMLResponse)
async def create_packing_list(
    request: Request,
    order_id: str = Form(...),
    user: User = Depends(require_permission("cargo", "M")),
    db: AsyncSession = Depends(get_db),
):
    oid = int(order_id)
    order_result = await db.execute(
        select(Order).options(
            selectinload(Order.leg).selectinload(Leg.vessel),
            selectinload(Order.leg).selectinload(Leg.departure_port),
            selectinload(Order.leg).selectinload(Leg.arrival_port),
        ).where(Order.id == oid)
    )
    order = order_result.scalar_one_or_none()
    if not order:
        raise HTTPException(404)

    # Check if packing list already exists
    existing = await db.execute(select(PackingList).where(PackingList.order_id == oid))
    if existing.scalar_one_or_none():
        url = "/cargo"
        if request.headers.get("HX-Request"):
            return HTMLResponse(content="", headers={"HX-Redirect": url})
        return RedirectResponse(url=url, status_code=303)

    pl = PackingList(order_id=oid)
    db.add(pl)
    await db.flush()
    await log_activity(db, user=user, action="create", module="cargo",
                       entity_type="packing_list", entity_id=pl.id,
                       entity_label=f"PL for {order.reference}",
                       ip_address=get_client_ip(request))

    # Create one default batch pre-filled with TOWT data
    batch = PackingListBatch(
        packing_list_id=pl.id,
        batch_number=1,
        booking_confirmation=order.reference,
        customer_name=order.client_name,
        freight_rate=order.unit_price,
    )
    if order.leg:
        leg = order.leg
        batch.voyage_id = leg.leg_code
        batch.vessel = leg.vessel.name if leg.vessel else None
        batch.loading_date = leg.etd.date() if leg.etd else None
        batch.pol_code = leg.departure_port.locode if leg.departure_port else None
        batch.pod_code = leg.arrival_port.locode if leg.arrival_port else None
        batch.pol_name = leg.departure_port.name if leg.departure_port else None
        batch.pod_name = leg.arrival_port.name if leg.arrival_port else None

    db.add(batch)
    await db.flush()

    url = "/cargo"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


# === VIEW PACKING LIST DETAIL (exploitation) ===
@router.get("/{pl_id}", response_class=HTMLResponse)
async def cargo_detail(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "C")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PackingList).options(
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.vessel),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.departure_port),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.arrival_port),
            selectinload(PackingList.batches),
        ).where(PackingList.id == pl_id)
    )
    pl = result.scalar_one_or_none()
    if not pl:
        raise HTTPException(404)

    # Load portal messages
    msg_result = await db.execute(
        select(PortalMessage)
        .where(PortalMessage.packing_list_id == pl_id)
        .order_by(PortalMessage.created_at)
    )
    portal_messages = msg_result.scalars().all()
    unread_client_msgs = sum(1 for m in portal_messages if m.sender_type == "client" and not m.is_read)

    return templates.TemplateResponse("cargo/detail.html", {
        "request": request, "user": user,
        "pl": pl, "imo_classes": IMO_CLASSES,
        "active_module": "cargo",
        "portal_messages": portal_messages,
        "unread_client_msgs": unread_client_msgs,
    })


# === LOCK / UNLOCK ===
@router.post("/{pl_id}/lock", response_class=HTMLResponse)
async def lock_packing_list(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "M")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PackingList).where(PackingList.id == pl_id))
    pl = result.scalar_one_or_none()
    if not pl:
        raise HTTPException(404)
    pl.status = "locked"
    pl.locked_at = datetime.now(timezone.utc)
    pl.locked_by = user.full_name or user.username
    await db.flush()
    url = f"/cargo/{pl_id}"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


@router.post("/{pl_id}/unlock", response_class=HTMLResponse)
async def unlock_packing_list(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "M")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PackingList).where(PackingList.id == pl_id))
    pl = result.scalar_one_or_none()
    if not pl:
        raise HTTPException(404)
    pl.status = "draft"
    pl.locked_at = None
    pl.locked_by = None
    await db.flush()
    url = f"/cargo/{pl_id}"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


# === DELETE PACKING LIST ===
@router.delete("/{pl_id}", response_class=HTMLResponse)
async def delete_packing_list(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "S")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PackingList).where(PackingList.id == pl_id))
    pl = result.scalar_one_or_none()
    if not pl:
        raise HTTPException(404)
    await db.delete(pl)
    await db.flush()
    url = "/cargo"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


# === EXCEL EXPORT ===
@router.get("/{pl_id}/excel")
async def export_excel(
    pl_id: int,
    user: User = Depends(require_permission("cargo", "C")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PackingList).options(
            selectinload(PackingList.order),
            selectinload(PackingList.batches),
        ).where(PackingList.id == pl_id)
    )
    pl = result.scalar_one_or_none()
    if not pl:
        raise HTTPException(404)

    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "LOADING_DATA"

    headers = [
        "VOYAGE_ID", "VESSEL", "LOADING_DATE", "POL_CODE", "POD_CODE",
        "POL_NAME", "POD_NAME", "CUSTOMER_NAME", "BOOKING_CONFIRMATION_TOWT",
        "FREIGHT_RATE_PER_PALLET_EURO", "CARGO_VALUE_USD", "FREIGHT_FORWARDER",
        "CODE_TRANSITAIRE", "SHIPPER_NAME", "WH_REFERENCES_SKU", "PO_NUMBER",
        "ADDITIONAL_REFERENCES", "CUSTOMER_BATCH_ID", "BILL_OF_LADING_ID",
        "NOTIFY_ADRESS", "CONSIGNEE_ORDER_ADRESS", "PALLET_TYPE",
        "TYPE_OF_GOODS", "BIO_PRODUCTS", "CASES_QUANTITY", "UNITS_PER_CASE",
        "IMO_PRODUCT_CLASS", "UN_NUMBER", "PALLET_QUANTITY_PER_BATCH",
        "STACKABLE", "HOLD", "LENGTH_CM", "WIDTH_CM", "HEIGHT_CM",
        "WEIGHT_KG", "SURFACE_M2", "VOLUME_M3",
    ]

    header_fill = PatternFill(start_color="095561", end_color="095561", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    yellow_fill = PatternFill(start_color="FFFFFF00", end_color="FFFFFF00", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin'),
    )

    yellow_cols = {
        "CUSTOMER_NAME", "FREIGHT_FORWARDER", "CODE_TRANSITAIRE", "SHIPPER_NAME",
        "PO_NUMBER", "CUSTOMER_BATCH_ID", "NOTIFY_ADRESS", "CONSIGNEE_ORDER_ADRESS",
        "PALLET_TYPE", "TYPE_OF_GOODS", "BIO_PRODUCTS", "CASES_QUANTITY",
        "UNITS_PER_CASE", "IMO_PRODUCT_CLASS", "PALLET_QUANTITY_PER_BATCH",
        "LENGTH_CM", "WIDTH_CM", "HEIGHT_CM", "WEIGHT_KG", "CARGO_VALUE_USD",
    }

    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border
        ws.column_dimensions[cell.column_letter].width = max(15, len(h) + 2)

    for row_idx, batch in enumerate(pl.batches, 2):
        data = {
            "VOYAGE_ID": batch.voyage_id,
            "VESSEL": batch.vessel,
            "LOADING_DATE": batch.loading_date.isoformat() if batch.loading_date else "",
            "POL_CODE": batch.pol_code,
            "POD_CODE": batch.pod_code,
            "POL_NAME": batch.pol_name,
            "POD_NAME": batch.pod_name,
            "CUSTOMER_NAME": batch.customer_name,
            "BOOKING_CONFIRMATION_TOWT": batch.booking_confirmation,
            "FREIGHT_RATE_PER_PALLET_EURO": batch.freight_rate,
            "CARGO_VALUE_USD": batch.cargo_value_usd,
            "FREIGHT_FORWARDER": batch.freight_forwarder,
            "CODE_TRANSITAIRE": batch.code_transitaire,
            "SHIPPER_NAME": batch.shipper_name,
            "WH_REFERENCES_SKU": batch.wh_references_sku,
            "PO_NUMBER": batch.po_number,
            "ADDITIONAL_REFERENCES": batch.additional_references,
            "CUSTOMER_BATCH_ID": batch.customer_batch_id,
            "BILL_OF_LADING_ID": batch.bill_of_lading_id,
            "NOTIFY_ADRESS": batch.notify_address,
            "CONSIGNEE_ORDER_ADRESS": batch.consignee_address,
            "PALLET_TYPE": batch.pallet_type,
            "TYPE_OF_GOODS": batch.type_of_goods,
            "BIO_PRODUCTS": batch.bio_products,
            "CASES_QUANTITY": batch.cases_quantity,
            "UNITS_PER_CASE": batch.units_per_case,
            "IMO_PRODUCT_CLASS": batch.imo_product_class,
            "UN_NUMBER": batch.un_number,
            "PALLET_QUANTITY_PER_BATCH": batch.pallet_quantity,
            "STACKABLE": batch.stackable,
            "HOLD": batch.hold,
            "LENGTH_CM": batch.length_cm,
            "WIDTH_CM": batch.width_cm,
            "HEIGHT_CM": batch.height_cm,
            "WEIGHT_KG": batch.weight_kg,
            "SURFACE_M2": batch.surface_m2,
            "VOLUME_M3": batch.volume_m3,
        }
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=data.get(h, ""))
            cell.border = thin_border
            if h in yellow_cols:
                cell.fill = yellow_fill

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"PACKING_LIST_{pl.order.reference}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# === PDF/DOCX BILL OF LADING (from TOWT template) ===
@router.get("/{pl_id}/bol")
async def bill_of_lading(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "C")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PackingList).options(
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.vessel),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.departure_port),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.arrival_port),
            selectinload(PackingList.batches),
        ).where(PackingList.id == pl_id)
    )
    pl = result.scalar_one_or_none()
    if not pl:
        raise HTTPException(404)

    import shutil, zipfile, re, os

    template_path = "/app/app/static/BILL_OF_LADING_TEMPLATE.docx"
    if not os.path.exists(template_path):
        # Fallback for local dev
        template_path = os.path.join(os.path.dirname(__file__), "..", "static", "BILL_OF_LADING_TEMPLATE.docx")
    if not os.path.exists(template_path):
        raise HTTPException(500, detail="Template BOL non trouvé")

    # Aggregate batch data
    total_cases = sum(b.cases_quantity or 0 for b in pl.batches)
    total_pallets = sum(b.pallet_quantity or 0 for b in pl.batches)
    total_weight = sum(b.weight_kg or 0 for b in pl.batches)
    goods_types = ", ".join(set(b.type_of_goods for b in pl.batches if b.type_of_goods))
    first = pl.batches[0] if pl.batches else None

    # Build replacement map
    shipper_full = first.shipper_name or "" if first else ""
    if first and first.shipper_address:
        shipper_full += "\n" + first.shipper_address
    replacements = {
        "SHIPPER_NAME": shipper_full,
        "BILL_OF_LADING_ID": f"{pl.order.reference}-BL",
        "BOOKING_CONFIRMATION_TOWT": pl.order.reference or "",
        "CONSIGNEE_ORDER_ADRESS": (first.consignee_address if first else "") or "",
        "NOTIFY_ADRESS": (first.notify_address if first else "") or "",
        "VESSEL": pl.order.leg.vessel.name if pl.order.leg and pl.order.leg.vessel else "",
        "VOYAGE_ID": pl.order.leg.leg_code if pl.order.leg else "",
        "POL_NAME": pl.order.leg.departure_port.name if pl.order.leg and pl.order.leg.departure_port else "",
        "POD_NAME": pl.order.leg.arrival_port.name if pl.order.leg and pl.order.leg.arrival_port else "",
        "Maximum_de_CASES_QUANTITY": str(total_cases) if total_cases else "—",
        "Nombre_de_PALLET_ID": str(total_pallets) if total_pallets else "—",
        "Maximum_de_WEIGHT_KG": str(int(total_weight)) if total_weight else "—",
        "TYPE_OF_GOODS": goods_types or "—",
    }

    # Clone template and do replacement in document.xml
    work_dir = f"/tmp/bol_{pl.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    os.makedirs(work_dir, exist_ok=True)
    output_path = os.path.join(work_dir, "output.docx")
    shutil.copy2(template_path, output_path)

    # Open docx (it's a zip), replace in document.xml
    import tempfile
    temp_docx = os.path.join(work_dir, "temp.docx")

    with zipfile.ZipFile(output_path, 'r') as zin:
        with zipfile.ZipFile(temp_docx, 'w') as zout:
            add_draft = (pl.status != "locked")
            header_rid = "rId50"

            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "word/document.xml":
                    content = data.decode('utf-8')
                    for key, val in replacements.items():
                        safe_val = (val or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        safe_val = safe_val.replace("\n", "</w:t><w:br/><w:t>")
                        content = content.replace(f"\u00ab{key}\u00bb", safe_val)

                    # Insert headerReference as FIRST child of the LAST sectPr
                    if add_draft:
                        header_ref = f'<w:headerReference w:type="default" r:id="{header_rid}"/>'
                        # Find the last <w:sectPr ...> tag and insert after its opening
                        import re as _re
                        # Match the last <w:sectPr with any attributes, ending with >
                        matches = list(_re.finditer(r'<w:sectPr[^>]*>', content))
                        if matches:
                            last_match = matches[-1]
                            insert_pos = last_match.end()
                            content = content[:insert_pos] + header_ref + content[insert_pos:]

                    data = content.encode('utf-8')

                elif item.filename == "word/_rels/document.xml.rels" and add_draft:
                    rels_content = data.decode('utf-8')
                    new_rel = f'<Relationship Id="{header_rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header_draft.xml"/>'
                    rels_content = rels_content.replace('</Relationships>', new_rel + '</Relationships>')
                    data = rels_content.encode('utf-8')

                elif item.filename == "[Content_Types].xml" and add_draft:
                    ct_content = data.decode('utf-8')
                    if 'header_draft.xml' not in ct_content:
                        override = '<Override PartName="/word/header_draft.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
                        ct_content = ct_content.replace('</Types>', override + '</Types>')
                    data = ct_content.encode('utf-8')

                zout.writestr(item, data)

            if add_draft:
                header_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                header_xml += '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w10="urn:schemas-microsoft-com:office:word">'
                header_xml += '<w:p><w:pPr><w:pStyle w:val="Header"/></w:pPr>'
                header_xml += '<w:r><w:rPr><w:noProof/></w:rPr><w:pict>'
                header_xml += '<v:shapetype id="_x0000_t136" coordsize="21600,21600" o:spt="136" adj="10800" path="m@7,l@8,m@5,21600l@6,21600e">'
                header_xml += '<v:formulas><v:f eqn="sum #0 0 10800"/><v:f eqn="prod #0 2 1"/><v:f eqn="sum 21600 0 @1"/><v:f eqn="sum 0 0 @2"/><v:f eqn="sum 21600 0 @3"/><v:f eqn="if @0 @3 0"/><v:f eqn="if @0 21600 @1"/><v:f eqn="if @0 0 @2"/><v:f eqn="if @0 @4 21600"/><v:f eqn="mid @5 @6"/><v:f eqn="mid @8 @5"/><v:f eqn="mid @7 @8"/><v:f eqn="mid @6 @7"/><v:f eqn="sum @6 0 @5"/></v:formulas>'
                header_xml += '<v:path textpathok="t" o:connecttype="custom" o:connectlocs="@9,0;@10,10800;@11,21600;@12,10800" o:connectangles="270,180,90,0"/>'
                header_xml += '<v:textpath on="t" fitshape="t"/>'
                header_xml += '<v:handles><v:h position="#0,bottomRight" xrange="6629,14971"/></v:handles>'
                header_xml += '<o:lock v:ext="edit" text="t" shapetype="t"/>'
                header_xml += '</v:shapetype>'
                header_xml += '<v:shape id="PowerPlusWaterMarkObject" o:spid="_x0000_s2049" type="#_x0000_t136"'
                header_xml += ' style="position:absolute;margin-left:0;margin-top:0;width:494.4pt;height:164.8pt;rotation:315;z-index:-251658752;mso-position-horizontal:center;mso-position-horizontal-relative:margin;mso-position-vertical:center;mso-position-vertical-relative:margin"'
                header_xml += ' o:allowincell="f" fillcolor="silver" stroked="f">'
                header_xml += '<v:fill opacity=".5"/>'
                header_xml += '<v:textpath style="font-family:&quot;Calibri&quot;;font-size:1pt" string="DRAFT"/>'
                header_xml += '<w10:wrap anchorx="margin" anchory="margin"/>'
                header_xml += '</v:shape>'
                header_xml += '</w:pict></w:r></w:p></w:hdr>'
                zout.writestr("word/header_draft.xml", header_xml.encode('utf-8'))

    # Read result
    with open(temp_docx, 'rb') as f:
        buffer = io.BytesIO(f.read())

    # Cleanup
    shutil.rmtree(work_dir, ignore_errors=True)

    filename = f"BOL_{pl.order.reference}_{datetime.now().strftime('%Y%m%d')}.docx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# === ADD BATCH (exploitation) ===
@router.post("/{pl_id}/add-batch", response_class=HTMLResponse)
async def add_batch(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "M")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PackingList).options(
            selectinload(PackingList.batches),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.vessel),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.departure_port),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.arrival_port),
        ).where(PackingList.id == pl_id)
    )
    pl = result.scalar_one_or_none()
    if not pl or pl.is_locked:
        raise HTTPException(403)

    first = pl.batches[0] if pl.batches else None
    batch = PackingListBatch(
        packing_list_id=pl.id,
        batch_number=len(pl.batches) + 1,
        voyage_id=first.voyage_id if first else None,
        vessel=first.vessel if first else None,
        loading_date=first.loading_date if first else None,
        pol_code=first.pol_code if first else None,
        pod_code=first.pod_code if first else None,
        pol_name=first.pol_name if first else None,
        pod_name=first.pod_name if first else None,
        booking_confirmation=first.booking_confirmation if first else None,
        freight_rate=first.freight_rate if first else None,
    )
    db.add(batch)
    await db.flush()

    url = f"/cargo/{pl_id}"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


# === AUDIT HELPER ===
CLIENT_FIELDS = [
    'customer_name', 'freight_forwarder', 'code_transitaire', 'shipper_name',
    'shipper_address', 'po_number', 'customer_batch_id', 'notify_address', 'consignee_address',
    'pallet_type', 'type_of_goods', 'bio_products', 'cases_quantity',
    'units_per_case', 'imo_product_class', 'pallet_quantity',
    'length_cm', 'width_cm', 'height_cm', 'weight_kg', 'cargo_value_usd',
]

async def audit_batch_changes(db: AsyncSession, pl_id: int, batch: PackingListBatch, form_data: dict, changed_by: str):
    """Record all field changes for a batch."""
    for field in CLIENT_FIELDS:
        old_val = getattr(batch, field, None)
        new_val = form_data.get(field)
        if new_val is not None:
            old_str = str(old_val) if old_val is not None else ""
            new_str = str(new_val).strip()
            if old_str != new_str and (old_str or new_str):
                db.add(PackingListAudit(
                    packing_list_id=pl_id,
                    batch_id=batch.id,
                    field_name=field,
                    old_value=old_str or None,
                    new_value=new_str or None,
                    changed_by=changed_by,
                ))


def apply_batch_fields(batch, form_data):
    """Apply client-editable fields to a batch from form data."""
    batch.customer_name = form_data.get('customer_name', batch.customer_name)
    batch.freight_forwarder = form_data.get('freight_forwarder', batch.freight_forwarder)
    batch.code_transitaire = form_data.get('code_transitaire', batch.code_transitaire)
    batch.shipper_name = form_data.get('shipper_name', batch.shipper_name)
    batch.shipper_address = form_data.get('shipper_address', batch.shipper_address)
    batch.po_number = form_data.get('po_number', batch.po_number)
    batch.customer_batch_id = form_data.get('customer_batch_id', batch.customer_batch_id)
    batch.notify_address = form_data.get('notify_address', batch.notify_address)
    batch.consignee_address = form_data.get('consignee_address', batch.consignee_address)
    batch.pallet_type = form_data.get('pallet_type', batch.pallet_type)
    batch.type_of_goods = form_data.get('type_of_goods', batch.type_of_goods)
    batch.bio_products = form_data.get('bio_products', batch.bio_products)
    batch.cases_quantity = pi(form_data.get('cases_quantity'))
    batch.units_per_case = pi(form_data.get('units_per_case'))
    batch.imo_product_class = form_data.get('imo_product_class', batch.imo_product_class)
    batch.pallet_quantity = pi(form_data.get('pallet_quantity'))
    batch.length_cm = pf(form_data.get('length_cm'))
    batch.width_cm = pf(form_data.get('width_cm'))
    batch.height_cm = pf(form_data.get('height_cm'))
    batch.weight_kg = pf(form_data.get('weight_kg'))
    batch.cargo_value_usd = pf(form_data.get('cargo_value_usd'))
    batch.compute_dimensions()


# === EXPLOITATION EDIT BATCHES (with audit) ===
@router.post("/{pl_id}/edit", response_class=HTMLResponse)
async def exploitation_edit_batches(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "M")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PackingList).options(selectinload(PackingList.batches))
        .where(PackingList.id == pl_id)
    )
    pl = result.scalar_one_or_none()
    if not pl:
        raise HTTPException(404)

    form = await request.form()
    changed_by = user.full_name or user.username

    for batch in pl.batches:
        prefix = f"batch_{batch.id}_"
        form_data = {k.replace(prefix, ''): v for k, v in form.items() if k.startswith(prefix)}
        if form_data:
            await audit_batch_changes(db, pl.id, batch, form_data, changed_by)
            apply_batch_fields(batch, form_data)

    await db.flush()
    url = f"/cargo/{pl_id}"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


# === AUDIT LOG VIEW ===
@router.get("/{pl_id}/history", response_class=HTMLResponse)
async def audit_history(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "C")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PackingList).options(selectinload(PackingList.order))
        .where(PackingList.id == pl_id)
    )
    pl = result.scalar_one_or_none()
    if not pl:
        raise HTTPException(404)

    audit_result = await db.execute(
        select(PackingListAudit).where(PackingListAudit.packing_list_id == pl_id)
        .order_by(PackingListAudit.changed_at.desc())
    )
    logs = audit_result.scalars().all()

    return templates.TemplateResponse("cargo/history.html", {
        "request": request, "user": user,
        "pl": pl, "logs": logs,
        "active_module": "cargo",
    })


# === EXCEL IMPORT ===
@router.post("/{pl_id}/import-excel", response_class=HTMLResponse)
async def import_excel(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "M")),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import UploadFile, File
    result = await db.execute(
        select(PackingList).options(
            selectinload(PackingList.batches),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.vessel),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.departure_port),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.arrival_port),
        ).where(PackingList.id == pl_id)
    )
    pl = result.scalar_one_or_none()
    if not pl or pl.is_locked:
        raise HTTPException(403)

    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(400, detail="Aucun fichier")

    import openpyxl
    content = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active

    # Read headers from row 1
    headers = [cell.value for cell in ws[1] if cell.value]
    header_map = {h: idx for idx, h in enumerate(headers)}

    changed_by = user.full_name or user.username

    # Map Excel columns to model fields
    EXCEL_TO_FIELD = {
        "CUSTOMER_NAME": "customer_name",
        "FREIGHT_FORWARDER": "freight_forwarder",
        "CODE_TRANSITAIRE": "code_transitaire",
        "SHIPPER_NAME": "shipper_name",
        "PO_NUMBER": "po_number",
        "CUSTOMER_BATCH_ID": "customer_batch_id",
        "NOTIFY_ADRESS": "notify_address",
        "CONSIGNEE_ORDER_ADRESS": "consignee_address",
        "PALLET_TYPE": "pallet_type",
        "TYPE_OF_GOODS": "type_of_goods",
        "BIO_PRODUCTS": "bio_products",
        "CASES_QUANTITY": "cases_quantity",
        "UNITS_PER_CASE": "units_per_case",
        "IMO_PRODUCT_CLASS": "imo_product_class",
        "PALLET_QUANTITY_PER_BATCH": "pallet_quantity",
        "LENGTH_CM": "length_cm",
        "WIDTH_CM": "width_cm",
        "HEIGHT_CM": "height_cm",
        "WEIGHT_KG": "weight_kg",
        "CARGO_VALUE_USD": "cargo_value_usd",
    }

    # Delete existing batches and recreate from Excel
    for b in pl.batches:
        await db.delete(b)
    await db.flush()

    first_batch = None
    batch_num = 0
    for row in ws.iter_rows(min_row=2, values_only=False):
        values = [cell.value for cell in row]
        if not any(values):
            continue
        batch_num += 1
        batch = PackingListBatch(packing_list_id=pl.id, batch_number=batch_num)

        # Pre-fill TOWT fields from order/leg
        batch.booking_confirmation = pl.order.reference
        batch.customer_name = pl.order.client_name
        batch.freight_rate = pl.order.unit_price
        if pl.order.leg:
            leg = pl.order.leg
            batch.voyage_id = leg.leg_code
            batch.vessel = leg.vessel.name if leg.vessel else None
            batch.loading_date = leg.etd.date() if leg.etd else None
            batch.pol_code = leg.departure_port.locode if leg.departure_port else None
            batch.pod_code = leg.arrival_port.locode if leg.arrival_port else None
            batch.pol_name = leg.departure_port.name if leg.departure_port else None
            batch.pod_name = leg.arrival_port.name if leg.arrival_port else None

        # Apply Excel data
        for excel_col, model_field in EXCEL_TO_FIELD.items():
            if excel_col in header_map:
                idx = header_map[excel_col]
                if idx < len(values):
                    val = values[idx]
                    if val is not None:
                        setattr(batch, model_field, val)

        batch.compute_dimensions()
        db.add(batch)

        # Audit log
        db.add(PackingListAudit(
            packing_list_id=pl.id, batch_id=None,
            field_name="excel_import",
            old_value=None,
            new_value=f"Batch #{batch_num} importé depuis Excel",
            changed_by=changed_by,
        ))

    await db.flush()
    url = f"/cargo/{pl_id}"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


# === VOYAGE EXPORT (all packing lists for a leg) ===
@router.get("/voyage/{leg_id}/excel")
async def export_voyage_excel(
    leg_id: int,
    user: User = Depends(require_permission("cargo", "C")),
    db: AsyncSession = Depends(get_db),
):
    leg_result = await db.execute(
        select(Leg).options(selectinload(Leg.vessel), selectinload(Leg.departure_port), selectinload(Leg.arrival_port))
        .where(Leg.id == leg_id)
    )
    leg = leg_result.scalar_one_or_none()
    if not leg:
        raise HTTPException(404)

    # Find all orders assigned to this leg, then their packing lists
    orders_result = await db.execute(
        select(Order).where(Order.leg_id == leg_id)
    )
    orders = orders_result.scalars().all()
    order_ids = [o.id for o in orders]

    if not order_ids:
        raise HTTPException(404, detail="Aucune commande sur ce voyage")

    pls_result = await db.execute(
        select(PackingList).options(selectinload(PackingList.batches), selectinload(PackingList.order))
        .where(PackingList.order_id.in_(order_ids))
    )
    packing_lists = pls_result.scalars().all()

    all_batches = []
    for pl in packing_lists:
        all_batches.extend(pl.batches)

    if not all_batches:
        raise HTTPException(404, detail="Aucun batch")

    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "LOADING_DATA"

    headers = [
        "VOYAGE_ID", "VESSEL", "LOADING_DATE", "POL_CODE", "POD_CODE",
        "POL_NAME", "POD_NAME", "CUSTOMER_NAME", "BOOKING_CONFIRMATION_TOWT",
        "FREIGHT_RATE_PER_PALLET_EURO", "CARGO_VALUE_USD", "FREIGHT_FORWARDER",
        "CODE_TRANSITAIRE", "SHIPPER_NAME", "PO_NUMBER", "CUSTOMER_BATCH_ID",
        "NOTIFY_ADRESS", "CONSIGNEE_ORDER_ADRESS", "PALLET_TYPE",
        "TYPE_OF_GOODS", "BIO_PRODUCTS", "CASES_QUANTITY", "UNITS_PER_CASE",
        "IMO_PRODUCT_CLASS", "PALLET_QUANTITY_PER_BATCH",
        "LENGTH_CM", "WIDTH_CM", "HEIGHT_CM", "WEIGHT_KG", "SURFACE_M2", "VOLUME_M3",
    ]

    header_fill = PatternFill(start_color="095561", end_color="095561", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border
        ws.column_dimensions[cell.column_letter].width = max(15, len(h) + 2)

    for row_idx, batch in enumerate(all_batches, 2):
        data = [
            batch.voyage_id, batch.vessel,
            batch.loading_date.isoformat() if batch.loading_date else "",
            batch.pol_code, batch.pod_code, batch.pol_name, batch.pod_name,
            batch.customer_name, batch.booking_confirmation, batch.freight_rate,
            batch.cargo_value_usd, batch.freight_forwarder, batch.code_transitaire,
            batch.shipper_name, batch.po_number, batch.customer_batch_id,
            batch.notify_address, batch.consignee_address, batch.pallet_type,
            batch.type_of_goods, batch.bio_products, batch.cases_quantity,
            batch.units_per_case, batch.imo_product_class, batch.pallet_quantity,
            batch.length_cm, batch.width_cm, batch.height_cm, batch.weight_kg,
            batch.surface_m2, batch.volume_m3,
        ]
        for col_idx, val in enumerate(data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val if val is not None else "")
            cell.border = thin_border

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"PACKING_LIST_VOYAGE_{leg.leg_code}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ═══════════════════════════════════════════════════════════════
# EXTERNAL CLIENT ACCESS (no auth required)
# ═══════════════════════════════════════════════════════════════

# ═══ BACKOFFICE CARGO MESSAGING ═══════════════════════════════

@router.post("/{pl_id}/messages/send", response_class=HTMLResponse)
async def backoffice_cargo_send_message(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "M")),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    message_text = form.get("message", "").strip()
    if message_text:
        msg = PortalMessage(
            packing_list_id=pl_id,
            sender_type="company",
            sender_name=user.username or "TOWT",
            message=message_text,
        )
        db.add(msg)
        await db.flush()
    return RedirectResponse(url=f"/cargo/{pl_id}#messaging", status_code=303)


@router.post("/{pl_id}/messages/read", response_class=HTMLResponse)
async def backoffice_cargo_mark_messages_read(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "M")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PortalMessage).where(
            PortalMessage.packing_list_id == pl_id,
            PortalMessage.sender_type == "client",
            PortalMessage.is_read == False,
        )
    )
    for msg in result.scalars().all():
        msg.is_read = True
    await db.flush()
    return RedirectResponse(url=f"/cargo/{pl_id}#messaging", status_code=303)


# ═══ HOLD ASSIGNMENT ═══════════════════════════════════════════
from app.models.hold import (
    HoldAssignment, HoldPlanConfirmation,
    HOLD_CODES, HOLD_SHORT_LABELS, HOLD_CAPACITIES, get_hold_capacity,
)


def suggest_hold_assignments(batches, existing_assignments, leg_id):
    """Auto-suggest hold assignments for batches based on pallet type and stackability.

    Strategy: fill holds from top to bottom (SUP → INT → INF), forward first (AV → AR).
    Distributes batches across holds to balance fill rates.
    """
    hold_order = ["SUP_AV", "SUP_AR", "INT_AV", "INT_AR", "INF_AV", "INF_AR"]

    # Track current usage per hold
    usage = {h: 0 for h in hold_order}
    for a in existing_assignments:
        usage[a.hold_code] = usage.get(a.hold_code, 0) + (a.pallet_quantity or 0)

    suggestions = []
    for batch in batches:
        qty = batch.pallet_quantity or 0
        if qty <= 0:
            continue
        # Already fully assigned?
        already_assigned = sum(
            a.pallet_quantity for a in existing_assignments if a.batch_id == batch.id
        )
        remaining = qty - already_assigned
        if remaining <= 0:
            continue

        ptype = (batch.pallet_type or "EPAL").upper()
        if ptype not in ("EPAL", "USPAL", "PORTPAL", "BB"):
            ptype = "EPAL"
        stackable = (batch.stackable or "").lower() in ("yes", "oui", "true", "1")

        # Find best hold: lowest fill rate with enough remaining capacity
        best_hold = None
        best_fill = 2.0  # > 100%
        for h in hold_order:
            cap = get_hold_capacity(h, ptype, stackable)
            if cap <= 0:
                continue
            current_fill = usage[h] / cap
            if current_fill < best_fill and (cap - usage[h]) > 0:
                best_hold = h
                best_fill = current_fill

        if best_hold:
            cap = get_hold_capacity(best_hold, ptype, stackable)
            assign_qty = min(remaining, cap - usage[best_hold])
            if assign_qty > 0:
                suggestions.append({
                    "batch_id": batch.id,
                    "hold_code": best_hold,
                    "pallet_quantity": assign_qty,
                    "pallet_type": ptype,
                    "is_stackable": stackable,
                })
                usage[best_hold] += assign_qty

    return suggestions


@router.get("/{pl_id}/holds", response_class=HTMLResponse)
async def cargo_holds(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "C")),
    db: AsyncSession = Depends(get_db),
):
    """Hold assignment page for a packing list."""
    result = await db.execute(
        select(PackingList).options(
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.vessel),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.departure_port),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.arrival_port),
            selectinload(PackingList.batches),
        ).where(PackingList.id == pl_id)
    )
    pl = result.scalar_one_or_none()
    if not pl:
        raise HTTPException(404)
    if not pl.order.leg_id:
        raise HTTPException(400, detail="Commande non affectée à un leg")

    leg = pl.order.leg
    leg_id = leg.id

    # Load existing hold assignments for this leg
    assign_result = await db.execute(
        select(HoldAssignment).where(HoldAssignment.leg_id == leg_id)
    )
    assignments = assign_result.scalars().all()

    # Load hold plan confirmation
    confirm_result = await db.execute(
        select(HoldPlanConfirmation).where(HoldPlanConfirmation.leg_id == leg_id)
    )
    confirmation = confirm_result.scalar_one_or_none()

    # Build hold summary (all assignments for this leg, not just this PL)
    hold_summary = {}
    for h_code, h_label in HOLD_CODES:
        h_assignments = [a for a in assignments if a.hold_code == h_code]
        total_qty = sum(a.pallet_quantity for a in h_assignments)
        # Use EPAL as default for capacity calculation
        cap_normal = get_hold_capacity(h_code, "EPAL", False)
        cap_stacked = get_hold_capacity(h_code, "EPAL", True)
        cap = cap_stacked if any(a.is_stackable for a in h_assignments) else cap_normal
        hold_summary[h_code] = {
            "label": h_label,
            "short": HOLD_SHORT_LABELS[h_code],
            "assignments": h_assignments,
            "total_palettes": total_qty,
            "capacity": cap if cap > 0 else cap_normal,
            "fill_pct": round(total_qty / cap * 100) if cap > 0 else 0,
        }

    # Current PL's batch assignments
    batch_assignments = {a.batch_id: a for a in assignments if a.batch_id in [b.id for b in pl.batches]}

    return templates.TemplateResponse("cargo/holds.html", {
        "request": request, "user": user,
        "pl": pl, "leg": leg,
        "hold_codes": HOLD_CODES,
        "hold_summary": hold_summary,
        "hold_capacities": HOLD_CAPACITIES,
        "assignments": assignments,
        "batch_assignments": batch_assignments,
        "confirmation": confirmation,
        "active_module": "cargo",
    })


@router.post("/{pl_id}/holds/suggest", response_class=HTMLResponse)
async def suggest_holds(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "M")),
    db: AsyncSession = Depends(get_db),
):
    """Auto-suggest hold assignments for unassigned batches."""
    result = await db.execute(
        select(PackingList).options(
            selectinload(PackingList.batches),
            selectinload(PackingList.order),
        ).where(PackingList.id == pl_id)
    )
    pl = result.scalar_one_or_none()
    if not pl or not pl.order.leg_id:
        raise HTTPException(404)

    leg_id = pl.order.leg_id
    assign_result = await db.execute(
        select(HoldAssignment).where(HoldAssignment.leg_id == leg_id)
    )
    existing = assign_result.scalars().all()

    suggestions = suggest_hold_assignments(pl.batches, existing, leg_id)
    changed_by = user.full_name or user.username

    for s in suggestions:
        ha = HoldAssignment(
            leg_id=leg_id,
            batch_id=s["batch_id"],
            hold_code=s["hold_code"],
            pallet_quantity=s["pallet_quantity"],
            pallet_type=s["pallet_type"],
            is_stackable=s["is_stackable"],
            assigned_by=changed_by,
        )
        db.add(ha)

    await db.flush()
    url = f"/cargo/{pl_id}/holds"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


@router.post("/{pl_id}/holds/save", response_class=HTMLResponse)
async def save_holds(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "M")),
    db: AsyncSession = Depends(get_db),
):
    """Save manual hold assignments from the form."""
    result = await db.execute(
        select(PackingList).options(
            selectinload(PackingList.batches),
            selectinload(PackingList.order),
        ).where(PackingList.id == pl_id)
    )
    pl = result.scalar_one_or_none()
    if not pl or not pl.order.leg_id:
        raise HTTPException(404)

    leg_id = pl.order.leg_id
    form = await request.form()
    changed_by = user.full_name or user.username

    # Delete existing assignments for this PL's batches
    batch_ids = [b.id for b in pl.batches]
    if batch_ids:
        existing_result = await db.execute(
            select(HoldAssignment).where(
                HoldAssignment.leg_id == leg_id,
                HoldAssignment.batch_id.in_(batch_ids),
            )
        )
        for old in existing_result.scalars().all():
            await db.delete(old)

    # Create new assignments from form data
    for batch in pl.batches:
        hold_code = form.get(f"hold_{batch.id}")
        qty_str = form.get(f"qty_{batch.id}")
        if hold_code and qty_str:
            qty = pi(qty_str, 0)
            if qty > 0:
                ptype = (batch.pallet_type or "EPAL").upper()
                if ptype not in ("EPAL", "USPAL", "PORTPAL", "BB"):
                    ptype = "EPAL"
                stackable = (batch.stackable or "").lower() in ("yes", "oui", "true", "1")
                ha = HoldAssignment(
                    leg_id=leg_id,
                    batch_id=batch.id,
                    hold_code=hold_code,
                    pallet_quantity=qty,
                    pallet_type=ptype,
                    is_stackable=stackable,
                    assigned_by=changed_by,
                )
                db.add(ha)

    await db.flush()
    url = f"/cargo/{pl_id}/holds"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


@router.post("/{pl_id}/holds/confirm", response_class=HTMLResponse)
async def confirm_hold_plan(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "M")),
    db: AsyncSession = Depends(get_db),
):
    """Confirm the hold plan for a leg."""
    result = await db.execute(
        select(PackingList).options(selectinload(PackingList.order))
        .where(PackingList.id == pl_id)
    )
    pl = result.scalar_one_or_none()
    if not pl or not pl.order.leg_id:
        raise HTTPException(404)

    leg_id = pl.order.leg_id
    form = await request.form()
    notes = form.get("notes", "")

    # Upsert confirmation
    existing = await db.execute(
        select(HoldPlanConfirmation).where(HoldPlanConfirmation.leg_id == leg_id)
    )
    conf = existing.scalar_one_or_none()
    if conf:
        conf.confirmed_by = user.full_name or user.username
        conf.confirmed_at = datetime.now(timezone.utc)
        conf.notes = notes
    else:
        conf = HoldPlanConfirmation(
            leg_id=leg_id,
            confirmed_by=user.full_name or user.username,
            notes=notes,
        )
        db.add(conf)

    await db.flush()
    url = f"/cargo/{pl_id}/holds"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


@router.get("/{pl_id}/holds/report", response_class=StreamingResponse)
async def hold_plan_report(
    pl_id: int, request: Request,
    user: User = Depends(require_permission("cargo", "C")),
    db: AsyncSession = Depends(get_db),
):
    """Generate PDF report of hold assignments for the leg."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    result = await db.execute(
        select(PackingList).options(
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.vessel),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.departure_port),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.arrival_port),
            selectinload(PackingList.batches),
        ).where(PackingList.id == pl_id)
    )
    pl = result.scalar_one_or_none()
    if not pl or not pl.order.leg_id:
        raise HTTPException(404)

    leg = pl.order.leg
    assign_result = await db.execute(
        select(HoldAssignment).where(HoldAssignment.leg_id == leg.id)
    )
    assignments = assign_result.scalars().all()

    confirm_result = await db.execute(
        select(HoldPlanConfirmation).where(HoldPlanConfirmation.leg_id == leg.id)
    )
    confirmation = confirm_result.scalar_one_or_none()

    # Build PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title2", parent=styles["Title"], fontSize=16, spaceAfter=6)
    subtitle_style = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=10, textColor=colors.grey)
    header_style = ParagraphStyle("Hdr", parent=styles["Normal"], fontSize=9, textColor=colors.white)
    cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8)

    elements = []
    elements.append(Paragraph(f"Plan de Cales — {leg.leg_code}", title_style))
    elements.append(Paragraph(
        f"{leg.vessel.name} · {leg.departure_port.name} → {leg.arrival_port.name} · "
        f"ETD {leg.etd.strftime('%d/%m/%Y') if leg.etd else '—'}",
        subtitle_style
    ))
    if confirmation:
        elements.append(Paragraph(
            f"Confirmé par {confirmation.confirmed_by} le {confirmation.confirmed_at.strftime('%d/%m/%Y %H:%M')}",
            subtitle_style
        ))
    elements.append(Spacer(1, 10*mm))

    # Table per hold
    for h_code, h_label in HOLD_CODES:
        h_assigns = [a for a in assignments if a.hold_code == h_code]
        if not h_assigns:
            continue
        total_qty = sum(a.pallet_quantity for a in h_assigns)

        elements.append(Paragraph(f"Cale {h_label} — {total_qty} palettes", styles["Heading3"]))

        data = [["Batch", "Client", "Marchandise", "Type palette", "Palettes", "Stackable"]]
        for a in h_assigns:
            # Find batch info
            batch = next((b for b in pl.batches if b.id == a.batch_id), None)
            if batch:
                data.append([
                    f"#{batch.batch_number}",
                    batch.customer_name or "—",
                    batch.type_of_goods or "—",
                    a.pallet_type or "—",
                    str(a.pallet_quantity),
                    "Oui" if a.is_stackable else "Non",
                ])
            else:
                data.append(["—", "—", "—", a.pallet_type or "—", str(a.pallet_quantity), "Oui" if a.is_stackable else "Non"])

        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#095561')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#ddd')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafb')]),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 6*mm))

    doc.build(elements)
    buffer.seek(0)

    filename = f"plan_cales_{leg.leg_code}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ═══ CLIENT EXTERNAL PORTAL ═══════════════════════════════════

ext_router = APIRouter(prefix="/p", tags=["packing-external"])

# ── Helpers ────────────────────────────────────────────────────
VALID_LANGS = ('fr', 'en', 'es', 'pt-br', 'vi')

def _lang(request):
    lang = request.query_params.get('lang') or request.cookies.get('towt_lang') or 'fr'
    return lang if lang in VALID_LANGS else 'fr'

async def _get_pl(token, db):
    result = await db.execute(
        select(PackingList).options(
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.vessel),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.departure_port),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.arrival_port),
            selectinload(PackingList.batches),
        ).where(PackingList.token == token)
    )
    pl = result.scalar_one_or_none()
    if not pl:
        raise HTTPException(404, detail="Lien invalide ou expiré")
    return pl

async def _unread_count(pl_id, db):
    r = await db.execute(
        select(func.count(PortalMessage.id)).where(
            PortalMessage.packing_list_id == pl_id,
            PortalMessage.sender_type == "company",
            PortalMessage.is_read == False,
        )
    )
    return r.scalar() or 0


# ── Page 1: Packing List (default) ────────────────────────────
@ext_router.get("/{token}", response_class=HTMLResponse)
async def client_portal_packing(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    pl = await _get_pl(token, db)
    lang = _lang(request)
    return templates.TemplateResponse("cargo/portal_packing.html", {
        "request": request, "pl": pl, "imo_classes": IMO_CLASSES,
        "lang": lang, "active_page": "packing",
        "unread_messages": await _unread_count(pl.id, db),
    })


# ── Page 2: Vessel ────────────────────────────────────────────
@ext_router.get("/{token}/vessel", response_class=HTMLResponse)
async def client_portal_vessel(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    pl = await _get_pl(token, db)
    lang = _lang(request)
    vessel = pl.order.leg.vessel if pl.order.leg else None
    return templates.TemplateResponse("cargo/portal_vessel.html", {
        "request": request, "pl": pl, "vessel": vessel,
        "lang": lang, "active_page": "vessel", "page_suffix": "/vessel",
        "unread_messages": await _unread_count(pl.id, db),
    })


# ── Page 3: Voyage ────────────────────────────────────────────
@ext_router.get("/{token}/voyage", response_class=HTMLResponse)
async def client_portal_voyage(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    pl = await _get_pl(token, db)
    lang = _lang(request)
    leg = pl.order.leg
    itinerary = []
    crew = []
    if leg:
        # Full itinerary for same vessel/year
        yr = leg.etd.year if leg.etd else None
        if yr:
            it_result = await db.execute(
                select(Leg).options(
                    selectinload(Leg.departure_port), selectinload(Leg.arrival_port)
                ).where(Leg.vessel_id == leg.vessel_id)
                .order_by(Leg.etd)
            )
            itinerary = it_result.scalars().all()
        # Crew on board
        from datetime import date
        crew_result = await db.execute(
            select(CrewAssignment).options(selectinload(CrewAssignment.member))
            .where(
                CrewAssignment.vessel_id == leg.vessel_id,
                CrewAssignment.embark_date <= (leg.etd.date() if leg.etd else date.today()),
                (CrewAssignment.disembark_date == None) | (CrewAssignment.disembark_date >= (leg.etd.date() if leg.etd else date.today())),
            )
        )
        crew = crew_result.scalars().all()
    return templates.TemplateResponse("cargo/portal_voyage.html", {
        "request": request, "pl": pl, "leg": leg,
        "itinerary": itinerary, "crew": crew,
        "lang": lang, "active_page": "voyage", "page_suffix": "/voyage",
        "unread_messages": await _unread_count(pl.id, db),
    })


# ── Page 4: Documents ─────────────────────────────────────────
@ext_router.get("/{token}/documents", response_class=HTMLResponse)
async def client_portal_docs(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    pl = await _get_pl(token, db)
    lang = _lang(request)
    return templates.TemplateResponse("cargo/portal_docs.html", {
        "request": request, "pl": pl,
        "lang": lang, "active_page": "docs", "page_suffix": "/documents",
        "unread_messages": await _unread_count(pl.id, db),
    })


# ── Page 5: Messages ──────────────────────────────────────────
@ext_router.get("/{token}/messages", response_class=HTMLResponse)
async def client_portal_messages(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    pl = await _get_pl(token, db)
    lang = _lang(request)
    # Load messages
    msg_result = await db.execute(
        select(PortalMessage)
        .where(PortalMessage.packing_list_id == pl.id)
        .order_by(PortalMessage.created_at)
    )
    messages = msg_result.scalars().all()
    # Mark company messages as read
    for m in messages:
        if m.sender_type == "company" and not m.is_read:
            m.is_read = True
    await db.flush()
    return templates.TemplateResponse("cargo/portal_messages.html", {
        "request": request, "pl": pl, "messages": messages,
        "lang": lang, "active_page": "messages", "page_suffix": "/messages",
        "unread_messages": 0,
    })


@ext_router.post("/{token}/messages/send", response_class=HTMLResponse)
async def client_portal_send_message(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    pl = await _get_pl(token, db)
    lang = _lang(request)
    form = await request.form()
    message_text = form.get("message", "").strip()
    if message_text:
        msg = PortalMessage(
            packing_list_id=pl.id,
            sender_type="client",
            sender_name=pl.order.client_name or "Client",
            message=message_text,
        )
        db.add(msg)
        # Notification
        from app.models.notification import Notification
        db.add(Notification(
            type="new_cargo_message",
            title=f"Message client — {pl.order.reference}",
            detail=f"{pl.order.client_name}: {message_text[:100]}",
            link=f"/cargo/{pl.id}#messages",
            packing_list_id=pl.id,
        ))
        await db.flush()
    return RedirectResponse(url=f"/p/{token}/messages?lang={lang}", status_code=303)


# ── Existing actions (batch add/save/delete) ──────────────────
@ext_router.post("/{token}/batch/add", response_class=HTMLResponse)
async def client_add_batch(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PackingList).options(
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.vessel),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.departure_port),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.arrival_port),
            selectinload(PackingList.batches),
        ).where(PackingList.token == token)
    )
    pl = result.scalar_one_or_none()
    if not pl or pl.is_locked:
        raise HTTPException(403)
    first = pl.batches[0] if pl.batches else None
    batch = PackingListBatch(
        packing_list_id=pl.id,
        batch_number=len(pl.batches) + 1,
        voyage_id=first.voyage_id if first else None,
        vessel=first.vessel if first else None,
        loading_date=first.loading_date if first else None,
        pol_code=first.pol_code if first else None,
        pod_code=first.pod_code if first else None,
        pol_name=first.pol_name if first else None,
        pod_name=first.pod_name if first else None,
        booking_confirmation=first.booking_confirmation if first else None,
        freight_rate=first.freight_rate if first else None,
    )
    db.add(batch)
    await db.flush()
    return RedirectResponse(url=f"/p/{token}", status_code=303)


@ext_router.post("/{token}/save", response_class=HTMLResponse)
async def client_save_batches(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PackingList).options(selectinload(PackingList.batches))
        .where(PackingList.token == token)
    )
    pl = result.scalar_one_or_none()
    if not pl or pl.is_locked:
        raise HTTPException(403)
    form = await request.form()
    for batch in pl.batches:
        prefix = f"batch_{batch.id}_"
        form_data = {k.replace(prefix, ''): v for k, v in form.items() if k.startswith(prefix)}
        if form_data:
            await audit_batch_changes(db, pl.id, batch, form_data, "Client")
            apply_batch_fields(batch, form_data)
    if pl.status == "draft":
        pl.status = "submitted"
    await db.flush()
    return RedirectResponse(url=f"/p/{token}?saved=1", status_code=303)


@ext_router.delete("/{token}/batch/{batch_id}", response_class=HTMLResponse)
async def client_delete_batch(token: str, batch_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PackingList).options(selectinload(PackingList.batches))
        .where(PackingList.token == token)
    )
    pl = result.scalar_one_or_none()
    if not pl or pl.is_locked:
        raise HTTPException(403)
    if len(pl.batches) <= 1:
        raise HTTPException(400, detail="Au moins 1 batch requis")
    batch_result = await db.execute(
        select(PackingListBatch).where(
            PackingListBatch.id == batch_id,
            PackingListBatch.packing_list_id == pl.id,
        )
    )
    batch = batch_result.scalar_one_or_none()
    if batch:
        await db.delete(batch)
        await db.flush()
    return RedirectResponse(url=f"/p/{token}", status_code=303)
