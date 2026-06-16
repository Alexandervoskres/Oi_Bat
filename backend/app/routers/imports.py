from __future__ import annotations

from io import BytesIO

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ImportBatch, User, UserRole
from ..schemas import ImportBatchOut, ImportPreview, UploadResponse
from ..security import require_roles
from ..services.audit import record_audit
from ..services.excel_import import import_products_from_excel, preview_excel_import


router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.get("", response_model=list[ImportBatchOut])
def list_imports(
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager, UserRole.buyer)),
    db: Session = Depends(get_db),
):
    return db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).all()


@router.post("/preview", response_model=ImportPreview)
async def preview_import(
    file: UploadFile = File(...),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Загрузите Excel-файл .xlsx или .xls")
    try:
        return preview_excel_import(db, file.file, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/upload", response_model=UploadResponse)
async def upload_excel(
    file: UploadFile = File(...),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Загрузите Excel-файл .xlsx или .xls")

    try:
        result = import_products_from_excel(db, file.file, file.filename, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record_audit(
        db, user, "import.upload", entity_type="import",
        entity_id=result["batch"].id,
        detail=(
            f"Импорт «{file.filename}»: {result['imported']} строк "
            f"(новых {result['created']}, обновлено {result['updated']})"
        ),
    )
    return result


@router.get("/template.xlsx")
def download_template(_: User = Depends(require_roles(UserRole.admin, UserRole.manager, UserRole.buyer))):
    rows = [
        {
            "Артикул": "BOSCH-226",
            "Название товара": "Перфоратор Bosch GBH 2-26",
            "Категория": "Дрели",
            "Остаток": 3,
            "Продано за месяц": 10,
            "Средние продажи в месяц": 10,
            "Закупочная цена": 8400,
            "Продажная цена": 12400,
            "Дата последней продажи": "06.06.2026",
            "Поставщик": "Bosch Pro",
            "Минимальный остаток": 5,
            "Срок поставки": 7,
        },
        {
            "Артикул": "DEWALT-771",
            "Название товара": "Шуруповерт DeWalt DCD771",
            "Категория": "Шуруповерты",
            "Остаток": 14,
            "Продано за месяц": 1,
            "Средние продажи в месяц": 1,
            "Закупочная цена": 6900,
            "Продажная цена": 9900,
            "Дата последней продажи": "02.04.2026",
            "Поставщик": "DeWalt",
            "Минимальный остаток": 4,
            "Срок поставки": 10,
        },
        {
            "Артикул": "MAKITA-HP1630",
            "Название товара": "Дрель Makita HP1630",
            "Категория": "Дрели",
            "Остаток": 22,
            "Продано за месяц": 7,
            "Средние продажи в месяц": 4,
            "Закупочная цена": 4100,
            "Продажная цена": 6500,
            "Дата последней продажи": "12.06.2026",
            "Поставщик": "Makita",
            "Минимальный остаток": 6,
            "Срок поставки": 8,
        },
    ]
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False, sheet_name="Товары")
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="skladai-template.xlsx"'},
    )
