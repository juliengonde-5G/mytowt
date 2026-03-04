"""
Seed demo data for all modules — based on existing legs.

Creates:
  1. Crew members + assignments (per vessel)
  2. Clients + Rate grids (grilles tarifaires)
  3. Orders (ordres de transport) + assignments
  4. Packing lists + batches
  5. Cabin price grids
  6. Passenger bookings + passengers + payments
  7. Escale operations + docker shifts
  8. SOF events (Statement of Facts)
  9. Claims + timeline
  10. Leg finances
  11. Port configs
  12. OPEX parameters

Usage (inside Docker):
    docker exec towt-app-v2 mkdir -p /app/scripts
    docker cp scripts/seed_demo_data.py towt-app-v2:/app/scripts/seed_demo_data.py
    docker exec towt-app-v2 python3 /app/scripts/seed_demo_data.py
"""
import asyncio
import os
import sys
import json
import secrets
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select, func, text
from app.database import engine, async_session
from app.models.leg import Leg
from app.models.vessel import Vessel
from app.models.port import Port
from app.models.order import Order, OrderAssignment
from app.models.packing_list import PackingList, PackingListBatch
from app.models.operation import EscaleOperation, DockerShift
from app.models.onboard import SofEvent, CargoDocument
from app.models.passenger import (
    PassengerBooking, Passenger, PassengerPayment, CabinPriceGrid,
)
from app.models.crew import CrewMember, CrewAssignment
from app.models.finance import LegFinance, PortConfig, OpexParameter
from app.models.claim import Claim, ClaimTimeline
from app.models.commercial import Client, RateGrid, RateGridLine
from app.models.kpi import LegKPI


