"""Таблицы базы данных (модели SQLAlchemy).

ЭТО САМЫЙ ВАЖНЫЙ ФАЙЛ ДЛЯ ПОНИМАНИЯ ПРОЕКТА: тут описано, ЧТО хранится в базе.
Каждый класс = одна таблица. Каждое поле (mapped_column) = одна колонка.

ВАЖНО: если ты ДОБАВИЛ или ИЗМЕНИЛ поле здесь — база сама об этом не узнает.
Нужно создать миграцию (см. README → «Миграции базы данных»), иначе приложение
упадёт с ошибкой «нет такой колонки». Это самая частая ошибка новичка.

Связи между таблицами задаются через ForeignKey (внешний ключ — «ссылка на id
другой таблицы») и relationship (удобный доступ к связанным объектам из Python).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import enum

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    """Текущее время по UTC без таймзоны — единый формат для всех дат в базе."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserRole(str, enum.Enum):
    """Роли пользователей. admin — всё, manager — работа со складом, buyer — только просмотр."""

    admin = "admin"
    manager = "manager"
    buyer = "buyer"


class User(Base):
    """Пользователь системы (тот, кто заходит по логину/паролю)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)  # логин (уникальный)
    full_name: Mapped[str] = mapped_column(String(160), default="")  # имя для отображения
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.manager)  # права
    hashed_password: Mapped[str] = mapped_column(String(255))  # пароль в зашифрованном виде (не открытый текст!)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # выключенный юзер не может войти
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    imports: Mapped[list["ImportBatch"]] = relationship(back_populates="created_by")


class ImportBatch(Base):
    """Одна загрузка Excel-файла. Нужна для истории импортов и сравнения периодов."""

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))  # имя загруженного файла
    rows_count: Mapped[int] = mapped_column(Integer, default=0)  # сколько строк импортировано
    source: Mapped[str] = mapped_column(String(80), default="excel")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # кто загрузил

    created_by: Mapped[User | None] = relationship(back_populates="imports")
    products: Mapped[list["Product"]] = relationship(back_populates="import_batch")
    snapshots: Mapped[list["ProductSnapshot"]] = relationship(back_populates="import_batch")


class Product(Base):
    """ТОВАР — центральная таблица всего проекта. Почти всё крутится вокруг неё."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sku: Mapped[str] = mapped_column(String(80), unique=True, index=True)  # артикул (уникальный код товара)
    name: Mapped[str] = mapped_column(String(255), index=True)  # название
    category: Mapped[str] = mapped_column(String(120), default="Без категории")
    stock: Mapped[int] = mapped_column(Integer, default=0)  # текущий остаток на складе, шт.
    sold_month: Mapped[int] = mapped_column(Integer, default=0)  # продано за последний месяц, шт.
    avg_monthly_sales: Mapped[float] = mapped_column(Float, default=0)  # средние продажи в месяц (спрос)
    purchase_price: Mapped[float] = mapped_column(Float, default=0)  # закупочная цена
    sale_price: Mapped[float] = mapped_column(Float, default=0)  # цена продажи
    last_sale_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # дата последней продажи
    supplier: Mapped[str] = mapped_column(String(160), default="")  # поставщик текстом (из Excel)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)  # ссылка на справочник поставщиков
    min_stock: Mapped[int] = mapped_column(Integer, default=5)  # минимальный остаток (ниже — пора заказывать)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7)  # срок поставки в днях
    notes: Mapped[str] = mapped_column(Text, default="")  # комментарий менеджера
    do_not_order: Mapped[bool] = mapped_column(Boolean, default=False)  # флаг «не закупать»
    is_seasonal: Mapped[bool] = mapped_column(Boolean, default=False)  # флаг «сезонный»
    is_on_demand: Mapped[bool] = mapped_column(Boolean, default=False)  # флаг «под заказ»
    # Поля ручной корректировки риска (когда менеджер не согласен с авто-оценкой):
    risk_status_override: Mapped[str | None] = mapped_column(String(40), nullable=True)  # ручной статус риска вместо авто
    risk_priority: Mapped[str | None] = mapped_column(String(20), nullable=True)  # приоритет: low/medium/high/critical
    risk_note: Mapped[str] = mapped_column(Text, default="")  # заметка по риску (заменяет авто-рекомендацию)
    excluded_from_ai: Mapped[bool] = mapped_column(Boolean, default=False)  # не показывать товар AI-советнику
    risk_resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    risk_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)  # из какой загрузки Excel
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)  # авто-обновляется при изменении

    import_batch: Mapped[ImportBatch | None] = relationship(back_populates="products")


