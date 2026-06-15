from __future__ import annotations

import json
import urllib.request

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Product
from .analytics import product_signal


def _rule_based_summary(products: list[Product]) -> str:
    if not products:
        return "Загрузите Excel-файл, чтобы AI-советник сформировал рекомендации по складу."

    signals = [(product, product_signal(product)) for product in products]
    urgent = [item for item in signals if item[1]["status"] in {"Срочно заказать", "Нет в наличии"}]
    dead = [item for item in signals if item[1]["status"] in {"Мертвый груз", "Сделать скидку"}]
    growing = [item for item in signals if item[1]["status"] == "Растущий спрос"]

    fragments: list[str] = []
    if urgent:
        names = ", ".join(product.name for product, _ in urgent[:3])
        fragments.append(f"Сначала проверьте закупку: {names}.")
    if dead:
        names = ", ".join(product.name for product, _ in dead[:3])
        fragments.append(f"Для залежавшихся позиций стоит запустить скидку: {names}.")
    if growing:
        names = ", ".join(product.name for product, _ in growing[:3])
        fragments.append(f"По растущему спросу можно усилить запас: {names}.")

    return " ".join(fragments) if fragments else "Критических отклонений нет: склад можно вести по текущему плану."


def _call_claude(prompt: str) -> str | None:
    if not settings.claude_enabled or not settings.claude_api_key:
        return None

    payload = {
        "model": settings.claude_model,
        "max_tokens": 500,
        "messages": [{"role": "user", "content": prompt}],
    }
    request = urllib.request.Request(
        settings.claude_api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": settings.claude_api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text")
    except Exception:
        return None
    return None


def build_ai_summary(db: Session) -> str:
    products = db.query(Product).order_by(Product.updated_at.desc()).limit(80).all()
    if not settings.claude_enabled:
        return _rule_based_summary(products)

    compact = [
        {
            "name": product.name,
            "category": product.category,
            "stock": product.stock,
            "sold_month": product.sold_month,
            "avg_monthly_sales": product.avg_monthly_sales,
            "last_sale_date": product.last_sale_date.isoformat() if product.last_sale_date else None,
            "signal": product_signal(product)["status"],
        }
        for product in products
    ]
    prompt = (
        "Ты AI-советник для склада строительных инструментов. "
        "Коротко, по-русски, в 2-3 предложениях дай управленческую рекомендацию. "
        "Не выдумывай данные, опирайся только на JSON.\n\n"
        f"{json.dumps(compact, ensure_ascii=False)}"
    )
    return _call_claude(prompt) or _rule_based_summary(products)
