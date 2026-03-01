from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from app.templating import templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime, timezone
import io

from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.order import Order
from app.models.leg import Leg
from app.models.vessel import Vessel
from app.models.packing_list import PackingList, PackingListBatch, PackingListAudit
from app.i18n import get_lang_from_request
from app.utils.activity import log_activity

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
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
    await log_activity(db, user, "cargo", "create", "PackingList", pl.id, f"Packing list commande {order.reference}")

    url = "/cargo"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


# === VIEW PACKING LIST DETAIL (exploitation) ===
@router.get("/{pl_id}", response_class=HTMLResponse)
async def cargo_detail(
    pl_id: int, request: Request,
    user: User = Depends(get_current_user),
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

    return templates.TemplateResponse("cargo/detail.html", {
        "request": request, "user": user,
        "pl": pl, "imo_classes": IMO_CLASSES,
        "active_module": "cargo",
    })


# === LOCK / UNLOCK ===
@router.post("/{pl_id}/lock", response_class=HTMLResponse)
async def lock_packing_list(
    pl_id: int, request: Request,
    user: User = Depends(get_current_user),
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
    await log_activity(db, user, "cargo", "lock", "PackingList", pl_id, "Verrouillage packing list")
    url = f"/cargo/{pl_id}"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


@router.post("/{pl_id}/unlock", response_class=HTMLResponse)
async def unlock_packing_list(
    pl_id: int, request: Request,
    user: User = Depends(get_current_user),
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
    await log_activity(db, user, "cargo", "unlock", "PackingList", pl_id, "Déverrouillage packing list")
    url = f"/cargo/{pl_id}"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


# === DELETE PACKING LIST ===
@router.delete("/{pl_id}", response_class=HTMLResponse)
async def delete_packing_list(
    pl_id: int, request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PackingList).where(PackingList.id == pl_id))
    pl = result.scalar_one_or_none()
    if not pl:
        raise HTTPException(404)
    await db.delete(pl)
    await db.flush()
    await log_activity(db, user, "cargo", "delete", "PackingList", pl_id, "Suppression packing list")
    url = "/cargo"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


# === EXCEL EXPORT ===
@router.get("/{pl_id}/excel")
async def export_excel(
    pl_id: int,
    user: User = Depends(get_current_user),
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
        "CODE_TRANSITAIRE",
        "SHIPPER_NAME", "SHIPPER_ADDRESS", "SHIPPER_POSTAL", "SHIPPER_CITY", "SHIPPER_COUNTRY",
        "WH_REFERENCES_SKU", "PO_NUMBER",
        "ADDITIONAL_REFERENCES", "CUSTOMER_BATCH_ID", "BILL_OF_LADING_ID",
        "NOTIFY_NAME", "NOTIFY_ADDRESS", "NOTIFY_POSTAL", "NOTIFY_CITY", "NOTIFY_COUNTRY",
        "CONSIGNEE_NAME", "CONSIGNEE_ADDRESS", "CONSIGNEE_POSTAL", "CONSIGNEE_CITY", "CONSIGNEE_COUNTRY",
        "PALLET_TYPE", "TYPE_OF_GOODS", "DESCRIPTION_OF_GOODS", "BIO_PRODUCTS",
        "CASES_QUANTITY", "UNITS_PER_CASE",
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
        "CUSTOMER_NAME", "FREIGHT_FORWARDER", "CODE_TRANSITAIRE",
        "SHIPPER_NAME", "SHIPPER_ADDRESS", "SHIPPER_POSTAL", "SHIPPER_CITY", "SHIPPER_COUNTRY",
        "PO_NUMBER", "CUSTOMER_BATCH_ID",
        "NOTIFY_NAME", "NOTIFY_ADDRESS", "NOTIFY_POSTAL", "NOTIFY_CITY", "NOTIFY_COUNTRY",
        "CONSIGNEE_NAME", "CONSIGNEE_ADDRESS", "CONSIGNEE_POSTAL", "CONSIGNEE_CITY", "CONSIGNEE_COUNTRY",
        "PALLET_TYPE", "TYPE_OF_GOODS", "DESCRIPTION_OF_GOODS", "BIO_PRODUCTS",
        "CASES_QUANTITY", "UNITS_PER_CASE", "IMO_PRODUCT_CLASS",
        "PALLET_QUANTITY_PER_BATCH",
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
            "SHIPPER_ADDRESS": batch.shipper_address,
            "SHIPPER_POSTAL": batch.shipper_postal,
            "SHIPPER_CITY": batch.shipper_city,
            "SHIPPER_COUNTRY": batch.shipper_country,
            "WH_REFERENCES_SKU": batch.wh_references_sku,
            "PO_NUMBER": batch.po_number,
            "ADDITIONAL_REFERENCES": batch.additional_references,
            "CUSTOMER_BATCH_ID": batch.customer_batch_id,
            "BILL_OF_LADING_ID": batch.bill_of_lading_id,
            "NOTIFY_NAME": batch.notify_name,
            "NOTIFY_ADDRESS": batch.notify_address,
            "NOTIFY_POSTAL": batch.notify_postal,
            "NOTIFY_CITY": batch.notify_city,
            "NOTIFY_COUNTRY": batch.notify_country,
            "CONSIGNEE_NAME": batch.consignee_name,
            "CONSIGNEE_ADDRESS": batch.consignee_address,
            "CONSIGNEE_POSTAL": batch.consignee_postal,
            "CONSIGNEE_CITY": batch.consignee_city,
            "CONSIGNEE_COUNTRY": batch.consignee_country,
            "PALLET_TYPE": batch.pallet_type,
            "TYPE_OF_GOODS": batch.type_of_goods,
            "DESCRIPTION_OF_GOODS": batch.description_of_goods,
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
    user: User = Depends(get_current_user),
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

    # Description of goods: use first batch's description_of_goods if available, else type_of_goods
    description = ""
    if first and first.description_of_goods:
        description = first.description_of_goods
    elif goods_types:
        description = goods_types

    # Build structured addresses
    def format_address(name, addr, postal, city, country):
        parts = [p for p in [name, addr, f"{postal or ''} {city or ''}".strip(), country] if p]
        return "\n".join(parts)

    shipper_full = ""
    if first:
        shipper_full = format_address(
            first.shipper_name, first.shipper_address,
            first.shipper_postal, first.shipper_city, first.shipper_country)

    consignee_full = ""
    if first:
        consignee_full = format_address(
            first.consignee_name, first.consignee_address,
            first.consignee_postal, first.consignee_city, first.consignee_country)

    notify_full = ""
    if first:
        notify_full = format_address(
            first.notify_name, first.notify_address,
            first.notify_postal, first.notify_city, first.notify_country)

    # BL number: TUAW_{voyage_id}_{bl_no}
    voyage_id = pl.order.leg.leg_code if pl.order.leg else ""
    bl_no = f"TUAW_{voyage_id}_{pl.id}"

    # Packages format: XX cases stowed on YY pallets of GOODS
    packages_desc = ""
    if total_cases and total_pallets:
        packages_desc = f"{total_cases} cases stowed on {total_pallets} pallets of {goods_types}"
    elif total_pallets:
        packages_desc = f"{total_pallets} pallets of {goods_types}"

    # Build replacement map
    replacements = {
        "SHIPPER_NAME": shipper_full,
        "BILL_OF_LADING_ID": bl_no,
        "BOOKING_CONFIRMATION_TOWT": pl.order.reference or "",
        "CONSIGNEE_ORDER_ADRESS": consignee_full,
        "NOTIFY_ADRESS": notify_full,
        "VESSEL": pl.order.leg.vessel.name if pl.order.leg and pl.order.leg.vessel else "",
        "VOYAGE_ID": voyage_id,
        "POL_NAME": pl.order.leg.departure_port.name if pl.order.leg and pl.order.leg.departure_port else "",
        "POD_NAME": pl.order.leg.arrival_port.name if pl.order.leg and pl.order.leg.arrival_port else "",
        "Maximum_de_CASES_QUANTITY": packages_desc or "—",
        "Nombre_de_PALLET_ID": f"{total_pallets} pallets" if total_pallets else "—",
        "Maximum_de_WEIGHT_KG": f"{int(total_weight)} KGS" if total_weight else "—",
        "TYPE_OF_GOODS": description or "—",
        "NUMBER_OF_OBL": "3",
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


# === ARRIVAL NOTICE (auto-generated DOCX) ===
@router.get("/{pl_id}/arrival-notice")
async def arrival_notice(
    pl_id: int, request: Request,
    user: User = Depends(get_current_user),
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

    from docx import Document
    from docx.shared import Pt, Inches, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT

    doc = Document()

    # Page margins
    for section in doc.sections:
        section.top_margin = Cm(1.5)
        section.bottom_margin = Cm(1.5)
        section.left_margin = Cm(2)
        section.right_margin = Cm(2)

    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(10)

    # --- Header ---
    h = doc.add_heading('ARRIVAL NOTICE', level=1)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in h.runs:
        run.font.color.rgb = RGBColor(9, 85, 97)  # TOWT teal
        run.font.size = Pt(22)

    # Sub-header with TOWT info
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = sub.add_run('TOWT — Transport à la Voile')
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor(100, 100, 100)

    doc.add_paragraph()  # spacer

    # --- Reference block ---
    leg = pl.order.leg
    vessel_name = leg.vessel.name if leg and leg.vessel else "—"
    voyage_id = leg.leg_code if leg else "—"
    pol = leg.departure_port if leg else None
    pod = leg.arrival_port if leg else None
    eta_str = leg.eta.strftime('%d/%m/%Y %H:%M') if leg and leg.eta else "TBC"

    ref_table = doc.add_table(rows=6, cols=2, style='Table Grid')
    ref_table.alignment = WD_TABLE_ALIGNMENT.LEFT

    ref_data = [
        ("Reference", f"TUAW_{voyage_id}_{pl.id}"),
        ("Vessel", vessel_name),
        ("Voyage", voyage_id),
        ("Port of Loading", f"{pol.name} ({pol.locode})" if pol else "—"),
        ("Port of Discharge", f"{pod.name} ({pod.locode})" if pod else "—"),
        ("ETA", eta_str),
    ]
    for i, (label, value) in enumerate(ref_data):
        cell_l = ref_table.cell(i, 0)
        cell_l.text = label
        for p in cell_l.paragraphs:
            for r in p.runs:
                r.font.bold = True
                r.font.size = Pt(10)
        cell_v = ref_table.cell(i, 1)
        cell_v.text = value
        for p in cell_v.paragraphs:
            for r in p.runs:
                r.font.size = Pt(10)

    # Set column widths
    for row in ref_table.rows:
        row.cells[0].width = Cm(5)
        row.cells[1].width = Cm(10)

    doc.add_paragraph()  # spacer

    # --- Consignee / Notify ---
    first = pl.batches[0] if pl.batches else None

    def addr_block(name, address, postal, city, country):
        parts = [p for p in [name, address, f"{postal or ''} {city or ''}".strip(), country] if p]
        return "\n".join(parts) if parts else "—"

    parties_table = doc.add_table(rows=1, cols=2, style='Table Grid')
    parties_table.alignment = WD_TABLE_ALIGNMENT.LEFT

    # Consignee
    c_cell = parties_table.cell(0, 0)
    c_para = c_cell.paragraphs[0]
    c_run = c_para.add_run("CONSIGNEE\n")
    c_run.font.bold = True
    c_run.font.size = Pt(10)
    c_run.font.color.rgb = RGBColor(9, 85, 97)
    if first:
        c_val = c_para.add_run(addr_block(
            first.consignee_name, first.consignee_address,
            first.consignee_postal, first.consignee_city, first.consignee_country))
    else:
        c_val = c_para.add_run("—")
    c_val.font.size = Pt(10)

    # Notify
    n_cell = parties_table.cell(0, 1)
    n_para = n_cell.paragraphs[0]
    n_run = n_para.add_run("NOTIFY PARTY\n")
    n_run.font.bold = True
    n_run.font.size = Pt(10)
    n_run.font.color.rgb = RGBColor(9, 85, 97)
    if first:
        n_val = n_para.add_run(addr_block(
            first.notify_name, first.notify_address,
            first.notify_postal, first.notify_city, first.notify_country))
    else:
        n_val = n_para.add_run("—")
    n_val.font.size = Pt(10)

    doc.add_paragraph()  # spacer

    # --- Cargo Details Table ---
    h2 = doc.add_heading('CARGO DETAILS', level=2)
    for run in h2.runs:
        run.font.color.rgb = RGBColor(9, 85, 97)
        run.font.size = Pt(14)

    cargo_headers = [
        "Batch", "Type of Goods", "Pallets", "Cases",
        "Weight (kg)", "L×W×H (cm)", "Volume (m³)"
    ]
    cargo_table = doc.add_table(rows=1, cols=len(cargo_headers), style='Table Grid')
    cargo_table.alignment = WD_TABLE_ALIGNMENT.LEFT

    # Header row
    for j, ch in enumerate(cargo_headers):
        cell = cargo_table.rows[0].cells[j]
        cell.text = ch
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.font.bold = True
                r.font.size = Pt(9)
                r.font.color.rgb = RGBColor(255, 255, 255)
        from docx.oxml.ns import qn
        shading = cell._element.get_or_add_tcPr()
        shd = shading.makeelement(qn('w:shd'), {
            qn('w:fill'): '095561', qn('w:val'): 'clear'
        })
        shading.append(shd)

    total_pallets = 0
    total_cases = 0
    total_weight = 0
    total_volume = 0

    for batch in pl.batches:
        row_cells = cargo_table.add_row().cells
        dims = f"{batch.length_cm or '—'}×{batch.width_cm or '—'}×{batch.height_cm or '—'}"
        row_data = [
            f"#{batch.batch_number}",
            batch.type_of_goods or "—",
            str(batch.pallet_quantity or 0),
            str(batch.cases_quantity or 0),
            str(batch.weight_kg or 0),
            dims,
            str(batch.volume_m3 or "—"),
        ]
        for j, val in enumerate(row_data):
            row_cells[j].text = val
            for p in row_cells[j].paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:
                    r.font.size = Pt(9)

        total_pallets += batch.pallet_quantity or 0
        total_cases += batch.cases_quantity or 0
        total_weight += batch.weight_kg or 0
        total_volume += batch.volume_m3 or 0

    # Totals row
    totals_cells = cargo_table.add_row().cells
    totals_data = [
        "TOTAL", "", str(total_pallets), str(total_cases),
        str(round(total_weight, 1)), "", str(round(total_volume, 4)) if total_volume else "—",
    ]
    for j, val in enumerate(totals_data):
        totals_cells[j].text = val
        for p in totals_cells[j].paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.font.bold = True
                r.font.size = Pt(9)

    doc.add_paragraph()  # spacer

    # --- Shipper ---
    h3 = doc.add_heading('SHIPPER', level=2)
    for run in h3.runs:
        run.font.color.rgb = RGBColor(9, 85, 97)
        run.font.size = Pt(14)

    if first:
        shipper_text = addr_block(
            first.shipper_name, first.shipper_address,
            first.shipper_postal, first.shipper_city, first.shipper_country)
    else:
        shipper_text = "—"
    p = doc.add_paragraph(shipper_text)
    for r in p.runs:
        r.font.size = Pt(10)

    doc.add_paragraph()  # spacer

    # --- Special instructions ---
    h4 = doc.add_heading('SPECIAL INSTRUCTIONS', level=2)
    for run in h4.runs:
        run.font.color.rgb = RGBColor(9, 85, 97)
        run.font.size = Pt(14)

    # Check for dangerous goods
    has_imo = any(b.imo_product_class and b.imo_product_class != "Non-Dangerous Goods" for b in pl.batches)
    instructions = []
    if has_imo:
        imo_classes = set(b.imo_product_class for b in pl.batches if b.imo_product_class and b.imo_product_class != "Non-Dangerous Goods")
        instructions.append(f"IMO Dangerous Goods: {', '.join(imo_classes)}")
        un_numbers = set(b.un_number for b in pl.batches if b.un_number)
        if un_numbers:
            instructions.append(f"UN Numbers: {', '.join(un_numbers)}")

    has_bio = any(b.bio_products and b.bio_products.lower() in ('yes', 'oui') for b in pl.batches)
    if has_bio:
        instructions.append("Contains BIO / Organic certified products")

    stackable_info = set(b.stackable for b in pl.batches if b.stackable)
    if stackable_info:
        instructions.append(f"Stackable: {', '.join(stackable_info)}")

    if instructions:
        for instr in instructions:
            p = doc.add_paragraph(f"• {instr}")
            for r in p.runs:
                r.font.size = Pt(10)
    else:
        p = doc.add_paragraph("No special instructions")
        for r in p.runs:
            r.font.size = Pt(10)
            r.font.italic = True

    # --- Footer ---
    doc.add_paragraph()
    footer = doc.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run(f"Document generated on {datetime.now().strftime('%d/%m/%Y at %H:%M')} — TOWT")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(150, 150, 150)

    # Save to buffer
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    filename = f"ARRIVAL_NOTICE_{pl.order.reference}_{datetime.now().strftime('%Y%m%d')}.docx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# === ADD BATCH (exploitation) ===
@router.post("/{pl_id}/add-batch", response_class=HTMLResponse)
async def add_batch(
    pl_id: int, request: Request,
    user: User = Depends(get_current_user),
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
    await log_activity(db, user, "cargo", "add_batch", "PackingList", pl_id, "Ajout batch")

    url = f"/cargo/{pl_id}"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


# === AUDIT HELPER ===
CLIENT_FIELDS = [
    'customer_name', 'freight_forwarder', 'code_transitaire',
    'shipper_name', 'shipper_address', 'shipper_postal', 'shipper_city', 'shipper_country',
    'po_number', 'customer_batch_id',
    'notify_name', 'notify_address', 'notify_postal', 'notify_city', 'notify_country',
    'consignee_name', 'consignee_address', 'consignee_postal', 'consignee_city', 'consignee_country',
    'pallet_type', 'type_of_goods', 'description_of_goods', 'bio_products', 'cases_quantity',
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
    batch.shipper_postal = form_data.get('shipper_postal', batch.shipper_postal)
    batch.shipper_city = form_data.get('shipper_city', batch.shipper_city)
    batch.shipper_country = form_data.get('shipper_country', batch.shipper_country)
    batch.po_number = form_data.get('po_number', batch.po_number)
    batch.customer_batch_id = form_data.get('customer_batch_id', batch.customer_batch_id)
    batch.notify_name = form_data.get('notify_name', batch.notify_name)
    batch.notify_address = form_data.get('notify_address', batch.notify_address)
    batch.notify_postal = form_data.get('notify_postal', batch.notify_postal)
    batch.notify_city = form_data.get('notify_city', batch.notify_city)
    batch.notify_country = form_data.get('notify_country', batch.notify_country)
    batch.consignee_name = form_data.get('consignee_name', batch.consignee_name)
    batch.consignee_address = form_data.get('consignee_address', batch.consignee_address)
    batch.consignee_postal = form_data.get('consignee_postal', batch.consignee_postal)
    batch.consignee_city = form_data.get('consignee_city', batch.consignee_city)
    batch.consignee_country = form_data.get('consignee_country', batch.consignee_country)
    batch.pallet_type = form_data.get('pallet_type', batch.pallet_type)
    batch.type_of_goods = form_data.get('type_of_goods', batch.type_of_goods)
    batch.description_of_goods = form_data.get('description_of_goods', batch.description_of_goods)
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
    user: User = Depends(get_current_user),
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
    await log_activity(db, user, "cargo", "update", "PackingList", pl_id, "Modification packing list")
    url = f"/cargo/{pl_id}"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


# === AUDIT LOG VIEW ===
@router.get("/{pl_id}/history", response_class=HTMLResponse)
async def audit_history(
    pl_id: int, request: Request,
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
        "SHIPPER_ADDRESS": "shipper_address",
        "SHIPPER_POSTAL": "shipper_postal",
        "SHIPPER_CITY": "shipper_city",
        "SHIPPER_COUNTRY": "shipper_country",
        "PO_NUMBER": "po_number",
        "CUSTOMER_BATCH_ID": "customer_batch_id",
        "NOTIFY_NAME": "notify_name",
        "NOTIFY_ADDRESS": "notify_address",
        "NOTIFY_POSTAL": "notify_postal",
        "NOTIFY_CITY": "notify_city",
        "NOTIFY_COUNTRY": "notify_country",
        "CONSIGNEE_NAME": "consignee_name",
        "CONSIGNEE_ADDRESS": "consignee_address",
        "CONSIGNEE_POSTAL": "consignee_postal",
        "CONSIGNEE_CITY": "consignee_city",
        "CONSIGNEE_COUNTRY": "consignee_country",
        "PALLET_TYPE": "pallet_type",
        "TYPE_OF_GOODS": "type_of_goods",
        "DESCRIPTION_OF_GOODS": "description_of_goods",
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
        # Legacy column names for backward compatibility
        "NOTIFY_ADRESS": "notify_address",
        "CONSIGNEE_ORDER_ADRESS": "consignee_address",
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
    await log_activity(db, user, "cargo", "import_excel", "PackingList", pl_id, "Import Excel")
    url = f"/cargo/{pl_id}"
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=303)


# === VOYAGE EXPORT (all packing lists for a leg) ===
@router.get("/voyage/{leg_id}/excel")
async def export_voyage_excel(
    leg_id: int,
    user: User = Depends(get_current_user),
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

ext_router = APIRouter(prefix="/p", tags=["packing-external"])


@ext_router.get("/{token}", response_class=HTMLResponse)
async def client_packing_list(
    token: str, request: Request,
    db: AsyncSession = Depends(get_db),
):
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

    # Language from query param or cookie, default fr
    lang = request.query_params.get('lang') or request.cookies.get('towt_lang') or 'fr'
    if lang not in ('fr', 'en', 'es', 'pt-br', 'vi'):
        lang = 'fr'

    return templates.TemplateResponse("cargo/client_form.html", {
        "request": request, "pl": pl,
        "imo_classes": IMO_CLASSES,
        "lang": lang,
    })


@ext_router.post("/{token}/batch/add", response_class=HTMLResponse)
async def client_add_batch(
    token: str, request: Request,
    db: AsyncSession = Depends(get_db),
):
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

    # Copy TOWT fields from first batch
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
async def client_save_batches(
    token: str, request: Request,
    db: AsyncSession = Depends(get_db),
):
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
async def client_delete_batch(
    token: str, batch_id: int, request: Request,
    db: AsyncSession = Depends(get_db),
):
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


# === CLIENT TEMPLATE DOWNLOAD ===
@ext_router.get("/{token}/template")
async def client_download_template(
    token: str, request: Request,
    db: AsyncSession = Depends(get_db),
):
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
        raise HTTPException(404)

    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PACKING_LIST"

    # Client-visible headers: TOWT pre-filled (grey) + Client fields (yellow, editable)
    towt_headers = [
        "VOYAGE_ID", "VESSEL", "LOADING_DATE", "POL_CODE", "POD_CODE",
        "POL_NAME", "POD_NAME", "BOOKING_CONFIRMATION_TOWT",
    ]
    client_headers = [
        "CUSTOMER_NAME",
        "SHIPPER_NAME", "SHIPPER_ADDRESS", "SHIPPER_POSTAL", "SHIPPER_CITY", "SHIPPER_COUNTRY",
        "NOTIFY_NAME", "NOTIFY_ADDRESS", "NOTIFY_POSTAL", "NOTIFY_CITY", "NOTIFY_COUNTRY",
        "CONSIGNEE_NAME", "CONSIGNEE_ADDRESS", "CONSIGNEE_POSTAL", "CONSIGNEE_CITY", "CONSIGNEE_COUNTRY",
        "FREIGHT_FORWARDER", "CODE_TRANSITAIRE", "PO_NUMBER", "CUSTOMER_BATCH_ID",
        "PALLET_TYPE", "TYPE_OF_GOODS", "DESCRIPTION_OF_GOODS", "BIO_PRODUCTS",
        "CASES_QUANTITY", "UNITS_PER_CASE", "IMO_PRODUCT_CLASS",
        "PALLET_QUANTITY_PER_BATCH",
        "LENGTH_CM", "WIDTH_CM", "HEIGHT_CM", "WEIGHT_KG", "CARGO_VALUE_USD",
    ]
    all_headers = towt_headers + client_headers

    # Styles
    towt_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    client_fill = PatternFill(start_color="FFFFFF00", end_color="FFFFFF00", fill_type="solid")
    header_fill = PatternFill(start_color="095561", end_color="095561", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin'),
    )

    # Header row
    for col_idx, h in enumerate(all_headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
        cell.border = thin_border
        ws.column_dimensions[get_column_letter(col_idx)].width = max(16, len(h) + 2)

    # Instructions row (row 2)
    ws.insert_rows(2)
    instr_font = Font(italic=True, size=9, color="666666")
    for col_idx, h in enumerate(all_headers, 1):
        cell = ws.cell(row=2, column=col_idx)
        cell.border = thin_border
        cell.font = instr_font
        if h in towt_headers:
            cell.value = "TOWT (ne pas modifier)"
            cell.fill = towt_fill
        else:
            cell.value = "A remplir"
            cell.fill = client_fill

    # Pre-fill batch data (row 3+)
    for row_idx, batch in enumerate(pl.batches, 3):
        towt_data = {
            "VOYAGE_ID": batch.voyage_id,
            "VESSEL": batch.vessel,
            "LOADING_DATE": batch.loading_date.isoformat() if batch.loading_date else "",
            "POL_CODE": batch.pol_code,
            "POD_CODE": batch.pod_code,
            "POL_NAME": batch.pol_name,
            "POD_NAME": batch.pod_name,
            "BOOKING_CONFIRMATION_TOWT": batch.booking_confirmation,
        }
        client_data = {
            "CUSTOMER_NAME": batch.customer_name,
            "SHIPPER_NAME": batch.shipper_name,
            "SHIPPER_ADDRESS": batch.shipper_address,
            "SHIPPER_POSTAL": batch.shipper_postal,
            "SHIPPER_CITY": batch.shipper_city,
            "SHIPPER_COUNTRY": batch.shipper_country,
            "NOTIFY_NAME": batch.notify_name,
            "NOTIFY_ADDRESS": batch.notify_address,
            "NOTIFY_POSTAL": batch.notify_postal,
            "NOTIFY_CITY": batch.notify_city,
            "NOTIFY_COUNTRY": batch.notify_country,
            "CONSIGNEE_NAME": batch.consignee_name,
            "CONSIGNEE_ADDRESS": batch.consignee_address,
            "CONSIGNEE_POSTAL": batch.consignee_postal,
            "CONSIGNEE_CITY": batch.consignee_city,
            "CONSIGNEE_COUNTRY": batch.consignee_country,
            "FREIGHT_FORWARDER": batch.freight_forwarder,
            "CODE_TRANSITAIRE": batch.code_transitaire,
            "PO_NUMBER": batch.po_number,
            "CUSTOMER_BATCH_ID": batch.customer_batch_id,
            "PALLET_TYPE": batch.pallet_type,
            "TYPE_OF_GOODS": batch.type_of_goods,
            "DESCRIPTION_OF_GOODS": batch.description_of_goods,
            "BIO_PRODUCTS": batch.bio_products,
            "CASES_QUANTITY": batch.cases_quantity,
            "UNITS_PER_CASE": batch.units_per_case,
            "IMO_PRODUCT_CLASS": batch.imo_product_class,
            "PALLET_QUANTITY_PER_BATCH": batch.pallet_quantity,
            "LENGTH_CM": batch.length_cm,
            "WIDTH_CM": batch.width_cm,
            "HEIGHT_CM": batch.height_cm,
            "WEIGHT_KG": batch.weight_kg,
            "CARGO_VALUE_USD": batch.cargo_value_usd,
        }
        all_data = {**towt_data, **client_data}
        for col_idx, h in enumerate(all_headers, 1):
            val = all_data.get(h, "")
            cell = ws.cell(row=row_idx, column=col_idx, value=val if val is not None else "")
            cell.border = thin_border
            if h in towt_headers:
                cell.fill = towt_fill
            else:
                cell.fill = client_fill

    # Add BIO_PRODUCTS data validation (Yes/No)
    bio_col_idx = all_headers.index("BIO_PRODUCTS") + 1
    bio_col_letter = get_column_letter(bio_col_idx)
    dv = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True)
    dv.error = "Please select Yes or No"
    dv.errorTitle = "Invalid value"
    ws.add_data_validation(dv)
    dv.add(f"{bio_col_letter}3:{bio_col_letter}100")

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    ref = pl.order.reference if pl.order else "UNKNOWN"
    filename = f"PACKING_LIST_TEMPLATE_{ref}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# === CLIENT EXCEL IMPORT ===
@ext_router.post("/{token}/import", response_class=HTMLResponse)
async def client_import_excel(
    token: str, request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PackingList).options(
            selectinload(PackingList.batches),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.vessel),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.departure_port),
            selectinload(PackingList.order).selectinload(Order.leg).selectinload(Leg.arrival_port),
        ).where(PackingList.token == token)
    )
    pl = result.scalar_one_or_none()
    if not pl or pl.is_locked:
        raise HTTPException(403)

    form = await request.form()
    file = form.get("file")
    if not file:
        return RedirectResponse(url=f"/p/{token}?error=no_file", status_code=303)

    import openpyxl
    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        return RedirectResponse(url=f"/p/{token}?error=invalid_file", status_code=303)

    ws = wb.active

    # Find header row (row 1 or row with known headers)
    headers = []
    header_row = 1
    for row_num in range(1, 4):
        row_vals = [cell.value for cell in ws[row_num] if cell.value]
        if "CUSTOMER_NAME" in row_vals or "PALLET_QUANTITY_PER_BATCH" in row_vals:
            headers = [cell.value for cell in ws[row_num]]
            header_row = row_num
            break

    if not headers:
        return RedirectResponse(url=f"/p/{token}?error=invalid_format", status_code=303)

    header_map = {h: idx for idx, h in enumerate(headers) if h}

    CLIENT_IMPORT_FIELDS = {
        "CUSTOMER_NAME": "customer_name",
        "FREIGHT_FORWARDER": "freight_forwarder",
        "CODE_TRANSITAIRE": "code_transitaire",
        "SHIPPER_NAME": "shipper_name",
        "SHIPPER_ADDRESS": "shipper_address",
        "SHIPPER_POSTAL": "shipper_postal",
        "SHIPPER_CITY": "shipper_city",
        "SHIPPER_COUNTRY": "shipper_country",
        "PO_NUMBER": "po_number",
        "CUSTOMER_BATCH_ID": "customer_batch_id",
        "NOTIFY_NAME": "notify_name",
        "NOTIFY_ADDRESS": "notify_address",
        "NOTIFY_POSTAL": "notify_postal",
        "NOTIFY_CITY": "notify_city",
        "NOTIFY_COUNTRY": "notify_country",
        "CONSIGNEE_NAME": "consignee_name",
        "CONSIGNEE_ADDRESS": "consignee_address",
        "CONSIGNEE_POSTAL": "consignee_postal",
        "CONSIGNEE_CITY": "consignee_city",
        "CONSIGNEE_COUNTRY": "consignee_country",
        "PALLET_TYPE": "pallet_type",
        "TYPE_OF_GOODS": "type_of_goods",
        "DESCRIPTION_OF_GOODS": "description_of_goods",
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

    # Update existing batches or create new ones
    data_start_row = header_row + 1
    # Skip instruction row if present
    first_data_row = ws[data_start_row]
    first_cell_val = str(first_data_row[0].value or "")
    if "ne pas modifier" in first_cell_val.lower() or "a remplir" in first_cell_val.lower():
        data_start_row += 1

    batch_idx = 0
    existing_batches = list(pl.batches)

    for row in ws.iter_rows(min_row=data_start_row, values_only=False):
        values = [cell.value for cell in row]
        if not any(values):
            continue

        if batch_idx < len(existing_batches):
            batch = existing_batches[batch_idx]
        else:
            # Create new batch with TOWT fields copied from first batch
            first = existing_batches[0] if existing_batches else None
            batch = PackingListBatch(
                packing_list_id=pl.id,
                batch_number=batch_idx + 1,
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

        # Apply client fields from Excel
        form_data = {}
        for excel_col, model_field in CLIENT_IMPORT_FIELDS.items():
            if excel_col in header_map:
                idx = header_map[excel_col]
                if idx < len(values):
                    val = values[idx]
                    if val is not None:
                        form_data[model_field] = str(val)

        if form_data:
            await audit_batch_changes(db, pl.id, batch, form_data, "Client (Excel)")
            apply_batch_fields(batch, form_data)

        batch_idx += 1

    if pl.status == "draft":
        pl.status = "submitted"

    await db.flush()
    return RedirectResponse(url=f"/p/{token}?saved=1", status_code=303)
