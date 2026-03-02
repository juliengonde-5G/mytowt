"""Crossing book PDF — real TOWT content, bilingual FR/EN."""
from io import BytesIO
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable,
)

TOWT_BLUE = colors.HexColor("#095561")
TOWT_GREEN = colors.HexColor("#87BD2B")
TOWT_LIGHT = colors.HexColor("#f0f7f8")
TOWT_GRAY = colors.HexColor("#555555")
W, H = A4

# ─── TRANSLATIONS ─────────────────────────────────────────────
T = {
    "fr": {
        "book_title": "BOOK DE TRAVERSÉE",
        "departure": "Départ",
        "arrival": "Arrivée",
        "voyage": "Voyage",
        "passengers": "Passager(s)",
        "vessel_title": "Le navire",
        "vessel_intro": (
            "Vous embarquez sur un voilier cargo de la compagnie TOWT (Transoceanic Wind Transport). "
            "Nos navires utilisent le vent comme source d'énergie principale, réduisant significativement "
            "l'empreinte carbone du transport de marchandises."
        ),
        "name": "Nom", "imo": "Numéro IMO", "flag": "Pavillon",
        "dwt": "Port en lourd (DWT)", "capacity": "Capacité cargo", "speed": "Vitesse d'exploitation",
        "crew_title": "L'équipage",
        "crew_intro": (
            "L'équipage minimum compte 8 personnes, se répartissant les quarts de navigation, "
            "la sécurité, la maintenance, la cuisine, et la conduite des machines. "
            "L'équipage est à votre disposition — n'hésitez pas à poser vos questions."
        ),
        "col_name": "Nom", "col_role": "Fonction",
        "itin_title": "Itinéraire",
        "itin_note": (
            "Les horaires sont indicatifs et dépendent des conditions météorologiques. "
            "La navigation à voile implique une certaine flexibilité."
        ),
        "col_leg": "Étape", "col_dep": "Départ", "col_arr": "Arrivée", "col_etd": "ETD", "col_eta": "ETA",
        "welcome_title": "Bienvenue à bord",
        "welcome_text": (
            "Vous venez d'embarquer sur un voilier cargo de la compagnie TOWT, en tant que passager. "
            "Vous allez partager notre quotidien tout au long de la traversée, ponctuellement au travers "
            "de notre travail à bord, mais surtout lors des moments de détente, comme les repas et les soirées.<br/><br/>"
            "En tant que navire de charge, aucun service spécifique ne vous est destiné. Néanmoins, nous serons "
            "heureux de partager cette traversée avec vous et de vous faire découvrir le métier de marin de commerce."
        ),
        "admin_title": "Administratif",
        "admin_text": (
            "• Votre passeport sera remis à l'équipage à votre arrivée à bord et conservé en lieu sécurisé.<br/>"
            "• Tout traitement médical lourd ou état de santé particulier doit être signalé à l'arrivée.<br/>"
            "• Une clé de cabine vous sera remise individuellement."
        ),
        "safety_title": "Sécurité",
        "safety_text": (
            "Ce navire est un voilier cargo, dont le comportement en mer est similaire à celui d'un voilier "
            "de plaisance (gîte, roulis, tangage).<br/><br/>"
            "Merci de :<br/>"
            "• Fixer et sécuriser vos effets personnels.<br/>"
            "• Manipuler prudemment les portes et utiliser les mains courantes.<br/>"
            "• Porter des chaussures antidérapantes.<br/><br/>"
            "<b>Accès réglementé :</b><br/>"
            "• Interdiction d'accès à la cambuse, aux machines, aux cales, et à la cuisine (sauf en dehors des horaires de service).<br/>"
            "• La passerelle n'est accessible qu'en dehors des manœuvres et avec autorisation.<br/><br/>"
            "Des consignes de sécurité et procédures d'évacuation sont à suivre en cas d'urgence. "
            "Un exercice obligatoire est prévu avant le départ, et d'autres peuvent avoir lieu durant la traversée."
        ),
        "health_title": "Santé à bord",
        "health_text": (
            "• Le commandement est responsable des soins à bord, en lien avec le Centre de Consultation "
            "Médicales Maritimes de Toulouse.<br/>"
            "• Si vous êtes sujet au mal de mer, nous vous préconisons de vous munir de médicaments "
            "(C'zen, bracelet Sea-band, Mercalm, Nausicalm, Métopimazine…).<br/>"
            "• Toute évacuation sanitaire sera organisée avec les autorités compétentes si nécessaire."
        ),
        "life_title": "Vie à bord",
        "life_text": (
            "<b>Repos :</b> Merci de respecter le sommeil de l'équipage (horaires décalés).<br/><br/>"
            "<b>Repas :</b><br/>"
            "• Petit-déjeuner en autonomie.<br/>"
            "• Déjeuner à 12h10.<br/>"
            "• Dîner à 20h00.<br/>"
            "• Aucun aliment en cabine.<br/>"
            "• Merci de signaler allergies et régimes spécifiques.<br/><br/>"
            "<b>Alcool :</b> Navire sans alcool. Des exceptions ponctuelles peuvent être accordées "
            "à discrétion de l'équipage.<br/><br/>"
            "<b>Nuisances sonores :</b> Le navire reste un environnement bruyant malgré les isolations. "
            "Prévoyez des bouchons d'oreille si vous êtes sensibles au bruit."
        ),
        "housekeeping_title": "Entretien",
        "housekeeping_text": (
            "• Deux jeux de linge sont fournis.<br/>"
            "• Vous êtes autonomes pour votre lessive.<br/>"
            "• Les machines ne sont utilisables que selon la stabilité du navire.<br/>"
            "• Vous êtes responsables du ménage de votre cabine. Produits disponibles à l'entrée du carré.<br/>"
            "• Le contrôle de la cabine sera effectué à votre débarquement."
        ),
        "waste_title": "Gestion des déchets",
        "waste_text": (
            "• Aucun rejet en mer n'est autorisé.<br/>"
            "• Respect strict du tri sélectif.<br/>"
            "• Rejets alimentaires en mer uniquement hors zones spéciales, selon la réglementation."
        ),
        "leisure_title": "Loisirs & connexion",
        "leisure_text": (
            "<b>Loisirs :</b> Livres, jeux, tapis de sport à disposition. Télévision sans abonnement, "
            "console de jeux prêtée à discrétion. Matériel de pêche disponible (prévenir la passerelle).<br/><br/>"
            "<b>Tablette loisir :</b> Une tablette est mise à disposition au carré pour la lecture (ePresse) "
            "et la prise de photos/vidéos de la vie à bord.<br/><br/>"
            "<b>Connexion Internet :</b> Un code Wi-Fi vous est fourni. Merci de désactiver les mises à jour "
            "automatiques et d'utiliser le mode avion. Accès limité selon la bande passante du navire.<br/><br/>"
            "<b>Forfaits Wi-Fi supplémentaires :</b><br/>"
            "• Journalier : 1 Go / 24h — 3 €<br/>"
            "• Hebdomadaire 1 : 1 Go / 7 jours — 3 €<br/>"
            "• Hebdomadaire 2 : 2 Go / 7 jours — 6 €<br/>"
            "• Mensuel : 5 Go / 30 jours — 15 €<br/>"
            "Paiement via lien Revolut auprès du Capitaine."
        ),
        "timezone_title": "Changement d'heure",
        "timezone_text": "L'heure du bord évolue selon la progression du navire. Les changements sont annoncés la veille.",
        "shop_title": "Boutique à bord",
        "shop_text": (
            "Une petite boutique propose : produits d'hygiène, boissons, confiseries, cigarettes en quantité limitée. "
            "Paiement via lien Revolut."
        ),
        "forbidden_title": "Produits et objets interdits à bord",
        "forbidden_text": (
            "<b>1. Produits dangereux :</b> matières inflammables/explosives (essence, gaz, feux d'artifice), "
            "produits chimiques toxiques/corrosifs, matières radioactives, drogues et stupéfiants.<br/><br/>"
            "<b>2. Armes :</b> armes à feu et munitions, armes blanches de grande taille, aérosols incapacitants.<br/><br/>"
            "<b>3. Équipements à risque :</b> batteries lithium non homologuées, générateurs.<br/><br/>"
            "<b>4. Marchandises interdites :</b> aliments non conformes, plantes/graines non autorisées.<br/><br/>"
            "<b>5. Objets réglementés :</b> drones, lasers, dispositifs de brouillage.<br/><br/>"
            "Tout passager transportant un de ces objets sera soumis aux procédures de rétention "
            "et d'éventuelle remise aux autorités compétentes."
        ),
        "closing": "Nous vous souhaitons une excellente traversée !\nL'équipage de TOWT",
        "footer_co": "TOWT — Transoceanic Wind Transport · Voilier cargo",
        "generated": "Généré le",
        "page": "Page",
    },
    "en": {
        "book_title": "CROSSING BOOK",
        "departure": "Departure",
        "arrival": "Arrival",
        "voyage": "Voyage",
        "passengers": "Passenger(s)",
        "vessel_title": "The vessel",
        "vessel_intro": (
            "You are boarding a cargo sailing vessel operated by TOWT (Transoceanic Wind Transport). "
            "Our ships use wind as their primary energy source, significantly reducing the carbon footprint "
            "of goods transportation."
        ),
        "name": "Name", "imo": "IMO Number", "flag": "Flag",
        "dwt": "Deadweight (DWT)", "capacity": "Cargo capacity", "speed": "Cruising speed",
        "crew_title": "The crew",
        "crew_intro": (
            "The minimum crew consists of 8 members, sharing navigation watches, safety, maintenance, "
            "cooking, and engine room duties. The crew is at your disposal — don't hesitate to ask questions."
        ),
        "col_name": "Name", "col_role": "Role",
        "itin_title": "Itinerary",
        "itin_note": "Schedules are indicative and depend on weather conditions. Sailing implies flexibility.",
        "col_leg": "Leg", "col_dep": "Departure", "col_arr": "Arrival", "col_etd": "ETD", "col_eta": "ETA",
        "welcome_title": "Welcome on board",
        "welcome_text": (
            "You have just boarded a TOWT cargo sailing vessel as a passenger. You will share our daily life "
            "throughout the crossing, through our work on board, but above all during relaxation moments "
            "such as meals and evenings.<br/><br/>"
            "As a cargo vessel, no specific service is provided to you. However, we will be happy to share "
            "this crossing with you and introduce you to the merchant marine profession."
        ),
        "admin_title": "Administrative",
        "admin_text": (
            "• Your passport will be handed to the crew upon arrival on board and kept in a secure location.<br/>"
            "• Any serious medical treatment or health condition must be reported upon arrival.<br/>"
            "• A cabin key will be provided to you individually."
        ),
        "safety_title": "Safety",
        "safety_text": (
            "This vessel is a cargo sailboat with sea behavior similar to a pleasure yacht (heeling, rolling, pitching).<br/><br/>"
            "Please:<br/>"
            "• Secure and fasten your personal belongings.<br/>"
            "• Handle doors carefully and use handrails.<br/>"
            "• Wear non-slip shoes.<br/><br/>"
            "<b>Restricted access:</b><br/>"
            "• No access to the galley, engine room, holds, and kitchen (except outside service hours).<br/>"
            "• The bridge is only accessible outside maneuvers and with authorization.<br/><br/>"
            "Safety instructions and evacuation procedures must be followed in case of emergency. "
            "A mandatory drill is planned before departure."
        ),
        "health_title": "Health on board",
        "health_text": (
            "• The command is responsible for medical care on board, in liaison with the Toulouse Maritime Medical Center.<br/>"
            "• If you are prone to seasickness, we recommend bringing medication (Sea-band bracelet, Mercalm, etc.).<br/>"
            "• Any medical evacuation will be organized with the competent authorities if necessary."
        ),
        "life_title": "Life on board",
        "life_text": (
            "<b>Rest:</b> Please respect the crew's sleep schedule (shift work).<br/><br/>"
            "<b>Meals:</b><br/>"
            "• Breakfast is self-service.<br/>"
            "• Lunch at 12:10 PM.<br/>"
            "• Dinner at 8:00 PM.<br/>"
            "• No food in cabins.<br/>"
            "• Please report allergies and dietary requirements.<br/><br/>"
            "<b>Alcohol:</b> Dry ship. Occasional exceptions may be granted at the crew's discretion.<br/><br/>"
            "<b>Noise:</b> The vessel remains a noisy environment despite insulation. Bring earplugs if you are sensitive to noise."
        ),
        "housekeeping_title": "Housekeeping",
        "housekeeping_text": (
            "• Two sets of linen are provided.<br/>"
            "• You are responsible for your own laundry.<br/>"
            "• Washing machines can only be used depending on vessel stability.<br/>"
            "• You are responsible for cleaning your cabin. Products available at the wardroom entrance.<br/>"
            "• Cabin inspection will be carried out upon disembarkation."
        ),
        "waste_title": "Waste management",
        "waste_text": (
            "• No discharge at sea is permitted.<br/>"
            "• Strict compliance with waste sorting.<br/>"
            "• Food waste at sea only outside special areas, per regulations."
        ),
        "leisure_title": "Leisure & connectivity",
        "leisure_text": (
            "<b>Leisure:</b> Books, games, sport mats available. TV without subscription, gaming console at discretion. "
            "Fishing gear available (notify the bridge).<br/><br/>"
            "<b>Leisure tablet:</b> A tablet is available in the wardroom for reading (ePresse) and taking photos/videos.<br/><br/>"
            "<b>Internet:</b> A Wi-Fi code is provided. Please disable automatic updates and use airplane mode. "
            "Access limited by ship's bandwidth.<br/><br/>"
            "<b>Additional Wi-Fi plans:</b><br/>"
            "• Daily: 1 GB / 24h — €3<br/>"
            "• Weekly 1: 1 GB / 7 days — €3<br/>"
            "• Weekly 2: 2 GB / 7 days — €6<br/>"
            "• Monthly: 5 GB / 30 days — €15<br/>"
            "Payment via Revolut link through the Captain."
        ),
        "timezone_title": "Time zone changes",
        "timezone_text": "Ship time changes as the vessel progresses. Changes are announced the day before.",
        "shop_title": "On-board shop",
        "shop_text": (
            "A small shop offers: hygiene products, drinks, snacks, limited cigarettes. "
            "Payment via Revolut link."
        ),
        "forbidden_title": "Prohibited items on board",
        "forbidden_text": (
            "<b>1. Dangerous goods:</b> flammable/explosive materials, toxic chemicals, radioactive materials, drugs.<br/><br/>"
            "<b>2. Weapons:</b> firearms and ammunition, large blades, incapacitating sprays.<br/><br/>"
            "<b>3. Risky equipment:</b> uncertified lithium batteries, generators.<br/><br/>"
            "<b>4. Prohibited goods:</b> non-compliant food, unauthorized plants/seeds.<br/><br/>"
            "<b>5. Regulated objects:</b> drones, lasers, jamming devices.<br/><br/>"
            "Any passenger carrying such items will be subject to retention procedures and possible handover to authorities."
        ),
        "closing": "We wish you an excellent crossing!\nThe TOWT crew",
        "footer_co": "TOWT — Transoceanic Wind Transport · Cargo sailing",
        "generated": "Generated on",
        "page": "Page",
    },
}


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("CoverTitle", parent=s["Title"], fontSize=30, textColor=colors.white,
                         alignment=TA_CENTER, spaceAfter=10, fontName="Helvetica-Bold"))
    s.add(ParagraphStyle("CoverSub", parent=s["Normal"], fontSize=15, textColor=colors.white,
                         alignment=TA_CENTER, spaceAfter=6))
    s.add(ParagraphStyle("CoverMeta", parent=s["Normal"], fontSize=11, textColor=colors.HexColor("#cccccc"),
                         alignment=TA_CENTER, spaceAfter=4))
    s.add(ParagraphStyle("Sec", parent=s["Heading1"], fontSize=16, textColor=TOWT_BLUE,
                         spaceBefore=12, spaceAfter=6, fontName="Helvetica-Bold"))
    s.add(ParagraphStyle("Sub", parent=s["Heading2"], fontSize=12, textColor=TOWT_BLUE,
                         spaceBefore=8, spaceAfter=3, fontName="Helvetica-Bold"))
    s.add(ParagraphStyle("B", parent=s["Normal"], fontSize=9.5, textColor=TOWT_GRAY,
                         leading=13, alignment=TA_JUSTIFY, spaceAfter=3))
    return s