# ─── HELPERS ───────────────────────────────────────────────────
def dt(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def d(year, month, day):
    return date(year, month, day)


def gen_ref(prefix, idx):
    return f"{prefix}-2026-{idx:04d}"


def gen_booking_ref(idx):
    return f"PAX-20260301-{secrets.token_hex(3).upper()}{idx}"


# ─── MAIN ──────────────────────────────────────────────────────
async def main():
    async with async_session() as db:
        # ─── Load existing data ──────────────────────────────
        legs = (await db.execute(
            select(Leg).order_by(Leg.vessel_id, Leg.sequence)
        )).scalars().all()
        vessels = (await db.execute(select(Vessel).order_by(Vessel.code))).scalars().all()
        ports = {p.locode: p for p in (await db.execute(select(Port))).scalars().all()}

        if not legs:
            print("ERROR: No legs found in database. Please create legs first.")
            return

        print(f"Found {len(legs)} legs, {len(vessels)} vessels, {len(ports)} ports")
        for leg in legs:
            print(f"  {leg.leg_code} | vessel={leg.vessel_id} | {leg.departure_port_locode} -> {leg.arrival_port_locode} | status={leg.status}")

        vessel_by_id = {v.id: v for v in vessels}

        # ─── Check what already exists ───────────────────────
        existing_crew = (await db.execute(select(func.count(CrewMember.id)))).scalar()
        existing_orders = (await db.execute(select(func.count(Order.id)))).scalar()
        existing_clients = (await db.execute(select(func.count(Client.id)))).scalar()

        # ═══════════════════════════════════════════════════════
        # 1. OPEX PARAMETERS
        # ═══════════════════════════════════════════════════════
        print("\n── 1. OPEX Parameters ──")
        existing_opex = (await db.execute(
            select(OpexParameter).where(OpexParameter.parameter_name == "opex_daily_rate")
        )).scalar_one_or_none()
        if not existing_opex:
            db.add(OpexParameter(
                parameter_name="opex_daily_rate",
                parameter_value=11600,
                unit="EUR/day",
                category="fleet",
                description="OPEX journalier moyen flotte TOWT"
            ))
            print("  Created opex_daily_rate = 11600 EUR/day")
        else:
            print("  OPEX already exists, skipping")

        # ═══════════════════════════════════════════════════════
        # 2. PORT CONFIGS
        # ═══════════════════════════════════════════════════════
        print("\n── 2. Port Configs ──")
        port_configs_data = {
            "FRFEC": {"port_cost_total": 8500, "cost_per_palette": 18, "daily_quay_cost": 1200, "notes": "Port de Fécamp — TOWT home port"},
            "FRLEH": {"port_cost_total": 15000, "cost_per_palette": 22, "daily_quay_cost": 2500, "notes": "Le Havre — grand port industriel"},
            "BRSSO": {"port_cost_total": 12000, "cost_per_palette": 25, "daily_quay_cost": 1800, "notes": "São Sebastião — Brésil"},
            "BRSSZ": {"port_cost_total": 13500, "cost_per_palette": 28, "daily_quay_cost": 2000, "notes": "Santos — Brésil"},
            "COBAQ": {"port_cost_total": 11000, "cost_per_palette": 22, "daily_quay_cost": 1500, "notes": "Barranquilla — Colombie"},
            "COPBG": {"port_cost_total": 9500, "cost_per_palette": 20, "daily_quay_cost": 1400, "notes": "Providencia / San Andrés"},
            "MXVER": {"port_cost_total": 10500, "cost_per_palette": 20, "daily_quay_cost": 1600, "notes": "Veracruz — Mexique"},
            "USNYC": {"port_cost_total": 22000, "cost_per_palette": 35, "daily_quay_cost": 3500, "notes": "New York — USA"},
            "GBSOU": {"port_cost_total": 12000, "cost_per_palette": 24, "daily_quay_cost": 2000, "notes": "Southampton — UK"},
            "ESLPA": {"port_cost_total": 7500, "cost_per_palette": 16, "daily_quay_cost": 1000, "notes": "Las Palmas — Canaries"},
            "PTLIS": {"port_cost_total": 9000, "cost_per_palette": 19, "daily_quay_cost": 1300, "notes": "Lisbonne — Portugal"},
            "VNSGN": {"port_cost_total": 8000, "cost_per_palette": 15, "daily_quay_cost": 900, "notes": "Ho Chi Minh Ville — Vietnam"},
        }
        for locode, data in port_configs_data.items():
            if locode not in ports:
                continue
            existing = (await db.execute(
                select(PortConfig).where(PortConfig.port_locode == locode)
            )).scalar_one_or_none()
            if not existing:
                db.add(PortConfig(port_locode=locode, accessible=True, **data))
                print(f"  Created config for {locode}")

        # ═══════════════════════════════════════════════════════
        # 3. CREW MEMBERS
        # ═══════════════════════════════════════════════════════
        print("\n── 3. Crew Members ──")
        crew_data = [
            # Anemos crew
            {"first_name": "Jean-Pierre", "last_name": "Morin", "role": "capitaine", "phone": "+33 6 12 34 56 78", "email": "jp.morin@towt.eu"},
            {"first_name": "Yann", "last_name": "Le Gall", "role": "second", "phone": "+33 6 23 45 67 89", "email": "y.legall@towt.eu"},
            {"first_name": "Marc", "last_name": "Dubois", "role": "chef_mecanicien", "phone": "+33 6 34 56 78 90", "email": "m.dubois@towt.eu"},
            {"first_name": "Sébastien", "last_name": "Perrot", "role": "lieutenant", "phone": "+33 6 45 67 89 01", "email": "s.perrot@towt.eu"},
            {"first_name": "Thierry", "last_name": "Blanchard", "role": "bosco", "phone": "+33 6 56 78 90 12", "email": "t.blanchard@towt.eu"},
            {"first_name": "Philippe", "last_name": "Tanguy", "role": "cook", "phone": "+33 6 67 89 01 23", "email": "p.tanguy@towt.eu"},
            {"first_name": "Lucas", "last_name": "Kervella", "role": "marin", "phone": "+33 6 78 90 12 34", "email": "l.kervella@towt.eu"},
            {"first_name": "Erwan", "last_name": "Quéré", "role": "marin", "phone": "+33 6 89 01 23 45", "email": "e.quere@towt.eu"},
            # Artemis crew
            {"first_name": "Guillaume", "last_name": "Bertrand", "role": "capitaine", "phone": "+33 6 11 22 33 44", "email": "g.bertrand@towt.eu"},
            {"first_name": "Loïc", "last_name": "Guégan", "role": "second", "phone": "+33 6 22 33 44 55", "email": "l.guegan@towt.eu"},
            {"first_name": "Pierre", "last_name": "Le Bras", "role": "chef_mecanicien", "phone": "+33 6 33 44 55 66", "email": "p.lebras@towt.eu"},
            {"first_name": "Mathieu", "last_name": "Hervé", "role": "lieutenant", "phone": "+33 6 44 55 66 77", "email": "m.herve@towt.eu"},
            {"first_name": "Nicolas", "last_name": "Corre", "role": "bosco", "phone": "+33 6 55 66 77 88", "email": "n.corre@towt.eu"},
            {"first_name": "Antoine", "last_name": "Madec", "role": "cook", "phone": "+33 6 66 77 88 99", "email": "a.madec@towt.eu"},
            {"first_name": "Julien", "last_name": "Riou", "role": "marin", "phone": "+33 6 77 88 99 00", "email": "j.riou@towt.eu"},
        ]
        crew_members = []
        if existing_crew == 0:
            for cd in crew_data:
                cm = CrewMember(**cd)
                db.add(cm)
                crew_members.append(cm)
            await db.flush()
            print(f"  Created {len(crew_members)} crew members")
        else:
            crew_members = (await db.execute(select(CrewMember))).scalars().all()
            print(f"  Crew already exists ({len(crew_members)} members), skipping creation")

        # ═══════════════════════════════════════════════════════
        # 4. CREW ASSIGNMENTS (link crew to vessels based on legs)
        # ═══════════════════════════════════════════════════════
        print("\n── 4. Crew Assignments ──")
        existing_assignments = (await db.execute(select(func.count(CrewAssignment.id)))).scalar()
        if existing_assignments == 0 and crew_members:
            # Assign first 8 crew to vessel 1 (Anemos), rest to vessel 2 (Artemis)
            anemos_legs = [l for l in legs if l.vessel_id == (vessels[0].id if vessels else 1)]
            artemis_legs = [l for l in legs if len(vessels) > 1 and l.vessel_id == vessels[1].id]

            for i, cm in enumerate(crew_members):
                if i < 8 and vessels:
                    vessel = vessels[0]
                    first_leg = anemos_legs[0] if anemos_legs else legs[0]
                elif len(vessels) > 1:
                    vessel = vessels[1]
                    first_leg = artemis_legs[0] if artemis_legs else legs[0]
                else:
                    vessel = vessels[0]
                    first_leg = legs[0]

                embark = first_leg.etd.date() if first_leg.etd else d(2026, 1, 15)
                ca = CrewAssignment(
                    member_id=cm.id,
                    vessel_id=vessel.id,
                    embark_date=embark,
                    embark_leg_id=first_leg.id,
                    status="active",
                    notes=f"Embarqué à {first_leg.departure_port_locode}"
                )
                db.add(ca)
            await db.flush()
            print(f"  Created {len(crew_members)} crew assignments")
        else:
            print(f"  Assignments already exist ({existing_assignments}), skipping")

        # ═══════════════════════════════════════════════════════
        # 5. CLIENTS
        # ═══════════════════════════════════════════════════════
        print("\n── 5. Clients ──")
        clients_data = [
            {"name": "Biocoop International", "client_type": "shipper", "contact_name": "Marie Lefèvre", "contact_email": "m.lefevre@biocoop-intl.fr", "contact_phone": "+33 1 45 67 89 00", "address": "12 rue du Commerce, 75015 Paris", "country": "France"},
            {"name": "Ethiquable", "client_type": "shipper", "contact_name": "Thomas Durand", "contact_email": "t.durand@ethiquable.coop", "contact_phone": "+33 5 62 96 18 00", "address": "Chemin du Bois, 32600 Fleurance", "country": "France"},
            {"name": "Café Michel", "client_type": "shipper", "contact_name": "Laurent Petit", "contact_email": "l.petit@cafemichel.fr", "contact_phone": "+33 4 68 35 22 10", "address": "ZA Les Music, 66000 Perpignan", "country": "France"},
            {"name": "TransGlobal Freight", "client_type": "freight_forwarder", "contact_name": "Sarah Johnson", "contact_email": "s.johnson@transglobal.com", "contact_phone": "+44 20 7946 0958", "address": "22 Dock Road, Southampton SO14 3GG", "country": "United Kingdom"},
            {"name": "Deloitte Maritime Logistics", "client_type": "freight_forwarder", "contact_name": "Jean-Marc Hamon", "contact_email": "jm.hamon@deloitte-maritime.fr", "contact_phone": "+33 2 35 19 44 00", "address": "Quai de la Saône, 76600 Le Havre", "country": "France"},
        ]
        clients = []
        if existing_clients == 0:
            for cd in clients_data:
                c = Client(**cd)
                db.add(c)
                clients.append(c)
            await db.flush()
            print(f"  Created {len(clients)} clients")
        else:
            clients = (await db.execute(select(Client).order_by(Client.id))).scalars().all()
            print(f"  Clients already exist ({len(clients)}), skipping")

        # ═══════════════════════════════════════════════════════
        # 6. RATE GRIDS (Grilles Tarifaires)
        # ═══════════════════════════════════════════════════════
        print("\n── 6. Rate Grids ──")
        existing_grids = (await db.execute(select(func.count(RateGrid.id)))).scalar()
        rate_grids = []
        if existing_grids == 0 and clients:
            # Get unique routes from legs
            routes = set()
            for leg in legs:
                routes.add((leg.departure_port_locode, leg.arrival_port_locode))

            grid_idx = 1
            for client in clients:
                rg = RateGrid(
                    reference=gen_ref("RG", grid_idx),
                    client_id=client.id,
                    vessel_id=vessels[0].id if vessels else None,
                    valid_from=d(2026, 1, 1),
                    valid_to=d(2026, 12, 31),
                    adjustment_index=1.0,
                    bl_fee=85.0,
                    booking_fee=50.0,
                    brackets_json=json.dumps([
                        {"key": "lt50", "label": "< 50 palettes", "max_qty": 49, "coeff": 1.10},
                        {"key": "100", "label": "100 palettes", "max_qty": 100, "coeff": 1.00},
                        {"key": "200", "label": "200 palettes", "max_qty": 200, "coeff": 0.80},
                        {"key": "300", "label": "300 palettes", "max_qty": 300, "coeff": 0.80},
                        {"key": "400", "label": "400 palettes", "max_qty": 400, "coeff": 0.80},
                        {"key": "500", "label": "500 palettes", "max_qty": 500, "coeff": 0.70},
                        {"key": "full", "label": "Full ship (850 pal.)", "max_qty": 850, "coeff": 0.60},
                    ]) if client.client_type == "shipper" else json.dumps([
                        {"key": "flat", "label": "Tarif unique", "max_qty": 99999, "coeff": 1.00},
                    ]),
                    volume_commitment=50 if client.client_type == "shipper" else None,
                    status="active",
                    notes=f"Grille tarifaire {client.name} — saison 2026",
                    created_by="admin",
                )
                db.add(rg)
                await db.flush()

                # Add lines for each route
                for pol, pod in routes:
                    # Calculate distance from leg data
                    matching_leg = next((l for l in legs if l.departure_port_locode == pol and l.arrival_port_locode == pod), None)
                    dist = matching_leg.distance_nm if matching_leg and matching_leg.distance_nm else 3000
                    nav_days = round(dist / (8 * 24), 2)
                    opex = 11600
                    base_rate = round(opex * nav_days / 850, 2)

                    if client.client_type == "shipper":
                        rates = {
                            "lt50": round(base_rate * 1.10, 2),
                            "100": round(base_rate * 1.00, 2),
                            "200": round(base_rate * 0.80, 2),
                            "300": round(base_rate * 0.80, 2),
                            "400": round(base_rate * 0.80, 2),
                            "500": round(base_rate * 0.70, 2),
                            "full": round(base_rate * 0.60, 2),
                        }
                    else:
                        rates = {"flat": round(base_rate * 0.95, 2)}

                    rgl = RateGridLine(
                        rate_grid_id=rg.id,
                        pol_locode=pol,
                        pod_locode=pod,
                        leg_id=matching_leg.id if matching_leg else None,
                        distance_nm=dist,
                        nav_days=nav_days,
                        opex_daily=opex,
                        base_rate=base_rate,
                        rates_json=json.dumps(rates),
                    )
                    db.add(rgl)

                rate_grids.append(rg)
                grid_idx += 1
            await db.flush()
            print(f"  Created {len(rate_grids)} rate grids with route lines")
        else:
            print(f"  Rate grids already exist ({existing_grids}), skipping")

        # ═══════════════════════════════════════════════════════
        # 7. ORDERS (Ordres de Transport)
        # ═══════════════════════════════════════════════════════
        print("\n── 7. Orders ──")
        orders = []
        if existing_orders == 0:
            # Define realistic order scenarios per leg
            order_scenarios = [
                # Client name, qty palettes, format, unit_price, description, status
                ("Biocoop International", 120, "EPAL", 245.00, "Café bio Colombie — torréfié", "confirme"),
                ("Ethiquable", 80, "EPAL", 260.00, "Chocolat noir 70% bio — origine Pérou", "confirme"),
                ("Café Michel", 200, "EPAL", 210.00, "Café vert Arabica — São Sebastião", "confirme"),
                ("TransGlobal Freight", 150, "USPAL", 280.00, "Rhum agricole AOC Martinique", "reserve"),
                ("Biocoop International", 60, "EPAL", 255.00, "Thé vert bio — Vietnam", "confirme"),
                ("Deloitte Maritime Logistics", 300, "EPAL", 195.00, "Cacao en fèves — Côte d'Ivoire", "confirme"),
                ("Ethiquable", 45, "EPAL", 310.00, "Épices bio — curcuma, poivre, cannelle", "reserve"),
                ("Café Michel", 100, "EPAL", 230.00, "Sucre de canne bio — Brésil", "confirme"),
                ("Biocoop International", 180, "EPAL", 220.00, "Quinoa bio — Pérou", "non_affecte"),
                ("TransGlobal Freight", 90, "USPAL", 290.00, "Vanille bourbon — Madagascar", "reserve"),
            ]

            order_idx = 1
            for i, (client_name, qty, fmt, price, desc, status) in enumerate(order_scenarios):
                leg = legs[i % len(legs)]
                order = Order(
                    reference=gen_ref("OT", order_idx),
                    client_name=client_name,
                    client_contact=next((c.contact_name for c in clients if c.name == client_name), None) if clients else None,
                    quantity_palettes=qty,
                    palette_format=fmt,
                    weight_per_palette=0.8,
                    unit_price=price,
                    thc_included=i % 3 == 0,
                    description=desc,
                    booking_fee=50.0,
                    documentation_fee=85.0,
                    delivery_date_start=leg.etd.date() - timedelta(days=5) if leg.etd else d(2026, 3, 1),
                    delivery_date_end=leg.eta.date() + timedelta(days=10) if leg.eta else d(2026, 5, 1),
                    departure_locode=leg.departure_port_locode,
                    arrival_locode=leg.arrival_port_locode,
                    status=status,
                    leg_id=leg.id if status != "non_affecte" else None,
                )
                order.compute_total()
                db.add(order)
                await db.flush()

                # Create assignment if assigned to a leg
                if status in ("reserve", "confirme"):
                    oa = OrderAssignment(
                        order_id=order.id,
                        leg_id=leg.id,
                        confirmed=status == "confirme",
                        notes=f"Affecté au {leg.leg_code}"
                    )
                    db.add(oa)

                orders.append(order)
                order_idx += 1

            await db.flush()
            print(f"  Created {len(orders)} orders")
        else:
            orders = (await db.execute(select(Order).order_by(Order.id))).scalars().all()
            print(f"  Orders already exist ({len(orders)}), skipping")

        # ═══════════════════════════════════════════════════════
        # 8. PACKING LISTS
        # ═══════════════════════════════════════════════════════
        print("\n── 8. Packing Lists ──")
        existing_pl = (await db.execute(select(func.count(PackingList.id)))).scalar()
        if existing_pl == 0 and orders:
            confirmed_orders = [o for o in orders if o.status == "confirme" and o.leg_id]
            pl_count = 0
            for order in confirmed_orders:
                leg = next((l for l in legs if l.id == order.leg_id), None)
                if not leg:
                    continue
                vessel = vessel_by_id.get(leg.vessel_id)

                pl = PackingList(order_id=order.id, status="submitted" if pl_count % 3 != 0 else "draft")
                db.add(pl)
                await db.flush()

                # Determine shipper/consignee based on route
                shipper_info = {
                    "FR": ("Coopérative Agricole Bio", "14 rue du Port", "76400", "Fécamp", "France"),
                    "BR": ("Fazenda Orgânica Ltda", "Rua das Palmeiras 45", "11600-000", "São Sebastião", "Brésil"),
                    "CO": ("Finca Cafetera El Dorado", "Calle 23 #15-42", "680001", "Barranquilla", "Colombie"),
                    "MX": ("Exportadora Maya SA", "Av. Insurgentes 1205", "91700", "Veracruz", "Mexique"),
                    "VN": ("Saigon Trade Co.", "12 Nguyen Hue Blvd", "700000", "Ho Chi Minh", "Vietnam"),
                }
                consignee_info = {
                    "FR": ("Entrepôt TOWT Fécamp", "Quai de la Vicomté", "76400", "Fécamp", "France"),
                    "BR": ("Armazém Santos Sul", "Av. Portuária 300", "11013-000", "Santos", "Brésil"),
                    "US": ("Brooklyn Navy Yard Warehouse", "63 Flushing Ave", "NY 11205", "New York", "USA"),
                    "GB": ("Southampton Docks Ltd", "22 Dock Road", "SO14 3GG", "Southampton", "UK"),
                }

                dep_country = leg.departure_port_locode[:2]
                arr_country = leg.arrival_port_locode[:2]
                shipper = shipper_info.get(dep_country, shipper_info["FR"])
                consignee = consignee_info.get(arr_country, consignee_info["FR"])

                batch = PackingListBatch(
                    packing_list_id=pl.id,
                    batch_number=1,
                    voyage_id=leg.leg_code,
                    vessel=vessel.name if vessel else "Anemos",
                    loading_date=leg.etd.date() if leg.etd else d(2026, 3, 15),
                    pol_code=leg.departure_port_locode,
                    pod_code=leg.arrival_port_locode,
                    pol_name=ports.get(leg.departure_port_locode, Port(name="Unknown")).name,
                    pod_name=ports.get(leg.arrival_port_locode, Port(name="Unknown")).name,
                    booking_confirmation=order.reference,
                    freight_rate=order.unit_price,
                    bill_of_lading_id=f"TUAW_{leg.leg_code}_{pl_count + 1:03d}",
                    stackable="Yes" if pl_count % 2 == 0 else "No",
                    customer_name=order.client_name,
                    shipper_name=shipper[0],
                    shipper_address=shipper[1],
                    shipper_postal=shipper[2],
                    shipper_city=shipper[3],
                    shipper_country=shipper[4],
                    consignee_name=consignee[0],
                    consignee_address=consignee[1],
                    consignee_postal=consignee[2],
                    consignee_city=consignee[3],
                    consignee_country=consignee[4],
                    notify_name=order.client_name,
                    notify_address="Identique destinataire",
                    notify_postal=consignee[2],
                    notify_city=consignee[3],
                    notify_country=consignee[4],
                    pallet_type=order.palette_format,
                    type_of_goods=order.description,
                    description_of_goods=f"{order.description}\n{order.quantity_palettes} palettes {order.palette_format}\nPoids brut: {order.total_weight:.1f} tonnes",
                    pallet_quantity=order.quantity_palettes,
                    length_cm=120,
                    width_cm=80 if order.palette_format == "EPAL" else 100,
                    height_cm=180,
                    weight_kg=order.total_weight * 1000 / order.quantity_palettes if order.quantity_palettes else 800,
                    cargo_value_usd=order.total_price * 1.08 if order.total_price else 0,
                    freight_forwarder=next((c.name for c in clients if c.client_type == "freight_forwarder"), None) if clients else None,
                )
                batch.compute_dimensions()
                db.add(batch)
                pl_count += 1

            await db.flush()
            print(f"  Created {pl_count} packing lists with batches")
        else:
            print(f"  Packing lists already exist ({existing_pl}), skipping")

        # ═══════════════════════════════════════════════════════
        # 9. CABIN PRICE GRID
        # ═══════════════════════════════════════════════════════
        print("\n── 9. Cabin Price Grid ──")
        existing_cpg = (await db.execute(select(func.count(CabinPriceGrid.id)))).scalar()
        if existing_cpg == 0:
            routes_for_pax = set()
            for leg in legs:
                routes_for_pax.add((leg.departure_port_locode, leg.arrival_port_locode))

            cpg_count = 0
            for pol, pod in routes_for_pax:
                if pol not in ports or pod not in ports:
                    continue
                for cabin_type, price_base in [("double", 4200), ("twin", 3800)]:
                    cpg = CabinPriceGrid(
                        origin_locode=pol,
                        destination_locode=pod,
                        cabin_type=cabin_type,
                        price=Decimal(str(price_base)),
                        deposit_pct=30,
                        notes=f"Tarif {cabin_type} {pol} → {pod} — saison 2026",
                        is_active=True,
                    )
                    db.add(cpg)
                    cpg_count += 1
            await db.flush()
            print(f"  Created {cpg_count} cabin price entries")
        else:
            print(f"  Cabin price grid already exists ({existing_cpg}), skipping")

        # ═══════════════════════════════════════════════════════
        # 10. PASSENGER BOOKINGS
        # ═══════════════════════════════════════════════════════
        print("\n── 10. Passenger Bookings ──")
        existing_bookings = (await db.execute(select(func.count(PassengerBooking.id)))).scalar()
        if existing_bookings == 0:
            pax_scenarios = [
                # (cabin_number, status, pax_data, contact_email)
                (1, "confirmed", [
                    ("Claire", "Dupont", "FR", "claire.dupont@gmail.com", "+33 6 12 34 56 78", d(1985, 4, 12)),
                    ("Marc", "Dupont", "FR", "marc.dupont@gmail.com", "+33 6 23 45 67 89", d(1983, 9, 25)),
                ], "claire.dupont@gmail.com"),
                (2, "paid", [
                    ("Hans", "Müller", "DE", "hans.mueller@web.de", "+49 170 1234567", d(1978, 7, 3)),
                    ("Ingrid", "Müller", "DE", "ingrid.mueller@web.de", "+49 170 2345678", d(1980, 11, 18)),
                ], "hans.mueller@web.de"),
                (3, "confirmed", [
                    ("John", "Smith", "GB", "j.smith@outlook.com", "+44 7700 900123", d(1990, 1, 30)),
                ], "j.smith@outlook.com"),
                (4, "draft", [
                    ("Yuki", "Tanaka", "JP", "yuki.tanaka@gmail.com", "+81 90 1234 5678", d(1992, 6, 8)),
                    ("Kenji", "Tanaka", "JP", "kenji.tanaka@gmail.com", "+81 90 2345 6789", d(1991, 12, 15)),
                ], "yuki.tanaka@gmail.com"),
            ]

            # Book on first 2 legs that have vessels with cabins (vessel_id 1 or 2)
            pax_legs = [l for l in legs if l.vessel_id in (1, 2)][:2]
            if not pax_legs:
                pax_legs = legs[:2]

            booking_idx = 0
            for leg in pax_legs:
                for cabin_no, status, passengers_data, email in pax_scenarios:
                    price_total = Decimal("4200") if cabin_no <= 2 else Decimal("3800")
                    price_total = price_total * len(passengers_data)
                    price_deposit = round(price_total * Decimal("0.30"), 2)

                    booking = PassengerBooking(
                        leg_id=leg.id,
                        vessel_id=leg.vessel_id,
                        cabin_number=cabin_no,
                        reference=gen_booking_ref(booking_idx),
                        status=status,
                        booking_date=d(2026, 1, 15) + timedelta(days=booking_idx * 3),
                        price_total=price_total,
                        price_deposit=price_deposit,
                        price_balance=price_total - price_deposit,
                        contact_email=email,
                        contact_phone=passengers_data[0][4],
                    )
                    db.add(booking)
                    await db.flush()

                    # Add passengers
                    for first, last, nationality, pax_email, phone, dob in passengers_data:
                        pax = Passenger(
                            booking_id=booking.id,
                            first_name=first,
                            last_name=last,
                            email=pax_email,
                            phone=phone,
                            date_of_birth=dob,
                            nationality=nationality,
                            passport_number=f"{nationality}{secrets.token_hex(4).upper()}",
                            emergency_contact_name=f"Contact urgence {last}",
                            emergency_contact_phone="+33 1 00 00 00 00",
                        )
                        db.add(pax)

                    # Add payment for confirmed/paid bookings
                    if status in ("confirmed", "paid"):
                        # Deposit payment
                        db.add(PassengerPayment(
                            booking_id=booking.id,
                            payment_type="acompte",
                            payment_method="virement",
                            amount=price_deposit,
                            status="received",
                            reference=f"VIR-{booking.reference}",
                            due_date=d(2026, 2, 1) + timedelta(days=booking_idx),
                            paid_date=d(2026, 2, 5) + timedelta(days=booking_idx),
                        ))
                    if status == "paid":
                        # Balance payment
                        db.add(PassengerPayment(
                            booking_id=booking.id,
                            payment_type="solde",
                            payment_method="revolut",
                            amount=price_total - price_deposit,
                            status="received",
                            reference=f"REV-{booking.reference}",
                            due_date=d(2026, 2, 15) + timedelta(days=booking_idx),
                            paid_date=d(2026, 2, 20) + timedelta(days=booking_idx),
                        ))

                    booking_idx += 1

            await db.flush()
            print(f"  Created {booking_idx} passenger bookings")
        else:
            print(f"  Bookings already exist ({existing_bookings}), skipping")

        # ═══════════════════════════════════════════════════════
        # 11. ESCALE OPERATIONS + DOCKER SHIFTS
        # ═══════════════════════════════════════════════════════
        print("\n── 11. Escale Operations ──")
        existing_ops = (await db.execute(select(func.count(EscaleOperation.id)))).scalar()
        if existing_ops == 0:
            op_count = 0
            ds_count = 0
            for leg in legs:
                base_date = leg.eta or leg.etd or dt(2026, 3, 15)
                if isinstance(base_date, date) and not isinstance(base_date, datetime):
                    base_date = datetime.combine(base_date, datetime.min.time()).replace(tzinfo=timezone.utc)

                # Operations for this leg's port call
                ops_data = [
                    ("technique", "soutage", base_date + timedelta(hours=4), base_date + timedelta(hours=8), 4.0,
                     "Total Energies Marine", "Soutage MDO — 25 m³", 4500, 4200),
                    ("technique", "intervention_technique", base_date + timedelta(hours=10), base_date + timedelta(hours=14), 4.0,
                     "Chantier Naval Fécamp", "Inspection coque + anodes", 3200, 3500),
                    ("relations_externes", "relation_client", base_date + timedelta(hours=6), base_date + timedelta(hours=8), 2.0,
                     "Biocoop International", "Visite clients + dégustation produits", 800, 750),
                    ("relations_externes", "relation_presse", base_date + timedelta(hours=9), base_date + timedelta(hours=11), 2.0,
                     "France 3 Normandie", "Reportage TV sur le transport à la voile", 0, 0),
                    ("armement", "avitaillement", base_date + timedelta(hours=2), base_date + timedelta(hours=4), 2.0,
                     "Metro Cash & Carry", "Avitaillement vivres 15 jours — 8 crew + 4 pax", 2800, 2650),
                    ("armement", "medicale", base_date + timedelta(hours=12), base_date + timedelta(hours=13), 1.0,
                     "Dr. Leblanc — Médecine Maritime", "Visite médicale annuelle marin Kervella", 180, 180),
                    ("technique", "inspection_technique", base_date + timedelta(days=1), base_date + timedelta(days=1, hours=3), 3.0,
                     "Bureau Veritas", "Inspection classe — vérification gréement", 1500, None),
                ]

                for op_type, action, planned_s, planned_e, dur, interv, desc, cost_f, cost_a in ops_data:
                    op = EscaleOperation(
                        leg_id=leg.id,
                        operation_type=op_type,
                        action=action,
                        planned_start=planned_s,
                        planned_end=planned_e,
                        planned_duration_hours=dur,
                        actual_start=planned_s + timedelta(minutes=15) if cost_a is not None else None,
                        actual_end=planned_e + timedelta(minutes=30) if cost_a is not None else None,
                        actual_duration_hours=dur + 0.5 if cost_a is not None else None,
                        intervenant=interv,
                        description=desc,
                        cost_forecast=cost_f,
                        cost_actual=cost_a,
                    )
                    db.add(op)
                    op_count += 1

                # Docker Shifts for loading/unloading
                for hold_idx, hold_name in enumerate(["Cale avant", "Cale arrière"], 1):
                    load_start = base_date + timedelta(hours=6 + hold_idx * 2)
                    ds = DockerShift(
                        leg_id=leg.id,
                        hold=f"Cale {hold_idx}",
                        planned_start=load_start,
                        planned_end=load_start + timedelta(hours=6),
                        actual_start=load_start + timedelta(minutes=20) if leg.status != "planned" else None,
                        actual_end=load_start + timedelta(hours=6, minutes=45) if leg.status != "planned" else None,
                        planned_palettes=200 + hold_idx * 50,
                        actual_palettes=195 + hold_idx * 48 if leg.status != "planned" else None,
                        notes=f"Shift {hold_name} — manutention {hold_name.lower()}",
                        cost_forecast=3500 + hold_idx * 500,
                        cost_actual=3650 + hold_idx * 480 if leg.status != "planned" else None,
                    )
                    db.add(ds)
                    ds_count += 1

            await db.flush()
            print(f"  Created {op_count} escale operations + {ds_count} docker shifts")
        else:
            print(f"  Operations already exist ({existing_ops}), skipping")

        # ═══════════════════════════════════════════════════════
        # 12. SOF EVENTS
        # ═══════════════════════════════════════════════════════
        print("\n── 12. SOF Events ──")
        existing_sof = (await db.execute(select(func.count(SofEvent.id)))).scalar()
        if existing_sof == 0:
            sof_count = 0
            for leg in legs:
                base_date = leg.eta or leg.etd or dt(2026, 3, 15)
                if isinstance(base_date, date) and not isinstance(base_date, datetime):
                    base_date = datetime.combine(base_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                event_date = base_date.date()

                # Full SOF sequence for a port call
                sof_sequence = [
                    ("EOSP", "End of Sea Passage", "06:00", "Position: 49°46'N 000°22'W — fin de passage en mer"),
                    ("PILOT_ONBOARD", "Pilot onboard", "06:30", "Pilote embarqué — chenal d'accès"),
                    ("TUG_FAST", "Tug made fast / escorting", "06:45", "Remorqueur Abeille amarré tribord avant"),
                    ("FIRST_LINE", "First line ashore", "07:15", "Première amarre à quai"),
                    ("ALL_FAST", "All fast", "07:30", "Navire amarré — toutes amarres tournées"),
                    ("TUG_CAST_OFF", "Tug cast off", "07:35", None),
                    ("PILOT_OFF", "Pilot off", "07:40", None),
                    ("FREE_PRATIQUE", "Free pratique granted", "08:00", "Libre pratique accordée par les autorités portuaires"),
                    ("GANGWAY_RIGGED", "Ship's gangway rigged", "08:15", "Coupée installée — accès à quai ouvert"),
                    ("NOR_RETENDERED", "NOR RE-Tendered — Without prejudice", "08:30", "Notice of Readiness retournée"),
                    ("HOLDS_INSPECTION", "Cargo holds inspection commenced", "09:00", "Inspection cales par l'expert maritime — RAS"),
                    ("HATCH_OPEN_CLOSE", "FWD cargo hold hatch open", "09:30", "Ouverture panneau cale avant"),
                    ("COMMENCE_LOADING", "Commence loading", "10:00", "Début chargement — cale avant"),
                    ("LOADING_SUSPENDED", "Loading suspended — lunch break", "12:00", "Pause déjeuner dockers"),
                    ("LOADING_RESUMED", "Loading resumed", "13:00", "Reprise chargement"),
                    ("HATCH_OPEN_CLOSE", "AFT cargo hold hatch open", "13:30", "Ouverture panneau cale arrière"),
                    ("COMPLETED_LOADING", "Completed loading", "18:00", "Fin chargement — 450 palettes embarquées"),
                    ("PAX_EMBARK", "Passengers embarked", "18:30", "4 passagers embarqués — cabines 1 à 4"),
                    ("PAX_SAFETY_DRILL", "Passenger safety drill", "19:00", "Exercice sécurité passagers — brassières, rassemblement"),
                    ("COMMENCE_UNMOORING", "Commence unmooring", "20:00", "Début désamarrage"),
                    ("ALL_CLEAR", "All clear", "20:15", "Toutes amarres larguées"),
                    ("SOSP", "Start of Sea Passage", "20:30", "Début de passage en mer — route vers destination"),
                ]

                for event_type, label, time_str, remarks in sof_sequence:
                    sof = SofEvent(
                        leg_id=leg.id,
                        event_type=event_type,
                        event_label=label,
                        event_date=event_date,
                        event_time=time_str,
                        remarks=remarks,
                        created_by="Cpt. Morin",
                    )
                    db.add(sof)
                    sof_count += 1

                # Advance date for second day events
                event_date_2 = event_date + timedelta(days=1)
                day2_events = [
                    ("HOLDS_INSPECTION", "Cargo holds inspection completed", "08:00", "Inspection finale cales — certificat émis"),
                    ("HATCH_OPEN_CLOSE", "All cargo hold hatches closed and sealed", "08:30", "Tous panneaux fermés et scellés"),
                ]
                for event_type, label, time_str, remarks in day2_events:
                    db.add(SofEvent(
                        leg_id=leg.id, event_type=event_type, event_label=label,
                        event_date=event_date_2, event_time=time_str,
                        remarks=remarks, created_by="Cpt. Morin",
                    ))
                    sof_count += 1

            await db.flush()
            print(f"  Created {sof_count} SOF events")
        else:
            print(f"  SOF events already exist ({existing_sof}), skipping")

        # ═══════════════════════════════════════════════════════
        # 13. CLAIMS
        # ═══════════════════════════════════════════════════════
        print("\n── 13. Claims ──")
        existing_claims = (await db.execute(select(func.count(Claim.id)))).scalar()
        if existing_claims == 0:
            claims_data = [
                {
                    "claim_type": "cargo",
                    "context": "unloading",
                    "description": "3 palettes de café bio endommagées lors du déchargement — mouillure par eau de pluie. Bâche mal positionnée pendant opération de manutention.",
                    "guarantee_type": "pi",
                    "responsibility": "third_party",
                    "provision_amount": 4500,
                    "franchise_amount": 1500,
                    "status": "declared",
                    "incident_location": "Quai de la Vicomté, Fécamp",
                },
                {
                    "claim_type": "cargo",
                    "context": "loading",
                    "description": "Palette USPAL de rhum — fissure sur 2 caisses, fuite constatée au chargement. Palette présentait un défaut avant embarquement.",
                    "guarantee_type": "pi",
                    "responsibility": "pending",
                    "provision_amount": 8200,
                    "franchise_amount": 1500,
                    "status": "instruction",
                    "incident_location": "Terminal fret, São Sebastião",
                },
                {
                    "claim_type": "hull",
                    "context": "navigation",
                    "description": "Choc avec objet flottant non identifié (OFNI) — déformation légère tôle bâbord sous ligne de flottaison. Aucune voie d'eau.",
                    "guarantee_type": "hull_div",
                    "responsibility": "company",
                    "provision_amount": 25000,
                    "franchise_amount": 5000,
                    "indemnity_amount": 18000,
                    "company_charge": 7000,
                    "status": "accepted",
                    "incident_location": "Atlantique Nord — 42°15'N 030°45'W",
                },
                {
                    "claim_type": "crew",
                    "context": "quay",
                    "description": "Marin Lucas Kervella — entorse cheville lors de manœuvre d'amarrage. Arrêt de travail 10 jours.",
                    "guarantee_type": "pi",
                    "responsibility": "company",
                    "provision_amount": 3500,
                    "franchise_amount": 500,
                    "status": "open",
                    "incident_location": "Quai n°3, Le Havre",
                },
            ]

            claim_idx = 1
            for i, cd in enumerate(claims_data):
                leg = legs[i % len(legs)]
                vessel = vessel_by_id.get(leg.vessel_id, vessels[0])
                incident_dt = (leg.eta or leg.etd or dt(2026, 3, 10)) - timedelta(days=2)

                claim = Claim(
                    reference=gen_ref("CLM", claim_idx),
                    claim_type=cd["claim_type"],
                    status=cd["status"],
                    vessel_id=vessel.id,
                    leg_id=leg.id,
                    context=cd["context"],
                    incident_date=incident_dt,
                    incident_location=cd["incident_location"],
                    description=cd["description"],
                    guarantee_type=cd["guarantee_type"],
                    responsibility=cd["responsibility"],
                    provision_amount=cd["provision_amount"],
                    franchise_amount=cd["franchise_amount"],
                    indemnity_amount=cd.get("indemnity_amount"),
                    company_charge=cd.get("company_charge"),
                    declared_by="admin",
                    notes=f"Claim {claim_idx} — leg {leg.leg_code}",
                )
                db.add(claim)
                await db.flush()

                # Add timeline entries
                timeline_entries = [
                    ("status_change", "Ouverture du sinistre", None, "open", "admin"),
                ]
                if cd["status"] in ("declared", "instruction", "accepted"):
                    timeline_entries.append(
                        ("declaration", "Déclaration envoyée à l'assureur", f"Provision: {cd['provision_amount']}€ — Franchise: {cd['franchise_amount']}€", "declared", "admin")
                    )
                if cd["status"] in ("instruction", "accepted"):
                    timeline_entries.append(
                        ("expertise", "Expert maritime mandaté", "Rendez-vous prévu pour expertise contradictoire", None, "admin")
                    )
                if cd["status"] == "accepted":
                    timeline_entries.append(
                        ("financial_update", "Indemnité confirmée par assureur", f"Indemnité: {cd.get('indemnity_amount', 0)}€ — Charge compagnie: {cd.get('company_charge', 0)}€", "accepted", "admin")
                    )

                for action_type, title, desc, new_val, actor in timeline_entries:
                    tl = ClaimTimeline(
                        claim_id=claim.id,
                        action_type=action_type,
                        title=title,
                        description=desc,
                        new_value=new_val,
                        actor=actor,
                        action_date=incident_dt + timedelta(days=timeline_entries.index((action_type, title, desc, new_val, actor))),
                    )
                    db.add(tl)

                claim_idx += 1

            await db.flush()
            print(f"  Created {claim_idx - 1} claims with timeline")
        else:
            print(f"  Claims already exist ({existing_claims}), skipping")

        # ═══════════════════════════════════════════════════════
        # 14. LEG FINANCES
        # ═══════════════════════════════════════════════════════
        print("\n── 14. Leg Finances ──")
        existing_fin = (await db.execute(select(func.count(LegFinance.id)))).scalar()
        if existing_fin == 0:
            fin_count = 0
            for i, leg in enumerate(legs):
                # Calculate realistic finance data
                # Revenue from orders on this leg
                leg_orders = [o for o in orders if o.leg_id == leg.id]
                revenue = sum(o.total_price or 0 for o in leg_orders)
                if revenue == 0:
                    revenue = 85000 + i * 15000  # Fallback

                # Add passenger revenue
                pax_revenue = 4200 * 4  # Approx 4 pax per leg
                revenue += pax_revenue

                # Costs
                nav_days = (leg.estimated_duration_hours or 180) / 24
                sea_cost = round(11600 * nav_days, 2)
                port_cost = port_configs_data.get(leg.arrival_port_locode, {}).get("port_cost_total", 10000)
                quay_cost = port_configs_data.get(leg.arrival_port_locode, {}).get("daily_quay_cost", 1500) * (leg.port_stay_days or 3)
                ops_cost = sum(o.quantity_palettes * 18 for o in leg_orders if o.quantity_palettes) or 8000

                lf = LegFinance(
                    leg_id=leg.id,
                    revenue_forecast=round(revenue, 2),
                    revenue_actual=round(revenue * 0.95, 2) if leg.status != "planned" else 0,
                    sea_cost_forecast=round(sea_cost, 2),
                    sea_cost_actual=round(sea_cost * 1.05, 2) if leg.status != "planned" else 0,
                    port_cost_forecast=port_cost,
                    port_cost_actual=round(port_cost * 0.98, 2) if leg.status != "planned" else 0,
                    quay_cost_forecast=quay_cost,
                    quay_cost_actual=round(quay_cost * 1.02, 2) if leg.status != "planned" else 0,
                    ops_cost_forecast=ops_cost,
                    ops_cost_actual=round(ops_cost * 1.08, 2) if leg.status != "planned" else 0,
                    notes=f"Finance leg {leg.leg_code}",
                )
                lf.compute()
                db.add(lf)
                fin_count += 1

            await db.flush()
            print(f"  Created {fin_count} leg finance records")
        else:
            print(f"  Leg finances already exist ({existing_fin}), skipping")

        # ═══════════════════════════════════════════════════════
        # COMMIT
        # ═══════════════════════════════════════════════════════
        await db.commit()
        print("\n✅ All demo data created successfully!")
        print("   Restart the app: docker restart towt-app-v2")


if __name__ == "__main__":
    asyncio.run(main())
