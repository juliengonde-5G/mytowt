from sqlalchemy import Column, Integer, String, DateTime, Text, func
from app.database import Base
import uuid


class PlanningShare(Base):
    """Shareable planning link — stores filter config so external users
    always see the latest planning data matching these filters."""
    __tablename__ = "planning_shares"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(32), unique=True, nullable=False, index=True,
                   default=lambda: uuid.uuid4().hex[:24])

    # Filters snapshot
    year = Column(Integer, nullable=False)
    vessel_code = Column(Integer, nullable=True)
    origin_locode = Column(String(5), nullable=True)
    destination_locode = Column(String(5), nullable=True)
    legs_ids = Column(Text, nullable=True)  # comma-separated leg ids (optional)
    lang = Column(String(5), default="fr")
    label = Column(String(200), nullable=True)  # optional label for identification

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, nullable=True)  # user id who created the share

    def __repr__(self):
        return f"<PlanningShare {self.token}>"
