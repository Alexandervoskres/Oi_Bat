from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _apply_migrations() -> None:
    """Add columns that may not exist in databases created before schema updates."""
    from sqlalchemy import text

    new_columns = [
        ("products", "do_not_order", "BOOLEAN NOT NULL DEFAULT 0"),
        ("products", "is_seasonal", "BOOLEAN NOT NULL DEFAULT 0"),
        ("products", "is_on_demand", "BOOLEAN NOT NULL DEFAULT 0"),
    ]
    with engine.connect() as conn:
        for table, col, definition in new_columns:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {definition}"))
                conn.commit()
            except Exception:
                pass  # column already exists


def init_db() -> None:
    from . import models  # noqa: F401
    from .services.initial_data import ensure_default_admin

    Base.metadata.create_all(bind=engine)
    _apply_migrations()

    db = SessionLocal()
    try:
        ensure_default_admin(db)
    finally:
        db.close()
