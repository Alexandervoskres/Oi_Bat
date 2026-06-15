from __future__ import annotations

from datetime import date, datetime, timezone
import enum

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    buyer = "buyer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), default="")
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.manager)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    imports: Mapped[list["ImportBatch"]] = relationship(back_populates="created_by")


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    rows_count: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(80), default="excel")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    created_by: Mapped[User | None] = relationship(back_populates="imports")
    products: Mapped[list["Product"]] = relationship(back_populates="import_batch")
    snapshots: Mapped[list["ProductSnapshot"]] = relationship(back_populates="import_batch")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sku: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(120), default="Без категории")
    stock: Mapped[int] = mapped_column(Integer, default=0)
    sold_month: Mapped[int] = mapped_column(Integer, default=0)
    avg_monthly_sales: Mapped[float] = mapped_column(Float, default=0)
    purchase_price: Mapped[float] = mapped_column(Float, default=0)
    sale_price: Mapped[float] = mapped_column(Float, default=0)
    last_sale_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    supplier: Mapped[str] = mapped_column(String(160), default="")
    min_stock: Mapped[int] = mapped_column(Integer, default=5)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7)
    notes: Mapped[str] = mapped_column(Text, default="")
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    import_batch: Mapped[ImportBatch | None] = relationship(back_populates="products")


class ProductSnapshot(Base):
    __tablename__ = "product_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    sku: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(120), default="Без категории")
    stock: Mapped[int] = mapped_column(Integer, default=0)
    sold_month: Mapped[int] = mapped_column(Integer, default=0)
    avg_monthly_sales: Mapped[float] = mapped_column(Float, default=0)
    sale_price: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    import_batch: Mapped[ImportBatch] = relationship(back_populates="snapshots")