def _hr():
    return HRFlowable(width="100%", thickness=1, color=TOWT_GREEN, spaceAfter=6)


def _tbl(data, col_widths):
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TOWT_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, TOWT_LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def generate_crossing_book(leg, vessel, crew_list, pax_bookings, legs_voyage=None, lang="fr"):
    buf = BytesIO()
    styles = _styles()
    t = T.get(lang, T["fr"])

    pax_names = []
    for b in pax_bookings:
        for p in b.passengers:
            pax_names.append(p.full_name)

    def on_page(canvas, doc):
        pn = doc.page
        if pn == 1:
            canvas.setFillColor(TOWT_BLUE)
            canvas.rect(0, 0, W, H, fill=1, stroke=0)
            canvas.setStrokeColor(TOWT_GREEN)
            canvas.setLineWidth(3)
            canvas.line(40, H - 40, W - 40, H - 40)
            canvas.line(40, 40, W - 40, 40)
        else:
            canvas.setStrokeColor(TOWT_BLUE)
            canvas.setLineWidth(0.5)
            canvas.line(15*mm, H-12*mm, W-15*mm, H-12*mm)
            canvas.setFont("Helvetica", 7)
            canvas.setFillColor(colors.HexColor("#aaaaaa"))
            vn = vessel.name if vessel else ""
            lc = leg.leg_code if leg else ""
            canvas.drawString(15*mm, H-10*mm, f"TOWT — {vn} — {lc}")
            canvas.drawRightString(W-15*mm, H-10*mm, f"{t['page']} {pn}")
            canvas.line(15*mm, 12*mm, W-15*mm, 12*mm)
            canvas.drawCentredString(W/2, 7*mm, f"{t['footer_co']} · {t['generated']} {date.today().strftime('%d/%m/%Y')}")

    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18*mm, bottomMargin=18*mm, leftMargin=15*mm, rightMargin=15*mm)
    e = []

    # ── COVER ──
    e.append(Spacer(1, 45*mm))
    e.append(Paragraph("🚢", ParagraphStyle("E", parent=styles["CoverTitle"], fontSize=48)))
    e.append(Spacer(1, 4*mm))
    e.append(Paragraph(t["book_title"], styles["CoverTitle"]))
    e.append(Spacer(1, 8*mm))
    route = f"{leg.departure_port.name} → {leg.arrival_port.name}" if leg else "—"
    e.append(Paragraph(route, styles["CoverSub"]))
    e.append(Paragraph(vessel.name if vessel else "", styles["CoverSub"]))
    e.append(Spacer(1, 5*mm))
    etd = leg.etd.strftime("%d/%m/%Y") if leg and leg.etd else "—"
    eta = leg.eta.strftime("%d/%m/%Y") if leg and leg.eta else "—"
    e.append(Paragraph(f"{t['departure']} : {etd}  ·  {t['arrival']} : {eta}", styles["CoverMeta"]))
    e.append(Paragraph(f"{t['voyage']} : {leg.leg_code}" if leg else "", styles["CoverMeta"]))
    if pax_names:
        e.append(Spacer(1, 8*mm))
        e.append(Paragraph(f"{t['passengers']} : {', '.join(pax_names)}", styles["CoverMeta"]))
    e.append(Spacer(1, 25*mm))
    e.append(Paragraph("TOWT — Transoceanic Wind Transport", styles["CoverMeta"]))
    e.append(Paragraph("Les Docks, 52 quai Frissard — 76600 Le Havre", styles["CoverMeta"]))
    e.append(PageBreak())

    # ── VESSEL ──
    e.append(Paragraph(t["vessel_title"], styles["Sec"])); e.append(_hr())
    info = [
        (t["name"], vessel.name), (t["imo"], vessel.imo_number or "—"), (t["flag"], vessel.flag or "—"),
        (t["dwt"], f"{vessel.dwt:.0f} t" if vessel.dwt else "—"),
        (t["capacity"], f"{vessel.capacity_palettes} palettes" if vessel.capacity_palettes else "—"),
        (t["speed"], f"{vessel.default_speed:.1f} kn" if vessel.default_speed else "—"),
    ]
    tb = Table(info, colWidths=[140, 380])
    tb.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), TOWT_BLUE), ("TEXTCOLOR", (1, 0), (1, -1), TOWT_GRAY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    e.append(tb); e.append(Spacer(1, 4*mm))
    e.append(Paragraph(t["vessel_intro"], styles["B"]))
    e.append(PageBreak())

    # ── CREW ──
    e.append(Paragraph(t["crew_title"], styles["Sec"])); e.append(_hr())
    if crew_list:
        data = [[t["col_name"], t["col_role"]]]
        for ca in crew_list:
            data.append([ca.member.full_name, ca.member.role_label])
        e.append(_tbl(data, [260, 260]))
    e.append(Spacer(1, 4*mm)); e.append(Paragraph(t["crew_intro"], styles["B"]))
    e.append(Spacer(1, 6*mm))

    # ── ITINERARY ──
    e.append(Paragraph(t["itin_title"], styles["Sec"])); e.append(_hr())
    if legs_voyage:
        data = [[t["col_leg"], t["col_dep"], t["col_arr"], t["col_etd"], t["col_eta"]]]
        for l in legs_voyage:
            data.append([
                l.leg_code,
                l.departure_port.name if l.departure_port else "—",
                l.arrival_port.name if l.arrival_port else "—",
                l.etd.strftime("%d/%m/%Y") if l.etd else "—",
                l.eta.strftime("%d/%m/%Y") if l.eta else "—",
            ])
        e.append(_tbl(data, [80, 120, 120, 80, 80]))
    e.append(Spacer(1, 3*mm)); e.append(Paragraph(t["itin_note"], styles["B"]))
    e.append(PageBreak())

    # ── WELCOME + RULES ──
    for key in ["welcome", "admin", "safety", "health", "life", "housekeeping", "waste", "leisure", "timezone", "shop"]:
        e.append(Paragraph(t[f"{key}_title"], styles["Sec"])); e.append(_hr())
        e.append(Paragraph(t[f"{key}_text"], styles["B"]))
        e.append(Spacer(1, 3*mm))
        if key in ("safety", "life", "shop"):
            e.append(PageBreak())

    # ── FORBIDDEN ──
    e.append(Paragraph(t["forbidden_title"], styles["Sec"])); e.append(_hr())
    e.append(Paragraph(t["forbidden_text"], styles["B"]))
    e.append(PageBreak())

    # ── CLOSING ──
    e.append(Spacer(1, 30*mm))
    e.append(_hr())
    e.append(Paragraph(
        t["closing"].replace("\n", "<br/>"),
        ParagraphStyle("Fin", parent=styles["B"], fontSize=13, textColor=TOWT_BLUE,
                       alignment=TA_CENTER, fontName="Helvetica-BoldOblique")
    ))
    e.append(Spacer(1, 10*mm))
    e.append(Paragraph("www.towt.eu", ParagraphStyle("url", parent=styles["B"], alignment=TA_CENTER, fontSize=10, textColor=TOWT_GREEN)))

    doc.build(e, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
