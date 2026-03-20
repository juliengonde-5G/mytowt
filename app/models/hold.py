"""Models for Hold (cale) management: capacities, assignments, confirmation."""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, func
)
from sqlalchemy.orm import relationship, backref
from app.database import Base


# ─── HOLD DEFINITIONS ────────────────────────────────────────
# 6 holds: 3 levels (sup/int/inf) × 2 positions (AV=avant/AR=arrière)
HOLD_CODES = [
    ("SUP_AV", "Supérieur Avant"),
    ("SUP_AR", "Supérieur Arrière"),
    ("INT_AV", "Intermédiaire Avant"),
    ("INT_AR", "Intermédiaire Arrière"),
    ("INF_AV", "Inférieur Avant"),
    ("INF_AR", "Inférieur Arrière"),
]

# Short labels for visual display
HOLD_SHORT_LABELS = {
    "SUP_AV": "Sup. AV",
    "SUP_AR": "Sup. AR",
    "INT_AV": "Int. AV",
    "INT_AR": "Int. AR",
    "INF_AV": "Inf. AV",
    "INF_AR": "Inf. AR",
}

# ─── HOLD CAPACITIES ─────────────────────────────────────────
# Capacities per hold, per pallet type, stackable vs non-stackable
# Format: HOLD_CAPACITIES[hold_code][pallet_type] = {"normal": X, "stacked": Y}
# Pallet types: PORTPAL (180×140), EPAL (80×100), USPAL (100×120), BB (100×110)
HOLD_CAPACITIES = {
    "SUP_AV": {
        "PORTPAL": {"normal": 53, "stacked": 104},
        "EPAL":    {"normal": 180, "stacked": 294},
        "USPAL":   {"normal": 109, "stacked": 209},
        "BB":      {"normal": 134, "stacked": 0},
    },
    "SUP_AR": {
        "PORTPAL": {"normal": 56, "stacked": 107},
        "EPAL":    {"normal": 177, "stacked": 318},
        "USPAL":   {"normal": 111, "stacked": 207},
        "BB":      {"normal": 135, "stacked": 0},
    },
    "INT_AV": {
        "PORTPAL": {"normal": 52, "stacked": 105},
        "EPAL":    {"normal": 166, "stacked": 318},
        "USPAL":   {"normal": 111, "stacked": 176},
        "BB":      {"normal": 129, "stacked": 0},
    },
    "INT_AR": {
        "PORTPAL": {"normal": 51, "stacked": 91},
        "EPAL":    {"normal": 166, "stacked": 297},
        "USPAL":   {"normal": 110, "stacked": 218},
        "BB":      {"normal": 134, "stacked": 0},
    },
    "INF_AV": {
        "PORTPAL": {"normal": 47, "stacked": 88},
        "EPAL":    {"normal": 159, "stacked": 299},
        "USPAL":   {"normal": 105, "stacked": 192},
        "BB":      {"normal": 123, "stacked": 0},
    },
    "INF_AR": {
        "PORTPAL": {"normal": 34, "stacked": 68},
        "EPAL":    {"normal": 124, "stacked": 196},
        "USPAL":   {"normal": 80, "stacked": 160},
        "BB":      {"normal": 98, "stacked": 0},
    },
}


def get_hold_capacity(hold_code: str, pallet_type: str, stackable: bool = False) -> int:
    """Get capacity for a hold given pallet type and stackability."""
    hold = HOLD_CAPACITIES.get(hold_code, {})
    ptype = hold.get(pallet_type, {"normal": 0, "stacked": 0})
    return ptype["stacked"] if stackable else ptype["normal"]


def get_total_capacity(pallet_type: str, stackable: bool = False) -> int:
    """Get total ship capacity for a pallet type."""
    return sum(get_hold_capacity(h, pallet_type, stackable) for h, _ in HOLD_CODES)


class HoldAssignment(Base):
    """Assignment of a packing list batch to a specific hold."""
    __tablename__ = "hold_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    leg_id = Column(Integer, ForeignKey("legs.id", ondelete="CASCADE"), nullable=False)
    batch_id = Column(Integer, ForeignKey("packing_list_batches.id", ondelete="CASCADE"), nullable=False)
    hold_code = Column(String(10), nullable=False)  # SUP_AV, SUP_AR, INT_AV, INT_AR, INF_AV, INF_AR
    pallet_quantity = Column(Integer, nullable=False, default=0)
    pallet_type = Column(String(20), nullable=True)  # EPAL, USPAL, PORTPAL, BB
    is_stackable = Column(Boolean, default=False)
    assigned_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    leg = relationship("Leg", backref=backref("hold_assignments", passive_deletes=True))
    batch = relationship("PackingListBatch", backref=backref("hold_assignments", passive_deletes=True))


class HoldPlanConfirmation(Base):
    """Confirmation of a hold plan for a leg — locks the assignments and allows report generation."""
    __tablename__ = "hold_plan_confirmations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    leg_id = Column(Integer, ForeignKey("legs.id", ondelete="CASCADE"), nullable=False, unique=True)
    confirmed_by = Column(String(200), nullable=False)
    confirmed_at = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(Text, nullable=True)

    leg = relationship("Leg", backref=backref("hold_plan_confirmation", uselist=False, passive_deletes=True))
