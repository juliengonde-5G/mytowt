"""
Portal access audit log — tracks every access to external portals.
RGPD compliance: who accessed what data and when.
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, func
from app.database import Base


class PortalAccessLog(Base):
    __tablename__ = "portal_access_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portal_type = Column(String(20), nullable=False)  # "cargo", "passenger", "planning"
    token = Column(String(50), nullable=False, index=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    path = Column(String(300), nullable=False)
    booking_id = Column(Integer, nullable=True)
    packing_list_id = Column(Integer, nullable=True)
    accessed_at = Column(DateTime(timezone=True), server_default=func.now())
