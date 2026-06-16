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


def _alembic_config():
    from pathlib import Path

    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def run_migrations() -> None:
    """Bring the database schema up to the latest Alembic revision.

    This is the single source of truth for schema management. The baseline
    revision builds the full schema from the models, so a fresh database is
    created entirely through migrations.
    """
    from alembic import command

    command.upgrade(_alembic_config(), "head")


def init_db() -> None:
    from . import models  # noqa: F401
    from .services.initial_data import ensure_default_admin

    run_migrations()

    db = SessionLocal()
    try:
        ensure_default_admin(db)
    finally:
        db.close()
