"""
Chatbot module models.

ChatSession = conversation d'un utilisateur avec le chatbot compagnie.
ChatMessage = message individuel (user ou bot) dans une session.
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean, func
)
from sqlalchemy.orm import relationship
from app.database import Base


class ChatSession(Base):
    """Session de conversation chatbot."""
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(300), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User")
    messages = relationship("ChatMessage", back_populates="session",
                            cascade="all, delete-orphan",
                            order_by="ChatMessage.created_at.asc()")

    @property
    def last_message(self):
        return self.messages[-1] if self.messages else None

    @property
    def message_count(self):
        return len(self.messages)

    def __repr__(self):
        return f"<ChatSession {self.id} user={self.user_id}>"


class ChatMessage(Base):
    """Message dans une session chatbot."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage {self.id} role={self.role}>"
