from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Date, func
)
from sqlalchemy.orm import relationship
from app.database import Base


class CrewMember(Base):
    __tablename__ = "crew_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    role = Column(String(50), nullable=False)  # capitaine, second, chef_mecanicien, cook, lieutenant, bosco, marin, eleve_officier
    phone = Column(String(50), nullable=True)
    email = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True)
    is_foreign = Column(Boolean, default=False)  # Personnel étranger
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    assignments = relationship("CrewAssignment", back_populates="member", cascade="all, delete-orphan")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def role_label(self):
        labels = {
            "capitaine": "Capitaine",
            "second": "Second",
            "chef_mecanicien": "Chef mécanicien",
            "cook": "Cook",
            "lieutenant": "Lieutenant",
            "bosco": "Bosco",
            "marin": "Marin",
            "eleve_officier": "Élève Officier",
        }
        return labels.get(self.role, self.role)

    def __repr__(self):
        return f"<CrewMember {self.full_name} ({self.role})>"


class CrewAssignment(Base):
    """Période d'embarquement d'un membre d'équipage sur un navire."""
    __tablename__ = "crew_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    member_id = Column(Integer, ForeignKey("crew_members.id"), nullable=False)
    vessel_id = Column(Integer, ForeignKey("vessels.id"), nullable=False)
    embark_date = Column(Date, nullable=False)
    disembark_date = Column(Date, nullable=True)  # None = still on board
    embark_leg_id = Column(Integer, ForeignKey("legs.id"), nullable=True)  # Leg of embarkation
    disembark_leg_id = Column(Integer, ForeignKey("legs.id"), nullable=True)  # Leg of disembarkation
    status = Column(String(20), default="active")  # active, completed, planned
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    member = relationship("CrewMember", back_populates="assignments")
    vessel = relationship("Vessel")
    embark_leg = relationship("Leg", foreign_keys=[embark_leg_id])
    disembark_leg = relationship("Leg", foreign_keys=[disembark_leg_id])


CREW_ROLES = [
    {"value": "capitaine", "label": "Capitaine"},
    {"value": "second", "label": "Second"},
    {"value": "chef_mecanicien", "label": "Chef mécanicien"},
    {"value": "cook", "label": "Cook"},
    {"value": "lieutenant", "label": "Lieutenant"},
    {"value": "bosco", "label": "Bosco"},
    {"value": "marin", "label": "Marin"},
    {"value": "eleve_officier", "label": "Élève Officier"},
]

REQUIRED_ROLES = ["capitaine", "second", "chef_mecanicien", "cook", "lieutenant", "bosco"]
