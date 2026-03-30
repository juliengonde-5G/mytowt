"""
Ticketing module models.

Ticket = demande d'un membre d'equipage liee a une escale (ou en preparation d'escale).
Categories: approvisionnement, maintenance, administratif, logistique, medical, autre.
"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, func
)
from sqlalchemy.orm import relationship
from app.database import Base


# ─── CONSTANTS ────────────────────────────────────────────────

TICKET_CATEGORIES = [
    ("approvisionnement", "Approvisionnement"),
    ("maintenance", "Maintenance / Réparation"),
    ("administratif", "Administratif"),
    ("logistique", "Logistique"),
    ("medical", "Médical"),
    ("autre", "Autre"),
]

TICKET_PRIORITIES = [
    ("low", "Basse"),
    ("normal", "Normale"),
    ("high", "Haute"),
    ("urgent", "Urgente"),
]

TICKET_STATUSES = [
    ("open", "Ouvert"),
    ("in_progress", "En cours"),
    ("waiting", "En attente"),
    ("resolved", "Résolu"),
    ("closed", "Clôturé"),
]


# ─── MODELS ───────────────────────────────────────────────────

class Ticket(Base):
    """Demande equipage liee a une escale."""
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reference = Column(String(30), unique=True, nullable=False, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=False)

    category = Column(String(30), nullable=False)  # approvisionnement, maintenance, etc.
    priority = Column(String(20), nullable=False, default="normal")
    status = Column(String(20), nullable=False, default="open")

    # Links
    vessel_id = Column(Integer, ForeignKey("vessels.id"), nullable=False)
    leg_id = Column(Integer, ForeignKey("legs.id"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Resolution
    resolution_notes = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    # Meta
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    vessel = relationship("Vessel")
    leg = relationship("Leg")
    created_by = relationship("User", foreign_keys=[created_by_id])
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])
    comments = relationship("TicketComment", back_populates="ticket",
                            cascade="all, delete-orphan",
                            order_by="TicketComment.created_at.asc()")

    @property
    def category_label(self):
        return dict(TICKET_CATEGORIES).get(self.category, self.category)

    @property
    def priority_label(self):
        return dict(TICKET_PRIORITIES).get(self.priority, self.priority)

    @property
    def status_label(self):
        return dict(TICKET_STATUSES).get(self.status, self.status)

    @property
    def is_open(self):
        return self.status in ("open", "in_progress", "waiting")

    def __repr__(self):
        return f"<Ticket {self.reference} ({self.category}/{self.status})>"


class TicketComment(Base):
    """Commentaire sur un ticket."""
    __tablename__ = "ticket_comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    is_internal = Column(Boolean, default=False)  # Note interne (non visible equipage)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ticket = relationship("Ticket", back_populates="comments")
    author = relationship("User")

    def __repr__(self):
        return f"<TicketComment ticket={self.ticket_id} by={self.author_id}>"
