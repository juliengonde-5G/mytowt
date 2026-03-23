"""
Portal messaging model — threaded conversations between client/passenger and company.
Used by both passenger external portal and cargo client portal.
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean, func
)
from sqlalchemy.orm import relationship
from app.database import Base


class PortalMessage(Base):
    """A single message in a portal conversation thread."""
    __tablename__ = "portal_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Polymorphic: either booking_id (passenger) or packing_list_id (cargo)
    booking_id = Column(Integer, ForeignKey("passenger_bookings.id", ondelete="CASCADE"), nullable=True)
    packing_list_id = Column(Integer, ForeignKey("packing_lists.id", ondelete="CASCADE"), nullable=True)

    sender_type = Column(String(20), nullable=False)  # "client" or "company"
    sender_name = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    booking = relationship("PassengerBooking", backref="messages", foreign_keys=[booking_id])
    packing_list = relationship("PackingList", backref="messages", foreign_keys=[packing_list_id])
