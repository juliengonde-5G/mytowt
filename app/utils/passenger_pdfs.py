"""PDF generators for passenger documents: confirmation letter, diploma, satisfaction survey."""
from io import BytesIO
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)

TOWT_BLUE = colors.HexColor("#095561")
TOWT_GREEN = colors.HexColor("#87BD2B")
TOWT_LIGHT = colors.HexColor("#f0f7f8")
W, H = A4

TOWT_HEADER = "TOWT – 803 845 270\n52 QUAI FRISSARD, 76600 LE HAVRE"
TOWT_SERVICE = "TOWT – Service Passagers\n52 quai Frissard, Le Havre, 76600"


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("H1", parent=styles["Heading1"], fontSize=16, textColor=TOWT_BLUE,
                              spaceAfter=8, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, textColor=TOWT_BLUE,
                              spaceAfter=6, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("B", parent=styles["BodyText"], fontSize=10, leading=14,
                              alignment=TA_JUSTIFY, fontName="Helvetica"))
    styles.add(ParagraphStyle("Sm", parent=styles["BodyText"], fontSize=8, leading=10,
                              textColor=colors.HexColor("#888888"), fontName="Helvetica"))
    styles.add(ParagraphStyle("Right", parent=styles["BodyText"], fontSize=10, alignment=TA_RIGHT,
                              fontName="Helvetica"))
    styles.add(ParagraphStyle("Center", parent=styles["BodyText"], fontSize=10, alignment=TA_CENTER,
                              fontName="Helvetica"))
    styles.add(ParagraphStyle("Header", parent=styles["Heading1"], fontSize=9, alignment=TA_CENTER,
                              textColor=colors.HexColor("#888888"), fontName="Helvetica-Oblique"))
    styles.add(ParagraphStyle("Footer", parent=styles["BodyText"], fontSize=8, alignment=TA_CENTER,
                              textColor=colors.HexColor("#888888"), fontName="Helvetica"))
    # Diploma styles
    styles.add(ParagraphStyle("DipTitle", fontSize=36, alignment=TA_CENTER, textColor=TOWT_BLUE,
                              fontName="Helvetica-Bold", spaceAfter=10))
    styles.add(ParagraphStyle("DipSub", fontSize=14, alignment=TA_CENTER, textColor=TOWT_GREEN,
                              fontName="Helvetica-Bold", spaceAfter=6))
    styles.add(ParagraphStyle("DipName", fontSize=24, alignment=TA_CENTER, textColor=TOWT_BLUE,
                              fontName="Helvetica-Bold", spaceAfter=8))
    styles.add(ParagraphStyle("DipBody", fontSize=12, alignment=TA_CENTER, leading=16,
                              fontName="Helvetica", textColor=colors.HexColor("#333333")))
    styles.add(ParagraphStyle("DipMeta", fontSize=10, alignment=TA_CENTER, leading=12,
                              fontName="Helvetica", textColor=colors.HexColor("#666666")))
    return styles


# ═══════════════════════════════════════════════════════════════
#  CONFIRMATION LETTER
# ═══════════════════════════════════════════════════════════════

