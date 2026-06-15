from __future__ import annotations

import json
import math
import re
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


def _recommended_qty(product: Product) -> int:
    demand = max(float(product.avg_monthly_sales or 0), float(product.sold_month or 0), 1)
    need = max(product.min_stock - product.stock, 1)
    return max(need, math.ceil(demand * (product.lead_time_days / 30 + 1)))


def _rule_based_chat(message: str, products: list[Product]) -> dict:
    """Answer common warehouse questions without calling Claude."""
    msg = message.lower().strip()
    signals = [(p, product_signal(p)) for p in products if not p.excluded_from_ai]
    urgent = [
        (p, s)
        for p, s in signals
        if s["severity"] in {"critical", "warning"} and not p.do_not_order
    ]
    urgent.sort(key=lambda x: (0 if x[1]["severity"] == "critical" else 1, x[1].get("days_left") or 9999))
    dead = [(p, s) for p, s in signals if s["status_code"] in {"dead_stock", "discount"}]
    growing = [(p, s) for p, s in signals if s["status_code"] == "growing"]

    used_products: list[str] = []

    # Budget allocation question.
    has_budget = ("бюджет" in msg or "₽" in msg or "руб" in msg or "тыс" in msg) and any(c.isdigit() for c in msg)
    if has_budget:
        digits = re.findall(r"\d[\d\s]*", message)
        try:
            budget = int(re.sub(r"\D", "", digits[0])) if digits else 100_000
        except (ValueError, IndexError):
            budget = 100_000
        if budget < 1000:
            budget *= 1000  # interpret "100" as 100000

        items: list[str] = []
        remaining = budget
        for p, _ in urgent:
            if p.purchase_price > 0 and remaining >= p.purchase_price:
                qty = min(_recommended_qty(p), int(remaining // p.purchase_price))
                if qty > 0:
                    cost = qty * p.purchase_price
                    supplier = f", поставщик: {p.supplier}" if p.supplier else ""
                    items.append(f"• {p.name} — {qty} шт. ({cost:,.0f} ₽){supplier}")
                    remaining -= cost
                    used_products.append(p.name)
            if len(items) >= 8:
                break

        if items:
            answer = f"На бюджет {budget:,} ₽ рекомендую заказать:\n" + "\n".join(items)
            if remaining > 100:
                answer += f"\nОстаток бюджета: {remaining:,.0f} ₽"
            actions = ["Перейти в Закупки", "Скачать CSV"]
        else:
            answer = f"На бюджет {budget:,} ₽ срочных закупок нет — критичные позиции отсутствуют или не хватает данных о ценах."
            actions = []
        return {"answer": answer, "suggested_actions": actions, "used_products": used_products}

    # What to order.
    if any(w in msg for w in ["заказ", "закупить", "закупка", "купить", "заканчива"]):
        if not urgent:
            return {"answer": "Срочных закупок нет: все позиции в норме или помечены «не закупать».", "suggested_actions": [], "used_products": []}
        lines = []
        for p, s in urgent[:7]:
            days = s.get("days_left")
            days_txt = f", хватит на {days} дн." if days is not None else ""
            supplier = f" — {p.supplier}" if p.supplier else ""
            lines.append(f"• {p.name} ({s['status']}{days_txt}){supplier}")
            used_products.append(p.name)
        answer = f"К срочному заказу ({len(urgent)} поз.):\n" + "\n".join(lines)
        if len(urgent) > 7:
            answer += f"\n... и ещё {len(urgent) - 7} позиций."
        return {"answer": answer, "suggested_actions": ["Открыть Закупки", "Скачать CSV"], "used_products": used_products}

    # What to sell / discount.
    if any(w in msg for w in ["распрод", "скидк", "залежал", "мертв", "избавить"]):
        if not dead:
            return {"answer": "Нет товаров с признаками мертвого груза или низких продаж.", "suggested_actions": [], "used_products": []}
        lines = []
        for p, s in dead[:7]:
            dwos = s.get("days_without_sales")
            txt = f", без продаж {dwos} дн." if dwos else ""
            lines.append(f"• {p.name} — {p.stock} шт. на складе{txt}")
            used_products.append(p.name)
        answer = f"Рекомендую распродать или дать скидку ({len(dead)} поз.):\n" + "\n".join(lines)
        return {"answer": answer, "suggested_actions": ["Сделать скидку", "Перейти в Риски"], "used_products": used_products}

    # Risks overview.
    if any(w in msg for w in ["риск", "проблем", "опасн", "критич"]):
        n_crit = sum(1 for _, s in signals if s["severity"] == "critical")
        n_warn = sum(1 for _, s in signals if s["severity"] == "warning")
        lines = [
            f"Всего товаров: {len(signals)}",
            f"Критичных (нет/заканчивается): {n_crit}",
            f"Предупреждений: {n_warn}",
            f"Залежавшихся: {len(dead)}",
        ]
        if urgent:
            lines.append("\nСамые срочные:")
            for p, s in urgent[:4]:
                lines.append(f"• {p.name} — {s['status']}")
                used_products.append(p.name)
        return {"answer": "\n".join(lines), "suggested_actions": ["Открыть Риски"], "used_products": used_products}

    # Week plan.
    if any(w in msg for w in ["план", "недел"]):
        actions = []
        for p, _ in urgent[:5]:
            actions.append(f"Заказать: {p.name} (срочно)")
            used_products.append(p.name)
        for p, _ in dead[:3]:
            actions.append(f"Скидка: {p.name}")
        for p, _ in growing[:2]:
            actions.append(f"Усилить запас: {p.name}")
        if actions:
            answer = "Приоритетный план на неделю:\n" + "\n".join(f"{i + 1}. {a}" for i, a in enumerate(actions))
        else:
            answer = "Нет срочных действий — склад работает в штатном режиме."
        return {"answer": answer, "suggested_actions": ["Открыть Закупки", "Открыть Риски"], "used_products": used_products}

    # Why a specific product is at risk.
    if any(w in msg for w in ["почему", "зачем", "попал", "статус"]):
        for p, s in signals:
            if p.name.lower() in msg or (p.sku and p.sku.lower() in msg):
                answer = s["recommendation"]
                if s.get("is_manual_risk"):
                    answer = f"[Ручной статус] {answer}"
                used_products.append(p.name)
                return {"answer": answer, "suggested_actions": ["Открыть карточку товара"], "used_products": used_products}
        return {"answer": "Уточните название товара — не нашёл подходящую позицию в данных склада.", "suggested_actions": [], "used_products": []}

    # What not to order.
    if "не закуп" in msg or "не стоит" in msg or "не нужно" in msg:
        no_order = [p for p, _ in signals if p.do_not_order]
        if no_order:
            lines = [f"• {p.name}" for p in no_order[:10]]
            answer = f"Помечены «не закупать» ({len(no_order)} поз.):\n" + "\n".join(lines)
        else:
            answer = "Нет товаров с флагом «не закупать»."
        return {"answer": answer, "suggested_actions": [], "used_products": []}

    # Generic fallback.
    if not products:
        return {"answer": "Данных о товарах нет. Загрузите Excel-файл, чтобы AI мог дать рекомендации.", "suggested_actions": ["Перейти в Импорт"], "used_products": []}
    return {
        "answer": _rule_based_summary(products),
        "suggested_actions": ["Что заказать?", "Риски склада", "Что распродать?"],
        "used_products": [],
    }


def chat_with_ai(db: Session, message: str) -> dict:
    products = db.query(Product).order_by(Product.updated_at.desc()).limit(120).all()

    if not settings.claude_enabled or not settings.claude_api_key:
        return _rule_based_chat(message, products)

    context_products = [p for p in products if not p.excluded_from_ai]
    compact = []
    for p in context_products:
        sig = product_signal(p)
        compact.append(
            {
                "sku": p.sku,
                "name": p.name,
                "category": p.category,
                "stock": p.stock,
                "sold_month": p.sold_month,
                "avg_monthly_sales": round(p.avg_monthly_sales, 1),
                "purchase_price": p.purchase_price,
                "sale_price": p.sale_price,
                "supplier": p.supplier,
                "lead_time_days": p.lead_time_days,
                "min_stock": p.min_stock,
                "last_sale_date": p.last_sale_date.isoformat() if p.last_sale_date else None,
                "status": sig["status"],
                "severity": sig["severity"],
                "days_left": sig.get("days_left"),
                "is_manual": sig.get("is_manual_risk", False),
                "risk_note": p.risk_note or None,
                "do_not_order": p.do_not_order or None,
                "is_seasonal": p.is_seasonal or None,
            }
        )

    system = (
        "Ты AI-советник для склада строительных инструментов. "
        "Отвечай только по-русски, кратко и конкретно. "
        "Используй только данные из JSON-контекста — не выдумывай товары. "
        "Если товара нет в данных — честно скажи об этом. "
        "При вопросе о бюджете учитывай purchase_price и рекомендуй количество. "
        "Отвечай практично: списки, цифры, действия."
    )
    prompt = (
        f"{system}\n\nКонтекст склада:\n"
        f"{json.dumps(compact, ensure_ascii=False, separators=(',', ':'))}\n\n"
        f"Вопрос: {message}"
    )

    answer = _call_claude(prompt)
    if answer:
        return {"answer": answer, "suggested_actions": [], "used_products": []}
    return _rule_based_chat(message, products)
