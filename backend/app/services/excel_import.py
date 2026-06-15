from __future__ import annotations

from datetime import datetime
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO

import pandas as pd
from sqlalchemy.orm import Session

from ..models import ImportBatch, Product, ProductSnapshot, User


COLUMN_ALIASES = {
    "sku": ["артикул", "sku", "код", "код товара"],
    "name": ["название товара", "товар", "название", "наименование"],
    "category": ["категория", "группа"],
    "stock": ["остаток", "остаток на складе", "количество"],
    "sold_month": ["продано за месяц", "продажи за месяц", "продано"],
    "avg_monthly_sales": ["средние продажи в месяц", "средний спрос", "спрос в месяц"],
    "purchase_price": ["закупочная цена", "закупка", "себестоимость"],
    "sale_price": ["продажная цена", "цена продажи", "цена"],
    "last_sale_date": ["дата последней продажи", "последняя продажа"],
    "supplier": ["поставщик"],
    "min_stock": ["минимальный остаток", "мин остаток", "min stock"],
    "lead_time_days": ["срок поставки", "срок поставки дней", "lead time"],
}


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _find_columns(columns: list[str]) -> dict[str, str]:
    normalized = {_normalize_header(column): column for column in columns}
    result = {}
    for key, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                result[key] = normalized[alias]
                break
    return result


def _clean_int(
    value,
    default: int = 0,
    *,
    field_name: str = "",
    row_number: int | None = None,
    warnings: list[str] | None = None,
    minimum: int | None = 0,
) -> int:
    if pd.isna(value) or value == "":
        return default
    try:
        result = int(float(str(value).replace(" ", "").replace(",", ".")))
    except (TypeError, ValueError):
        if warnings is not None and row_number is not None:
            warnings.append(
                f"Строка {row_number}: поле '{field_name}' содержит нечисловое значение, использовано {default}"
            )
        return default
    if minimum is not None and result < minimum:
        if warnings is not None and row_number is not None:
            warnings.append(
                f"Строка {row_number}: поле '{field_name}' меньше {minimum}, использовано {minimum}"
            )
        return minimum
    return result


