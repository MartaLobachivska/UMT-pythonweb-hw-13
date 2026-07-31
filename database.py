from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings


engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Common declarative base class for all ORM models."""


def get_db():
    """FastAPI dependency that yields a request-scoped DB session.

    The session is always closed after the request, even if a handler
    raises, since ``close()`` runs in the ``finally`` block.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()