"""Models for On Board module: SOF events, notifications, cargo documents."""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Date, func
)
from sqlalchemy.orm import relationship
from app.database import Base


# ─── SOF EVENT TYPES ────────────────────────────────────────
SOF_EVENT_TYPES = [
    ("EOSP", "EOSP (End of Sea Passage)"),
    ("SOSP", "SOSP (Start of Sea Passage)"),
    ("FREE_PRATIQUE", "Free pratique granted"),
    ("NOR_RETENDERED", "Notice of Readiness RE-Tendered - Without prejudice"),
    ("PILOT_ONBOARD", "Pilot onboard"),
    ("PILOT_OFF", "Pilot off"),
    ("TUG_FAST", "Tug made fast / escorting"),
    ("TUG_CAST_OFF", "Tug cast off"),
    ("TUG_FREE", "Tug free"),
    ("FIRST_LINE", "First line ashore"),
    ("ALL_FAST", "All fast"),
    ("COMMENCE_UNMOORING", "Commence unmooring"),
    ("ALL_CLEAR", "All clear"),
    ("ANCHORED", "Anchored"),
    ("ANCHOR_AWEIGH", "Anchor aweigh"),
    ("GANGWAY_RIGGED", "Ship's / Shore gangway rigged"),
    ("HOLDS_INSPECTION", "Cargo holds inspection commenced / completed"),
    ("HATCH_OPEN_CLOSE", "FWD / Aft cargo hold hatch open / close"),
    ("COMMENCE_LOADING", "Commence loading / discharging"),
    ("COMPLETED_LOADING", "Completed loading / discharging"),
    ("LOADING_SUSPENDED", "Loading / Discharging suspended - Shore / Ship stop"),
    ("LOADING_RESUMED", "Loading / discharging resumed"),
    # ─── PASSENGER OPERATIONS ───
    ("PAX_EMBARK", "Passengers embarked / Embarquement passagers"),
    ("PAX_DISEMBARK", "Passengers disembarked / Débarquement passagers"),
    ("PAX_SAFETY_DRILL", "Passenger safety drill / Exercice sécurité passagers"),
    ("PAX_MUSTER", "Passenger muster / Appel passagers"),
]

# ─── CARGO DOCUMENT TYPES ───────────────────────────────────
CARGO_DOC_TYPES = [
    ("SOF", "Statement of Facts"),
    ("NOR", "Notice of Readiness"),
    ("NOR_RT", "Notice of Readiness Re-Tendered"),
    ("HOLDS_CERT", "Holds Readiness Certificate"),
    ("KEY_MEETING", "Key Transfer Meeting"),
    ("PRE_MEETING", "Pre-Loading / Discharging Meeting"),
    ("LOP_FP", "Letter of Protest - Free Pratique"),
    ("LOP_DELAYS", "Letter of Protest - Delays & Restrictions"),
    ("LOP_DOCUMENT", "Letter of Protest - Documentation"),
    ("LOP_QTY", "Letter of Protest - Quantity"),
    ("LOP_DEADFREIGHT", "Letter of Protest - Deadfreight"),
    ("LOP_OTHER", "Letter of Protest - Other"),
    ("MATES_RECEIPT", "Mate's Receipt"),
]


class SofEvent(Base):
    """Statement of Facts - individual event record."""
    __tablename__ = "sof_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    leg_id = Column(Integer, ForeignKey("legs.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(50), nullable=False)  # code from SOF_EVENT_TYPES
    event_label = Column(String(300), nullable=False)  # display text (can be customized)
    event_date = Column(Date, nullable=True)
    event_time = Column(String(10), nullable=True)  # HH:MM format (LT)
    remarks = Column(Text, nullable=True)
    created_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    leg = relationship("Leg", backref="sof_events")


class OnboardNotification(Base):
    """Notification for onboard crew about changes to escale, crew, or cargo."""
    __tablename__ = "onboard_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    leg_id = Column(Integer, ForeignKey("legs.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(30), nullable=False)  # crew, escale, cargo
    title = Column(String(300), nullable=False)
    detail = Column(Text, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    leg = relationship("Leg", backref="onboard_notifications")


class CargoDocument(Base):
    """Generated cargo document for a leg."""
    __tablename__ = "cargo_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    leg_id = Column(Integer, ForeignKey("legs.id", ondelete="CASCADE"), nullable=False)
    doc_type = Column(String(30), nullable=False)  # code from CARGO_DOC_TYPES
    title = Column(String(300), nullable=False)
    data_json = Column(Text, nullable=True)  # JSON blob with form data
    created_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    leg = relationship("Leg", backref="cargo_documents")
