"""SharedLink model — tracks generated public share links for commercial support."""
import secrets
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, func, Index
from app.database import Base


def generate_share_token():
    return secrets.token_urlsafe(24)


class SharedLink(Base):
    __tablename__ = "shared_links"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Token (public identifier in the URL)
    token = Column(String(64), unique=True, nullable=False, default=generate_share_token, index=True)

    # Who created it
    created_by_id = Column(Integer, nullable=False)
    created_by_name = Column(String(100), nullable=False)

    # Filter parameters (stored as human-readable description)
    label = Column(String(300), nullable=True)  # e.g. "Anemos · vers New York · 2026"
    year = Column(Integer, nullable=False)
    vessel_code = Column(String(10), nullable=True)
    origin_locode = Column(String(10), nullable=True)
    destination_locode = Column(String(10), nullable=True)
    legs_ids = Column(Text, nullable=True)  # comma-separated IDs
    lang = Column(String(5), nullable=False, default="fr")

    # Stats
    view_count = Column(Integer, nullable=False, default=0)
    last_viewed_at = Column(DateTime(timezone=True), nullable=True)

    # Status
    is_active = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_shared_link_created_by", "created_by_id"),
        Index("idx_shared_link_active", "is_active"),
    )

    def __repr__(self):
        return f"<SharedLink {self.token[:8]}… by {self.created_by_name}>"
