from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from .models import UserRole


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    full_name: str = Field(default="", max_length=160)
    password: str = Field(min_length=6)
    role: UserRole = UserRole.manager


class ImportBatchOut(BaseModel):
    id: int
    filename: str
    rows_count: int
    source: str
    created_at: datetime
    created_by_id: int | None

    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    category: str
    stock: int
    sold_month: int
    avg_monthly_sales: float
    purchase_price: float
    sale_price: float
    last_sale_date: date | None
    supplier: str
    min_stock: int
    lead_time_days: int
    notes: str
    import_batch_id: int | None
    created_at: datetime
    updated_at: datetime
    status: str
    action: str
    severity: str
    days_left: int | None
    days_without_sales: int | None
    recommendation: str
    margin_percent: float


class DashboardResponse(BaseModel):
    metrics: dict
    ai_summary: str
    urgent_actions: list[dict]
    top_sales: list[dict]
    forecast: list[dict]
    import_history: list[dict]
    status_distribution: list[dict]


class UploadResponse(BaseModel):
    batch: ImportBatchOut
    imported: int
    updated: int
    created: int
    warnings: list[str]


class ProductUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    supplier: str | None = None
    min_stock: int | None = None
    lead_time_days: int | None = None
    notes: str | None = None
    do_not_order: bool | None = None
    is_seasonal: bool | None = None
    is_on_demand: bool | None = None


class ImportPreviewRow(BaseModel):
    row_number: int
    sku: str
    name: str
    action: str
    error: str | None = None


class ImportPreview(BaseModel):
    columns_found: list[str]
    columns_missing: list[str]
    total_rows: int
    new_count: int
    update_count: int
    error_count: int
    warnings: list[str]
    preview_rows: list[ImportPreviewRow]
