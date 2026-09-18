from sqlalchemy import Column, ForeignKey, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, TEXT, TIMESTAMP, BOOLEAN
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func, text
from pgvector.sqlalchemy import Vector
import uuid

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    email = Column(TEXT, unique=True, nullable=False)
    password_hash = Column(TEXT, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

class Memory(Base):
    __tablename__ = "memories"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    text_content = Column("text", TEXT, nullable=False)
    embedding = Column(Vector(384), nullable=False)
    superseded = Column(BOOLEAN, nullable=False, server_default=text("false"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index('memories_user_id_idx', 'user_id'),
        Index('memories_embedding_idx', 'embedding', postgresql_using='ivfflat', postgresql_with={'lists': 100}, postgresql_ops={'embedding': 'vector_cosine_ops'}),
    )

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    ended_at = Column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        Index('chat_sessions_user_id_idx', 'user_id'),
    )

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(TEXT, nullable=False)
    content = Column(TEXT, nullable=False)
    was_interrupted = Column(BOOLEAN, nullable=False, server_default=text("false"))
    intent = Column(TEXT, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="chat_messages_role_check"),
        Index('chat_messages_session_id_idx', 'session_id'),
    )

