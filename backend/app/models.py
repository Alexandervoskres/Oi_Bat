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
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    min_stock: Mapped[int] = mapped_column(Integer, default=5)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7)
    notes: Mapped[str] = mapped_column(Text, default="")
    do_not_order: Mapped[bool] = mapped_column(Boolean, default=False)
    is_seasonal: Mapped[bool] = mapped_column(Boolean, default=False)
    is_on_demand: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_status_override: Mapped[str | None] = mapped_column(String(40), nullable=True)
    risk_priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_note: Mapped[str] = mapped_column(Text, default="")
    excluded_from_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    risk_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    import_batch: Mapped[ImportBatch | None] = relationship(back_populates="products")


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    contact_person: Mapped[str] = mapped_column(String(160), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    reliability: Mapped[int] = mapped_column(Integer, default=3)  # 1..5 rating
    min_order_amount: Mapped[float] = mapped_column(Float, default=0)
    payment_terms: Mapped[str] = mapped_column(String(200), default="")
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class MovementType(str, enum.Enum):
    receipt = "receipt"        # приход
    write_off = "write_off"    # списание
    sale = "sale"              # продажа
    adjustment = "adjustment"  # корректировка
    return_ = "return"         # возврат
    reserve = "reserve"        # резерв


# Sign applied to the request quantity for each movement type. `adjustment`
# carries its own sign (the correction may be negative).
MOVEMENT_SIGN = {
    MovementType.receipt: 1,
    MovementType.return_: 1,
    MovementType.sale: -1,
    MovementType.write_off: -1,
    MovementType.reserve: -1,
    MovementType.adjustment: 1,
}


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    movement_type: Mapped[str] = mapped_column(String(20), index=True)
    quantity: Mapped[int] = mapped_column(Integer)  # signed delta actually applied
    stock_before: Mapped[int] = mapped_column(Integer)
    stock_after: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    product: Mapped["Product"] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(80), default="", index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), default="", index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    type: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="notice")
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text, default="")
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


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
