from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Date, func
)
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class OrderStatus(str, enum.Enum):
    UNASSIGNED = "non_affecte"
    RESERVED = "reserve"
    CONFIRMED = "confirme"
    CANCELLED = "annule"


PALETTE_FORMATS = [
    {"value": "EPAL", "label": "EPAL (Europe)", "coeff": 1.0},
    {"value": "USPAL", "label": "USPAL (US)", "coeff": 1.2},
    {"value": "PORTPAL", "label": "PORTPAL (Port)", "coeff": 1.2},
]

PALETTE_COEFF = {"EPAL": 1.0, "USPAL": 1.2, "PORTPAL": 1.2}


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reference = Column(String(50), unique=True, nullable=False, index=True)

    client_name = Column(String(200), nullable=False)
    client_contact = Column(String(200), nullable=True)

    # Cargo
    quantity_palettes = Column(Integer, nullable=False)
    palette_format = Column(String(20), default="EPAL")  # EPAL, USPAL, PORTPAL
    weight_per_palette = Column(Float, default=0.8)
    unit_price = Column(Float, nullable=False)
    thc_included = Column(Boolean, default=False)
    description = Column(Text, nullable=True)

    # Fees
    booking_fee = Column(Float, default=0)       # Frais de booking
    documentation_fee = Column(Float, default=0)  # Frais de documentation

    # Delivery period requested by client
    delivery_date_start = Column(Date, nullable=True)
    delivery_date_end = Column(Date, nullable=True)

    # Port preferences
    departure_locode = Column(String(5), nullable=True)
    arrival_locode = Column(String(5), nullable=True)

    # Status
    status = Column(String(20), default=OrderStatus.UNASSIGNED.value)

    # Computed
    total_price = Column(Float, nullable=True)
    total_weight = Column(Float, nullable=True)

    # Attachment
    attachment_filename = Column(String(255), nullable=True)
    attachment_path = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Single assignment
    leg_id = Column(Integer, ForeignKey("legs.id"), nullable=True)
    leg = relationship("Leg", foreign_keys=[leg_id])

    # Rate grid linkage
    rate_grid_id = Column(Integer, ForeignKey("rate_grids.id"), nullable=True)
    rate_grid_line_id = Column(Integer, ForeignKey("rate_grid_lines.id"), nullable=True)
    rate_grid = relationship("RateGrid", foreign_keys=[rate_grid_id])
    rate_grid_line = relationship("RateGridLine", foreign_keys=[rate_grid_line_id])

    assignments = relationship("OrderAssignment", back_populates="order", cascade="all, delete-orphan")

    @property
    def palette_coeff(self):
        return PALETTE_COEFF.get(self.palette_format, 1.0)

    @property
    def equivalent_epal(self):
        """Number of equivalent EPAL slots used."""
        return round(self.quantity_palettes * self.palette_coeff, 1)

    def compute_total(self):
        self.total_price = (self.quantity_palettes * self.unit_price) + (self.booking_fee or 0) + (self.documentation_fee or 0)
        self.total_weight = self.quantity_palettes * (self.weight_per_palette or 0.8)

    def __repr__(self):
        return f"<Order {self.reference} - {self.client_name}>"


class OrderAssignment(Base):
    __tablename__ = "order_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    leg_id = Column(Integer, ForeignKey("legs.id"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    confirmed = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)

    order = relationship("Order", back_populates="assignments")
    leg = relationship("Leg", back_populates="order_assignments")
