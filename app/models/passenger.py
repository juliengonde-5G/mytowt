"""
Passenger module models — V2.

Booking = 1 cabin on 1 leg (both mandatory at creation).
Price auto-computed from CabinPriceGrid (route × cabin type).
A booking holds 1 or 2 passengers (up to cabin capacity).
Documents are per-passenger.
"""
import secrets
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Date, Numeric, func
)
from sqlalchemy.orm import relationship
from app.database import Base


def _gen_token():
    return secrets.token_urlsafe(24)


# ─── CABIN CONFIG (same for all vessels) ─────────────────────
CABIN_CONFIG = [
    {"number": 1, "name": "Cabine 1", "bed_type": "double", "capacity": 2},
    {"number": 2, "name": "Cabine 2", "bed_type": "double", "capacity": 2},
    {"number": 3, "name": "Cabine 3", "bed_type": "twin", "capacity": 2},
    {"number": 4, "name": "Cabine 4", "bed_type": "twin", "capacity": 2},
]
# Total: 8 passengers per voyage

CABIN_TYPE_LABELS = {
    "double": "Lit double",
    "twin": "Lits jumeaux",
}

BOOKING_STATUSES = [
    ("draft", "Brouillon"),
    ("confirmed", "Confirmée"),
    ("paid", "Payée"),
    ("embarked", "Embarqué"),
    ("completed", "Terminée"),
    ("cancelled", "Annulée"),
]

PAYMENT_METHODS = [
    ("virement", "Virement bancaire"),
    ("revolut", "Carte bancaire (Revolut)"),
]

PAYMENT_TYPES = [
    ("acompte", "Acompte"),
    ("solde", "Solde"),
]

PAYMENT_STATUSES = [
    ("pending", "En attente"),
    ("sent", "Ordre envoyé"),
    ("received", "Reçu"),
    ("failed", "Échoué"),
    ("refunded", "Remboursé"),
]

DOCUMENT_TYPES = [
    ("passport", "Passeport / Pièce d'identité"),
    ("medical", "Certificat médical"),
    ("waiver", "Décharge / Conditions générales signées"),
    ("esta_visa", "ESTA / VISA"),
    ("emergency_contact", "Contact d'urgence"),
    ("photo_rights", "Renonciation aux droits d'auteur"),
]

DOCUMENT_STATUSES = [
    ("missing", "Manquant"),
    ("uploaded", "Téléversé"),
    ("validated", "Validé"),
    ("rejected", "Rejeté"),
]


class PassengerBooking(Base):
    """Booking = 1 cabin on 1 leg. Contains 1 or 2 passengers."""
    __tablename__ = "passenger_bookings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    leg_id = Column(Integer, ForeignKey("legs.id", ondelete="SET NULL"), nullable=False)
    vessel_id = Column(Integer, ForeignKey("vessels.id"), nullable=False)
    cabin_number = Column(Integer, nullable=False)  # 1-4

    reference = Column(String(20), unique=True, nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    booking_date = Column(Date, nullable=True)

    # Pricing (auto from grid)
    price_total = Column(Numeric(10, 2), nullable=True)
    price_deposit = Column(Numeric(10, 2), nullable=True)
    price_balance = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(3), default="EUR")

    # Booker contact
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)

    # External access
    token = Column(String(40), unique=True, nullable=False, default=_gen_token, index=True)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    leg = relationship("Leg", backref="passenger_bookings")
    vessel = relationship("Vessel")
    passengers = relationship("Passenger", back_populates="booking", cascade="all, delete-orphan")
    payments = relationship("PassengerPayment", back_populates="booking", cascade="all, delete-orphan")

    @property
    def cabin_type(self):
        return "double" if self.cabin_number <= 2 else "twin"

    @property
    def cabin_label(self):
        return CABIN_TYPE_LABELS.get(self.cabin_type, self.cabin_type)

    @property
    def pax_names(self):
        return ", ".join(p.full_name for p in self.passengers) if self.passengers else "—"

    def __repr__(self):
        return f"<Booking {self.reference} ({self.status})>"


class Passenger(Base):
    """A passenger within a booking (1 or 2 per booking)."""
    __tablename__ = "passengers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(Integer, ForeignKey("passenger_bookings.id", ondelete="CASCADE"), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    nationality = Column(String(100), nullable=True)
    passport_number = Column(String(50), nullable=True)
    emergency_contact_name = Column(String(200), nullable=True)
    emergency_contact_phone = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    booking = relationship("PassengerBooking", back_populates="passengers")
    documents = relationship("PassengerDocument", back_populates="passenger", cascade="all, delete-orphan")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class PassengerPayment(Base):
    __tablename__ = "passenger_payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(Integer, ForeignKey("passenger_bookings.id", ondelete="CASCADE"), nullable=False)
    payment_type = Column(String(20), nullable=False)
    payment_method = Column(String(20), nullable=True)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="EUR")
    status = Column(String(20), nullable=False, default="pending")
    revolut_order_id = Column(String(200), nullable=True)
    reference = Column(String(100), nullable=True)
    due_date = Column(Date, nullable=True)
    paid_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    booking = relationship("PassengerBooking", back_populates="payments")


class PassengerDocument(Base):
    __tablename__ = "passenger_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    passenger_id = Column(Integer, ForeignKey("passengers.id", ondelete="CASCADE"), nullable=False)
    doc_type = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="missing")
    filename = Column(String(300), nullable=True)
    file_path = Column(String(500), nullable=True)
    expiry_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    reviewed_by = Column(String(200), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    passenger = relationship("Passenger", back_populates="documents")


class CabinPriceGrid(Base):
    __tablename__ = "cabin_price_grid"

    id = Column(Integer, primary_key=True, autoincrement=True)
    origin_locode = Column(String(5), ForeignKey("ports.locode"), nullable=False)
    destination_locode = Column(String(5), ForeignKey("ports.locode"), nullable=False)
    cabin_type = Column(String(20), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="EUR")
    deposit_pct = Column(Integer, default=30)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    origin_port = relationship("Port", foreign_keys=[origin_locode])
    destination_port = relationship("Port", foreign_keys=[destination_locode])


class PreBoardingForm(Base):
    """Pre-boarding questionnaire filled by passenger."""
    __tablename__ = "preboarding_forms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    passenger_id = Column(Integer, ForeignKey("passengers.id", ondelete="CASCADE"), nullable=False, unique=True)
    # Maritime experience
    sailed_before = Column(String(20), nullable=True)  # yes/no
    seasick = Column(String(20), nullable=True)  # yes/no/sometimes
    willing_maneuvers = Column(String(20), nullable=True)  # yes/no
    # Health
    chronic_conditions = Column(Text, nullable=True)
    allergies = Column(Text, nullable=True)
    daily_medication = Column(Text, nullable=True)
    can_swim_50m = Column(String(20), nullable=True)  # yes/no
    # Diet
    dietary_requirements = Column(Text, nullable=True)
    intolerances = Column(Text, nullable=True)
    # Signature
    signed = Column(Boolean, default=False)
    signed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    passenger = relationship("Passenger")
