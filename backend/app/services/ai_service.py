from __future__ import annotations

import math
import re

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Product
from .analytics import product_signal
from .claw_agent import call_claw_agent, claw_agent_status


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


def build_ai_summary(db: Session) -> str:
    products = db.query(Product).order_by(Product.updated_at.desc()).limit(80).all()
    return _rule_based_summary(products)


def _recommended_qty(product: Product) -> int:
    demand = max(float(product.avg_monthly_sales or 0), float(product.sold_month or 0), 1)
    need = max(product.min_stock - product.stock, 1)
    return max(need, math.ceil(demand * (product.lead_time_days / 30 + 1)))


def _with_agent_meta(result: dict, agent: str, source: str, status: str | None = None) -> dict:
    return {
        **result,
        "agent": agent,
        "source": source,
        "agent_status": status,
    }


def _format_rub(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ") + " ₽"


def _product_matches_message(product: Product, message: str) -> bool:
    if product.sku and product.sku.lower() in message:
        return True
    if product.name.lower() in message:
        return True

    words = [w for w in re.findall(r"[a-zа-яё0-9]+", product.name.lower()) if len(w) >= 4]
    if not words:
        return False
    hits = sum(1 for word in words if word in message)
    has_distinct_word = any(len(word) >= 6 and word in message for word in words)
    return hits >= min(2, len(words)) or has_distinct_word


def _compact_product_context(products: list[Product]) -> list[dict]:
    compact = []
    for product in products:
        sig = product_signal(product)
        compact.append(
            {
                "sku": product.sku,
                "name": product.name,
                "category": product.category,
                "stock": product.stock,
                "sold_month": product.sold_month,
                "avg_monthly_sales": round(product.avg_monthly_sales, 1),
                "purchase_price": product.purchase_price,
                "sale_price": product.sale_price,
                "supplier": product.supplier,
                "lead_time_days": product.lead_time_days,
                "min_stock": product.min_stock,
                "last_sale_date": product.last_sale_date.isoformat() if product.last_sale_date else None,
                "status": sig["status"],
                "severity": sig["severity"],
                "days_left": sig.get("days_left"),
                "is_manual": sig.get("is_manual_risk", False),
                "risk_note": product.risk_note or None,
                "do_not_order": product.do_not_order or None,
                "is_seasonal": product.is_seasonal or None,
                "is_on_demand": product.is_on_demand or None,
            }
        )
    return compact


def _products_mentioned_in_answer(answer: str, products: list[Product]) -> list[str]:
    msg = answer.lower()
    names: list[str] = []
    for product in products:
        if product.name.lower() in msg or (product.sku and product.sku.lower() in msg):
            names.append(product.name)
        if len(names) >= 8:
            break
    return names


def _actions_from_agent_answer(answer: str) -> list[str]:
    msg = answer.lower()
    actions: list[str] = []
    if any(token in msg for token in ["закуп", "заказ", "поставщик"]):
        actions.append("Открыть Закупки")
    if any(token in msg for token in ["риск", "скид", "не закуп", "залеж"]):
        actions.append("Открыть Риски")
    return actions[:3]


def _is_greeting(message: str) -> bool:
    normalized = re.sub(r"[^a-zа-яё0-9\s]", " ", message.lower()).strip()
    words = set(normalized.split())
    return bool(words & {"привет", "здравствуй", "здравствуйте", "добрый", "hello", "hi"})


def _is_thanks(message: str) -> bool:
    normalized = message.lower()
    return any(token in normalized for token in ["спасибо", "благодарю", "thank"])


def _is_capabilities_question(message: str) -> bool:
    normalized = message.lower()
    return any(
        token in normalized
        for token in [
            "что ты умеешь",
            "чем можешь",
            "помоги",
            "команды",
            "как пользоваться",
            "что спросить",
        ]
    )


def _is_weather_question(message: str) -> bool:
    normalized = message.lower()
    return any(token in normalized for token in ["погода", "температура", "дожд", "снег", "ветер", "weather"])


def _looks_like_warehouse_question(message: str) -> bool:
    normalized = message.lower()
    return any(
        token in normalized
        for token in [
            "склад",
            "товар",
            "остат",
            "закуп",
            "заказ",
            "продаж",
            "риск",
            "постав",
            "цена",
            "бюджет",
            "марж",
            "категор",
            "артикул",
            "спрос",
            "план",
            "недел",
            "скид",
            "распрод",
            "налич",
            "сезон",
        ]
    )


def _rule_based_chat(message: str, products: list[Product]) -> dict:
    """Answer common warehouse questions when the external agent is unavailable."""
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

    # Small talk and help should not turn into a warehouse summary.
    if _is_greeting(msg):
        return {
            "answer": (
                "Привет! Я AI-советник СкладAI. Могу подсказать, что заказать, "
                "что распродать, где риски по остаткам и как уложить закупку в бюджет."
            ),
            "suggested_actions": ["Что заказать?", "Риски склада", "Заказ на 100 000 ₽"],
            "used_products": [],
        }

    if _is_thanks(msg):
        return {
            "answer": "Пожалуйста. Готов помочь с закупками, рисками, остатками и товарами под скидку.",
            "suggested_actions": ["План на неделю", "Риски склада"],
            "used_products": [],
        }

    if _is_capabilities_question(msg):
        return {
            "answer": (
                "Можешь спросить меня: «Что заказать?», «Что не закупать?», "
                "«Какие риски на складе?», «Что распродать?» или «Заказ на 100 000 ₽». "
                "Я отвечаю по текущим данным склада."
            ),
            "suggested_actions": ["Что заказать?", "Что распродать?", "Риски склада"],
            "used_products": [],
        }

    if _is_weather_question(msg):
        return {
            "answer": (
                "Я сейчас не подключен к сервису погоды. В этом чате могу помочь по складу: "
                "закупки, остатки, риски, скидки и план заказа."
            ),
            "suggested_actions": ["Что заказать?", "Риски склада", "План на неделю"],
            "used_products": [],
        }

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
                    items.append(f"• {p.name} — {qty} шт. ({_format_rub(cost)}){supplier}")
                    remaining -= cost
                    used_products.append(p.name)
            if len(items) >= 8:
                break

        if items:
            answer = f"На бюджет {_format_rub(budget)} рекомендую заказать:\n" + "\n".join(items)
            if remaining > 100:
                answer += f"\nОстаток бюджета: {_format_rub(remaining)}"
            actions = ["Перейти в Закупки", "Скачать CSV"]
        else:
            answer = f"На бюджет {_format_rub(budget)} срочных закупок нет — критичные позиции отсутствуют или не хватает данных о ценах."
            actions = []
        return {"answer": answer, "suggested_actions": actions, "used_products": used_products}

    # What not to order. Must be checked before the general order intent.
    if "не закуп" in msg or "не стоит" in msg or "не нужно" in msg:
        no_order = [p for p, _ in signals if p.do_not_order]
        if no_order:
            lines = [f"• {p.name}" for p in no_order[:10]]
            used_products = [p.name for p in no_order[:10]]
            answer = f"Помечены «не закупать» ({len(no_order)} поз.):\n" + "\n".join(lines)
        else:
            answer = "Нет товаров с флагом «не закупать»."
        return {"answer": answer, "suggested_actions": ["Открыть Риски"], "used_products": used_products}

    # What to order.
    if any(w in msg for w in ["заказ", "закупить", "закупка", "купить", "заканчива"]):
        if not urgent:
            return {"answer": "Срочных закупок нет: все позиции в норме или помечены «не закупать».", "suggested_actions": [], "used_products": []}
        lines = []
        for p, s in urgent[:7]:
            days = s.get("days_left")
            days_txt = f", хватит на {days} дн." if days is not None else ""
            qty = _recommended_qty(p)
            cost_txt = f", примерно {_format_rub(qty * p.purchase_price)}" if p.purchase_price > 0 else ""
            supplier = f", поставщик: {p.supplier}" if p.supplier else ""
            lines.append(f"• {p.name}: заказать {qty} шт. ({s['status']}{days_txt}{cost_txt}{supplier})")
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

    # Why a specific product is at risk.
    if any(w in msg for w in ["почему", "зачем", "попал", "статус"]):
        for p, s in signals:
            if _product_matches_message(p, msg):
                answer = s["recommendation"]
                if s.get("is_manual_risk"):
                    answer = f"[Ручной статус] {answer}"
                used_products.append(p.name)
                return {"answer": answer, "suggested_actions": ["Открыть карточку товара"], "used_products": used_products}
        return {"answer": "Уточните название товара — не нашёл подходящую позицию в данных склада.", "suggested_actions": [], "used_products": []}

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

    # Generic fallback.
    if not products:
        return {"answer": "Данных о товарах нет. Загрузите Excel-файл, чтобы AI мог дать рекомендации.", "suggested_actions": ["Перейти в Импорт"], "used_products": []}
    if not _looks_like_warehouse_question(msg):
        return {
            "answer": (
                "Я пока отвечаю как складской ассистент StoreAI. Лучше всего понимаю вопросы "
                "про товары, остатки, закупки, риски и скидки."
            ),
            "suggested_actions": ["Что заказать?", "Что распродать?", "Риски склада"],
            "used_products": [],
        }
    return {
        "answer": _rule_based_summary(products),
        "suggested_actions": ["Что заказать?", "Риски склада", "Что распродать?"],
        "used_products": [],
    }


def _trim_history(history: list[dict] | None) -> list[dict]:
    """Keep only the last N valid turns so prompts stay small and on-topic."""
    if not history:
        return []
    turns = settings.ai_history_turns
    if turns <= 0:
        return []
    cleaned = [
        {"role": turn["role"], "content": (turn["content"] or "").strip()}
        for turn in history
        if turn.get("role") in {"user", "assistant"} and (turn.get("content") or "").strip()
    ]
    return cleaned[-turns:]


def chat_with_ai(db: Session, message: str, history: list[dict] | None = None) -> dict:
    products = db.query(Product).order_by(Product.updated_at.desc()).limit(120).all()
    context_products = [p for p in products if not p.excluded_from_ai]
    history = _trim_history(history)

    claw_result = call_claw_agent(message, _compact_product_context(context_products), history)
    if claw_result.answer:
        return _with_agent_meta(
            {
                "answer": claw_result.answer,
                "suggested_actions": _actions_from_agent_answer(claw_result.answer),
                "used_products": _products_mentioned_in_answer(claw_result.answer, context_products),
            },
            agent="Claw Code",
            source="claw",
        )

    return _with_agent_meta(_rule_based_chat(message, products), "StoreAI", "rule_based")


def ai_status() -> dict:
    claw = claw_agent_status()
    if claw["available"]:
        active_agent = "Claw Code"
    else:
        active_agent = "StoreAI"
    return {
        "active_agent": active_agent,
        "fallback_agent": "StoreAI",
        "claw": claw,
    }
