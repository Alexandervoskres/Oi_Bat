from __future__ import annotations

from collections import Counter
from datetime import date
import math

from sqlalchemy.orm import Session

from ..models import ImportBatch, Product, ProductSnapshot


STATUS_LABELS = {
    "out_of_stock": "Нет в наличии",
    "order_now": "Срочно заказать",
    "discount": "Сделать скидку",
    "dead_stock": "Мертвый груз",
    "growing": "Растущий спрос",
    "ok": "Норма",
}


def margin_percent(product: Product) -> float:
    if not product.sale_price:
        return 0
    return round(((product.sale_price - product.purchase_price) / product.sale_price) * 100, 1)


def product_signal(product: Product, today: date | None = None) -> dict:
    today = today or date.today()
    demand = max(float(product.avg_monthly_sales or 0), float(product.sold_month or 0))
    daily_demand = demand / 30 if demand > 0 else 0
    days_left = None
    if daily_demand > 0:
        days_left = max(0, math.ceil(product.stock / daily_demand))

    days_without_sales = None
    if product.last_sale_date:
        days_without_sales = max(0, (today - product.last_sale_date).days)

    status = "ok"
    action = "Следить по плану"
    severity = "normal"

    if product.stock <= 0:
        status = "out_of_stock"
        action = "Срочно заказать"
        severity = "critical"
    elif days_left is not None and days_left <= max(product.lead_time_days + 3, 14):
        status = "order_now"
        action = "Заказать"
        severity = "critical" if days_left <= product.lead_time_days else "warning"
    elif product.stock <= product.min_stock:
        status = "order_now"
        action = "Заказать"
        severity = "warning"
    elif days_without_sales is not None and days_without_sales >= 90 and product.stock >= product.min_stock:
        status = "dead_stock"
        action = "Сделать распродажу"
        severity = "warning"
    elif days_without_sales is not None and days_without_sales >= 60:
        status = "discount"
        action = "Скидка 10-15%"
        severity = "notice"
    elif product.avg_monthly_sales and product.sold_month >= product.avg_monthly_sales * 1.25:
        status = "growing"
        action = "Усилить закупку"
        severity = "positive"

    label = STATUS_LABELS[status]
    days_text = f"{days_left} дней" if days_left is not None else "нет спроса"

    if status == "out_of_stock":
        recommendation = f"{product.name}: остаток 0 шт. Нужно оформить заказ у поставщика."
    elif status == "order_now":
        recommendation = (
            f"{product.name}: остаток {product.stock} шт., хватит примерно на {days_text}. "
            f"Рекомендуется заказать с учетом срока поставки {product.lead_time_days} дн."
        )
    elif status == "dead_stock":
        recommendation = (
            f"{product.name}: нет продаж {days_without_sales} дн., остаток {product.stock} шт. "
            "Рекомендуется распродажа или перенос бюджета в ходовые позиции."
        )
    elif status == "discount":
        recommendation = (
            f"{product.name}: продаж не было {days_without_sales} дн. "
            "Рекомендуется скидка 10-15% и проверка цены относительно конкурентов."
        )
    elif status == "growing":
        recommendation = (
            f"{product.name}: спрос выше среднего. Стоит увеличить план закупки и держать запас."
        )
    else:
        recommendation = f"{product.name}: показатели в норме, достаточно регулярного контроля."

    return {
        "status": label,
        "status_code": status,
        "action": action,
        "severity": severity,
        "days_left": days_left,
        "days_without_sales": days_without_sales,
        "recommendation": recommendation,
        "margin_percent": margin_percent(product),
    }


def product_to_dict(product: Product) -> dict:
    signal = product_signal(product)
    return {
        "id": product.id,
        "sku": product.sku,
        "name": product.name,
        "category": product.category,
        "stock": product.stock,
        "sold_month": product.sold_month,
        "avg_monthly_sales": product.avg_monthly_sales,
        "purchase_price": product.purchase_price,
        "sale_price": product.sale_price,
        "last_sale_date": product.last_sale_date,
        "supplier": product.supplier,
        "min_stock": product.min_stock,
        "lead_time_days": product.lead_time_days,
        "notes": product.notes,
        "import_batch_id": product.import_batch_id,
        "created_at": product.created_at,
        "updated_at": product.updated_at,
        **signal,
    }


def build_dashboard(db: Session, ai_summary: str) -> dict:
    products = db.query(Product).order_by(Product.name.asc()).all()
    product_rows = [product_to_dict(product) for product in products]
    counter = Counter(row["status"] for row in product_rows)
    critical = [row for row in product_rows if row["severity"] in {"critical", "warning"}]
    dead = [row for row in product_rows if row["status"] in {"Мертвый груз", "Сделать скидку"}]

    sales_revenue = sum(product.sold_month * product.sale_price for product in products)
    inventory_value = sum(product.stock * product.purchase_price for product in products)
    sold_units = sum(product.sold_month for product in products)

    top_sales = sorted(
        (
            {
                "name": product.name,
                "category": product.category,
                "sold_month": product.sold_month,
                "revenue": round(product.sold_month * product.sale_price, 2),
            }
            for product in products
        ),
        key=lambda item: item["sold_month"],
        reverse=True,
    )[:7]

    forecast = sorted(
        product_rows,
        key=lambda row: (row["days_left"] if row["days_left"] is not None else 9999, -row["stock"]),
    )[:12]

    batches = db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(8).all()
    import_history = []
    for batch in reversed(batches):
        snapshots = db.query(ProductSnapshot).filter(ProductSnapshot.import_batch_id == batch.id).all()
        import_history.append(
            {
                "id": batch.id,
                "date": batch.created_at.strftime("%d.%m"),
                "filename": batch.filename,
                "rows_count": batch.rows_count,
                "stock": sum(item.stock for item in snapshots),
                "sold_month": sum(item.sold_month for item in snapshots),
            }
        )

    return {
        "metrics": {
            "products": len(products),
            "low_stock": len([row for row in product_rows if row["status"] in {"Нет в наличии", "Срочно заказать"}]),
            "dead_stock": len(dead),
            "sales_revenue": round(sales_revenue, 2),
            "sold_units": sold_units,
            "inventory_value": round(inventory_value, 2),
        },
        "ai_summary": ai_summary,
        "urgent_actions": critical[:6],
        "top_sales": top_sales,
        "forecast": forecast,
        "import_history": import_history,
        "status_distribution": [{"status": key, "count": value} for key, value in counter.items()],
    }