def generate_confirmation_letter(booking, leg, passengers, portal_url=None):
    """Generate a booking confirmation letter PDF."""
    buf = BytesIO()
    styles = _styles()

    def on_page(canvas, doc):
        # Header
        canvas.setFont("Helvetica-Oblique", 8)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawCentredString(W / 2, H - 10 * mm, "TOWT – Confirmation de réservation")
        # Footer
        canvas.drawCentredString(W / 2, 8 * mm, TOWT_HEADER.replace("\n", " — "))

    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=20 * mm, rightMargin=20 * mm)
    e = []

    # Title
    e.append(Paragraph("<b>Objet : Confirmation de réservation pour un voyage en bateau</b>", styles["H1"]))
    e.append(Spacer(1, 4 * mm))

    # Passenger info block
    for pax in passengers:
        e.append(Paragraph(f"<b>NOM :</b> {pax.last_name or '—'}", styles["B"]))
        e.append(Paragraph(f"<b>PRENOM :</b> {pax.first_name or '—'}", styles["B"]))
        e.append(Paragraph(f"<b>Adresse :</b> —", styles["B"]))
        e.append(Paragraph(f"<b>Téléphone :</b> {pax.phone or '—'}", styles["B"]))
        e.append(Paragraph(f"<b>Mail :</b> {pax.email or '—'}", styles["B"]))
        e.append(Spacer(1, 3 * mm))

    e.append(Spacer(1, 6 * mm))

    # Right-aligned TOWT address
    e.append(Paragraph(TOWT_SERVICE.replace("\n", "<br/>"), styles["Right"]))
    e.append(Spacer(1, 4 * mm))

    # Date
    e.append(Paragraph(f"Le {date.today().strftime('%d/%m/%Y')}", styles["B"]))
    e.append(Spacer(1, 6 * mm))

    # Salutation
    e.append(Paragraph("Madame, Monsieur,", styles["B"]))
    e.append(Spacer(1, 4 * mm))

    e.append(Paragraph(
        "Suite à notre échange, nous vous confirmons par la présente votre réservation pour un voyage "
        "en bateau à bord de notre navire, conformément aux conditions générales de vente de notre "
        "compagnie (2026_TOWT_passagers_CGV).", styles["B"]))
    e.append(Spacer(1, 4 * mm))

    e.append(Paragraph("<b>Les détails de la réservation sont les suivants :</b>", styles["B"]))
    e.append(Spacer(1, 2 * mm))

    # Booking details
    dep_port = leg.departure_port.name if leg and leg.departure_port else "—"
    arr_port = leg.arrival_port.name if leg and leg.arrival_port else "—"
    etd = leg.etd.strftime("%d/%m/%Y") if leg and leg.etd else "À confirmer"
    vessel_name = leg.vessel.name if leg and leg.vessel else (booking.vessel.name if booking.vessel else "—")
    cabin_type = "Lit double" if booking.cabin_number <= 2 else "Lits jumeaux"

    details = [
        f"<b>Référence :</b> {booking.reference}",
        f"<b>Navire :</b> {vessel_name}",
        f"<b>Date de départ :</b> {etd}",
        f"<b>Itinéraire :</b> {dep_port} → {arr_port}",
        f"<b>Cabine :</b> {booking.cabin_number} — {cabin_type}",
        f"<b>Passager(s) :</b> {', '.join(p.full_name for p in passengers)}",
    ]
    if booking.price_total:
        details.append(f"<b>Prix total :</b> {booking.price_total:.2f} €")
    if booking.price_deposit:
        details.append(f"<b>Acompte (30%) :</b> {booking.price_deposit:.2f} €")
    if booking.price_balance:
        details.append(f"<b>Solde :</b> {booking.price_balance:.2f} €")

    for d in details:
        e.append(Paragraph(f"&nbsp;&nbsp;&nbsp;• {d}", styles["B"]))

    e.append(Spacer(1, 6 * mm))

    # Portal link
    if portal_url:
        e.append(Paragraph(
            f"<b>Votre espace personnel :</b> {portal_url}", styles["B"]))
        e.append(Paragraph(
            "Connectez-vous à votre espace pour suivre votre réservation, déposer vos documents "
            "et remplir le questionnaire pré-embarquement.", styles["B"]))
        e.append(Spacer(1, 4 * mm))

    # Payment paragraph
    e.append(Paragraph(
        "Conformément aux conditions de réservation indiquées dans nos conditions générales de "
        "service, un acompte de 30% est requis pour confirmer votre réservation. Le solde devra "
        "être réglé avant le départ effectif.", styles["B"]))
    e.append(Spacer(1, 4 * mm))

    e.append(Paragraph(
        "Nous vous remercions pour votre confiance et restons à votre disposition pour toute "
        "information complémentaire.", styles["B"]))
    e.append(Spacer(1, 6 * mm))

    e.append(Paragraph(
        "Dans l'attente et en vous souhaitant une excellente traversée, nous vous prions "
        "d'agréer, Madame, Monsieur, l'expression de nos salutations distinguées.", styles["B"]))
    e.append(Spacer(1, 10 * mm))

    e.append(Paragraph("TOWT — Service Passagers", styles["B"]))
    e.append(Paragraph("voyage@towt.eu", styles["B"]))

    doc.build(e, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════
#  DIPLOMA / CERTIFICATE
# ═══════════════════════════════════════════════════════════════

def generate_diploma(passenger_name, vessel_name, departure_port, arrival_port,
                     departure_date, arrival_date, leg_code, distance_nm=None):
    """Generate a passenger diploma/certificate PDF."""
    buf = BytesIO()
    styles = _styles()

    def on_page(canvas, doc):
        # Decorative border
        canvas.setStrokeColor(TOWT_BLUE)
        canvas.setLineWidth(3)
        canvas.rect(15 * mm, 15 * mm, W - 30 * mm, H - 30 * mm, fill=0, stroke=1)
        # Inner border green
        canvas.setStrokeColor(TOWT_GREEN)
        canvas.setLineWidth(1)
        canvas.rect(18 * mm, 18 * mm, W - 36 * mm, H - 36 * mm, fill=0, stroke=1)

    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=30 * mm, bottomMargin=30 * mm,
                            leftMargin=25 * mm, rightMargin=25 * mm)
    e = []

    e.append(Spacer(1, 15 * mm))
    e.append(Paragraph("🚢", ParagraphStyle("E", fontSize=40, alignment=TA_CENTER)))
    e.append(Spacer(1, 5 * mm))
    e.append(Paragraph("TOWT", styles["DipTitle"]))
    e.append(Paragraph("Transoceanic Wind Transport", styles["DipSub"]))
    e.append(Spacer(1, 8 * mm))

    e.append(HRFlowable(width="60%", thickness=2, color=TOWT_GREEN, spaceAfter=8))

    e.append(Paragraph("DIPLÔME DE TRAVERSÉE", ParagraphStyle(
        "dt", fontSize=18, alignment=TA_CENTER, textColor=TOWT_BLUE,
        fontName="Helvetica-Bold", spaceAfter=12)))

    e.append(Paragraph("Nous certifions que", styles["DipBody"]))
    e.append(Spacer(1, 4 * mm))
    e.append(Paragraph(f"<b>{passenger_name}</b>", styles["DipName"]))
    e.append(Spacer(1, 4 * mm))

    e.append(Paragraph(
        f"a effectué la traversée à bord du voilier-cargo <b>{vessel_name}</b>",
        styles["DipBody"]))
    e.append(Spacer(1, 3 * mm))

    e.append(Paragraph(
        f"<b>{departure_port}</b> → <b>{arrival_port}</b>",
        ParagraphStyle("route", fontSize=16, alignment=TA_CENTER, textColor=TOWT_GREEN,
                       fontName="Helvetica-Bold", spaceAfter=6)))

    dep_str = departure_date.strftime("%d/%m/%Y") if departure_date else "—"
    arr_str = arrival_date.strftime("%d/%m/%Y") if arrival_date else "—"
    e.append(Paragraph(f"du {dep_str} au {arr_str}", styles["DipMeta"]))

    if distance_nm:
        e.append(Paragraph(f"Distance parcourue : {distance_nm} milles nautiques", styles["DipMeta"]))

    e.append(Paragraph(f"Voyage : {leg_code}", styles["DipMeta"]))
    e.append(Spacer(1, 8 * mm))

    e.append(HRFlowable(width="60%", thickness=2, color=TOWT_GREEN, spaceAfter=8))

    e.append(Paragraph(
        "En participant à cette traversée transocéanique à la voile, vous avez contribué "
        "à la décarbonation du transport maritime. Merci pour votre engagement écologique.",
        styles["DipBody"]))

    e.append(Spacer(1, 15 * mm))

    e.append(Paragraph(f"Délivré le {date.today().strftime('%d/%m/%Y')}", styles["DipMeta"]))
    e.append(Spacer(1, 10 * mm))

    # Signatures row
    sig_data = [["Le Capitaine", "TOWT — Service Passagers"]]
    sig_table = Table(sig_data, colWidths=[(W - 50 * mm) / 2] * 2)
    sig_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#666666")),
    ]))
    e.append(sig_table)

    doc.build(e, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
