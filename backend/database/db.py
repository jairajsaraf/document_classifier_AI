"""
Database setup and session management
"""
import uuid

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from typing import Generator
from backend.config import settings
from backend.models.document import Base

# Create engine
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _add_public_id(eng):
    """`create_all` leaves an existing table alone, so a database made before Phase 5 has no
    documents.public_id. Add it, give every row an unguessable id, and index it."""
    if "public_id" in {c["name"] for c in inspect(eng).get_columns("documents")}:
        return
    with eng.begin() as conn:
        conn.execute(text("ALTER TABLE documents ADD COLUMN public_id VARCHAR(32)"))
        for (doc_id,) in conn.execute(text("SELECT id FROM documents")).fetchall():
            conn.execute(text("UPDATE documents SET public_id = :p WHERE id = :i"), {"p": uuid.uuid4().hex, "i": doc_id})
        conn.execute(text("CREATE UNIQUE INDEX ix_documents_public_id ON documents (public_id)"))


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    _add_public_id(engine)


def get_db() -> Generator[Session, None, None]:
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