def _clean_float(
    value,
    default: float = 0,
    *,
    field_name: str = "",
    row_number: int | None = None,
    warnings: list[str] | None = None,
    minimum: float | None = 0,
) -> float:
    if pd.isna(value) or value == "":
        return default
    try:
        result = float(str(value).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        if warnings is not None and row_number is not None:
            warnings.append(
                f"Строка {row_number}: поле '{field_name}' содержит нечисловое значение, использовано {default}"
            )
        return default
    if minimum is not None and result < minimum:
        if warnings is not None and row_number is not None:
            warnings.append(
                f"Строка {row_number}: поле '{field_name}' меньше {minimum}, использовано {minimum}"
            )
        return minimum
    return result


def _clean_text(value, default: str = "") -> str:
    if pd.isna(value):
        return default
    return str(value).strip()


def _clean_date(value, *, field_name: str = "", row_number: int | None = None, warnings: list[str] | None = None):
    if pd.isna(value) or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        if warnings is not None and row_number is not None:
            warnings.append(f"Строка {row_number}: поле '{field_name}' не распознано как дата")
        return None
    return parsed.date()


def _slug_sku(name: str, index: int) -> str:
    raw = re.sub(r"[^A-Za-zА-Яа-я0-9]+", "-", name).strip("-").upper()
    return (raw[:40] or f"ITEM-{index}") + f"-{index:03d}"


def preview_excel_import(db: Session, file: BinaryIO, filename: str) -> dict:
    """Parse the Excel file and return a preview without writing to the database."""
    suffix = Path(filename).suffix or ".xlsx"
    with NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        temp.write(file.read())
        temp_path = Path(temp.name)

    try:
        try:
            frame = pd.read_excel(temp_path)
        except Exception as exc:
            raise ValueError("Не удалось прочитать Excel-файл. Проверьте формат и структуру файла.") from exc
    finally:
        temp_path.unlink(missing_ok=True)

    if frame.empty:
        raise ValueError("Excel-файл пустой")

    columns = _find_columns(list(frame.columns))
    columns_found = list(columns.keys())
    columns_missing = [key for key in COLUMN_ALIASES if key not in columns]

    warnings: list[str] = []
    preview_rows = []
    new_count = 0
    update_count = 0
    error_count = 0

    for index, row in frame.iterrows():
        row_number = int(index) + 2
        name = _clean_text(row[columns["name"]]) if "name" in columns else ""
        if not name:
            error_count += 1
            preview_rows.append(
                {
                    "row_number": row_number,
                    "sku": "",
                    "name": "(пусто)",
                    "action": "error",
                    "error": "Пустое название",
                }
            )
            continue

        sku = _clean_text(row[columns["sku"]]) if "sku" in columns else ""
        if not sku:
            sku = _slug_sku(name, index + 1)

        existing = db.query(Product).filter(Product.sku == sku).first()
        action = "update" if existing else "create"
        if existing:
            update_count += 1
        else:
            new_count += 1

        preview_rows.append(
            {
                "row_number": row_number,
                "sku": sku,
                "name": name,
                "action": action,
                "error": None,
            }
        )

    return {
        "columns_found": columns_found,
        "columns_missing": columns_missing,
        "total_rows": len(frame),
        "new_count": new_count,
        "update_count": update_count,
        "error_count": error_count,
        "warnings": warnings,
        "preview_rows": preview_rows[:50],
    }


def import_products_from_excel(db: Session, file: BinaryIO, filename: str, user: User) -> dict:
    suffix = Path(filename).suffix or ".xlsx"
    with NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        temp.write(file.read())
        temp_path = Path(temp.name)

    warnings: list[str] = []
    try:
        try:
            frame = pd.read_excel(temp_path)
        except Exception as exc:
            raise ValueError("Не удалось прочитать Excel-файл. Проверьте формат и структуру файла.") from exc
    finally:
        temp_path.unlink(missing_ok=True)

    if frame.empty:
        raise ValueError("Excel-файл пустой")

    columns = _find_columns(list(frame.columns))
    if "name" not in columns or "stock" not in columns:
        raise ValueError("В Excel обязательны колонки: 'Название товара' и 'Остаток'")

    created = 0
    updated = 0
    imported = 0

    try:
        batch = ImportBatch(filename=filename, rows_count=0, created_by_id=user.id)
        db.add(batch)
        db.flush()

        for index, row in frame.iterrows():
            row_number = int(index) + 2
            name = _clean_text(row[columns["name"]])
            if not name:
                warnings.append(f"Строка {row_number}: пропущено пустое название")
                continue

            sku = _clean_text(row[columns["sku"]]) if "sku" in columns else ""
            if not sku:
                sku = _slug_sku(name, index + 1)
            product = db.query(Product).filter(Product.sku == sku).first()
            if not product:
                product = Product(sku=sku, name=name)
                db.add(product)
                created += 1
            else:
                updated += 1

            product.name = name
            product.category = _clean_text(row[columns["category"]], "Без категории") if "category" in columns else "Без категории"
            product.stock = _clean_int(
                row[columns["stock"]],
                field_name="Остаток",
                row_number=row_number,
                warnings=warnings,
            )
            product.sold_month = (
                _clean_int(
                    row[columns["sold_month"]],
                    field_name="Продано за месяц",
                    row_number=row_number,
                    warnings=warnings,
                )
                if "sold_month" in columns
                else 0
            )
            product.avg_monthly_sales = (
                _clean_float(
                    row[columns["avg_monthly_sales"]],
                    field_name="Средние продажи в месяц",
                    row_number=row_number,
                    warnings=warnings,
                )
                if "avg_monthly_sales" in columns
                else float(product.sold_month)
            )
            product.purchase_price = (
                _clean_float(
                    row[columns["purchase_price"]],
                    field_name="Закупочная цена",
                    row_number=row_number,
                    warnings=warnings,
                )
                if "purchase_price" in columns
                else 0
            )
            product.sale_price = (
                _clean_float(
                    row[columns["sale_price"]],
                    field_name="Продажная цена",
                    row_number=row_number,
                    warnings=warnings,
                )
                if "sale_price" in columns
                else 0
            )
            product.last_sale_date = (
                _clean_date(
                    row[columns["last_sale_date"]],
                    field_name="Дата последней продажи",
                    row_number=row_number,
                    warnings=warnings,
                )
                if "last_sale_date" in columns
                else None
            )
            product.supplier = _clean_text(row[columns["supplier"]]) if "supplier" in columns else ""
            product.min_stock = (
                _clean_int(
                    row[columns["min_stock"]],
                    5,
                    field_name="Минимальный остаток",
                    row_number=row_number,
                    warnings=warnings,
                )
                if "min_stock" in columns
                else 5
            )
            product.lead_time_days = (
                _clean_int(
                    row[columns["lead_time_days"]],
                    7,
                    field_name="Срок поставки",
                    row_number=row_number,
                    warnings=warnings,
                    minimum=1,
                )
                if "lead_time_days" in columns
                else 7
            )
            product.import_batch_id = batch.id

            db.add(
                ProductSnapshot(
                    import_batch_id=batch.id,
                    sku=product.sku,
                    name=product.name,
                    category=product.category,
                    stock=product.stock,
                    sold_month=product.sold_month,
                    avg_monthly_sales=product.avg_monthly_sales,
                    sale_price=product.sale_price,
                )
            )
            imported += 1

        if imported == 0:
            raise ValueError("В Excel не найдено ни одной строки с товаром")

        batch.rows_count = imported
        db.commit()
        db.refresh(batch)
    except Exception:
        db.rollback()
        raise

    return {
        "batch": batch,
        "imported": imported,
        "created": created,
        "updated": updated,
        "warnings": warnings,
    }