class Supplier(Base):
    """ПОСТАВЩИК — справочник, к которому привязываются товары (Product.supplier_id)."""

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)  # название (уникальное)
    contact_person: Mapped[str] = mapped_column(String(160), default="")  # контактное лицо
    phone: Mapped[str] = mapped_column(String(60), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    reliability: Mapped[int] = mapped_column(Integer, default=3)  # надёжность 1..5 (звёзды в интерфейсе)
    min_order_amount: Mapped[float] = mapped_column(Float, default=0)  # минимальная сумма заказа
    payment_terms: Mapped[str] = mapped_column(String(200), default="")  # условия оплаты
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7)  # типовой срок поставки
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class MovementType(str, enum.Enum):
    """Типы движения товара по складу (для журнала StockMovement)."""

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
    """ЖУРНАЛ ДВИЖЕНИЙ — одна строка = один приход/списание/продажа и т.п.

    Показывает историю: почему остаток изменился, на сколько, кто и когда.
    quantity — это итоговая знаковая дельта (приход +, списание −)."""

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)  # какой товар
    movement_type: Mapped[str] = mapped_column(String(20), index=True)  # тип (см. MovementType)
    quantity: Mapped[int] = mapped_column(Integer)  # знаковое изменение остатка (+/−)
    stock_before: Mapped[int] = mapped_column(Integer)  # остаток ДО операции
    stock_after: Mapped[int] = mapped_column(Integer)  # остаток ПОСЛЕ операции
    note: Mapped[str] = mapped_column(Text, default="")  # комментарий
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(160), default="")  # имя автора (сохраняем на случай удаления юзера)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    product: Mapped["Product"] = relationship()


class AuditLog(Base):
    """АУДИТ — кто что сделал (создал товар, загрузил Excel, сменил пароль и т.п.).

    username хранится текстом отдельно, чтобы запись осталась читаемой даже если
    пользователя потом удалят."""

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
    """УВЕДОМЛЕНИЕ — оповещение пользователю (товар заканчивается, залежался и т.п.).

    severity: critical / warning / notice (цвет точки). is_read — прочитано ли."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    type: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="notice")
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text, default="")
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class OrderStatus(str, enum.Enum):
    """Статусы заказа поставщику (жизненный цикл заказа)."""

    draft = "draft"          # черновик
    sent = "sent"            # отправлен поставщику
    received = "received"    # получен (создаёт приход на склад)
    cancelled = "cancelled"  # отменён


# Какие переходы статуса разрешены. Например, из «черновика» можно «отправить»
# или «отменить», но нельзя сразу «получить». Проверяется в services/orders.py.
ORDER_TRANSITIONS = {
    "draft": {"sent", "cancelled"},
    "sent": {"received", "cancelled"},
    "received": set(),   # конечный статус — дальше переходов нет
    "cancelled": set(),  # конечный статус
}


class PurchaseOrder(Base):
    """ЗАКАЗ ПОСТАВЩИКУ. Создаётся из плана закупок, имеет статус и список позиций."""

    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    supplier_name: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    total_amount: Mapped[float] = mapped_column(Float, default=0)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class PurchaseOrderItem(Base):
    """ПОЗИЦИЯ ЗАКАЗА — одна строка заказа (товар + количество + цена на момент заказа)."""

    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    sku: Mapped[str] = mapped_column(String(80), default="")
    name: Mapped[str] = mapped_column(String(255), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    purchase_price: Mapped[float] = mapped_column(Float, default=0)
    line_total: Mapped[float] = mapped_column(Float, default=0)

    order: Mapped["PurchaseOrder"] = relationship(back_populates="items")


class ProductSnapshot(Base):
    """СНИМОК ТОВАРА на момент загрузки Excel. Это «фотография» остатков/продаж.

    Нужен, чтобы сравнивать периоды (дашборд) и считать стабильность спроса (XYZ):
    каждый импорт = снимок состояния, по разнице снимков видим динамику."""

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
