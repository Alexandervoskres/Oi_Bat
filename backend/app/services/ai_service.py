from __future__ import annotations

import json
import math
import re
import urllib.request

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Product
from .analytics import product_signal
from .procurement import build_procurement_plan


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
    result = dict(result)
    if "answer" in result:
        result["answer"] = _clean_chat_answer(str(result["answer"]))
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


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else stripped


def _format_json_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [_format_json_value(item) for item in value]
        return "; ".join(part for part in parts if part)
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            rendered = _format_json_value(item)
            if rendered:
                parts.append(f"{key}: {rendered}")
        return "; ".join(parts)
    return str(value)


def _humanize_agent_json(data) -> str | None:
    if isinstance(data, dict):
        for key in ("answer", "response", "message", "summary", "result", "text"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        lines: list[str] = []
        analysis = data.get("analysis")
        if isinstance(analysis, dict):
            budget_status = analysis.get("budget_status") or analysis.get("status")
            if budget_status:
                lines.append(f"Оценка бюджета: {_format_json_value(budget_status)}.")

            reasons = analysis.get("reasons") or analysis.get("risks")
            if isinstance(reasons, list) and reasons:
                lines.append("Почему:")
                for reason in reasons[:5]:
                    if isinstance(reason, dict):
                        category = reason.get("category") or reason.get("title") or reason.get("name")
                        details = reason.get("details") or reason.get("reason") or reason.get("description")
                        if category and details:
                            lines.append(f"• {category}: {_format_json_value(details)}")
                        elif category:
                            lines.append(f"• {_format_json_value(category)}")
                        else:
                            rendered = _format_json_value(reason)
                            if rendered:
                                lines.append(f"• {rendered}")
                    else:
                        rendered = _format_json_value(reason)
                        if rendered:
                            lines.append(f"• {rendered}")

        recommendations = (
            data.get("recommendations")
            or data.get("actions")
            or data.get("next_steps")
            or (analysis.get("recommendations") if isinstance(analysis, dict) else None)
        )
        if isinstance(recommendations, list) and recommendations:
            lines.append("Что сделать:")
            for item in recommendations[:5]:
                rendered = _format_json_value(item)
                if rendered:
                    lines.append(f"• {rendered}")
        elif isinstance(recommendations, str) and recommendations.strip():
            lines.append(f"Что сделать: {recommendations.strip()}")

        if lines:
            return "\n".join(lines)

        compact = _format_json_value(data)
        if compact:
            return f"Я получил структурированный вывод агента. Кратко: {compact}"

    if isinstance(data, list) and data:
        lines = []
        for item in data[:8]:
            rendered = _format_json_value(item)
            if rendered:
                lines.append(f"• {rendered}")
        if lines:
            return "\n".join(lines)

    return None


def _normalize_agent_answer(answer: str) -> str:
    text = (answer or "").strip()
    if not text:
        return text

    candidate = _strip_json_fence(text)
    if candidate.startswith(("{", "[")):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return text
        humanized = _humanize_agent_json(parsed)
        if humanized:
            return _clean_chat_answer(humanized)
    return text


def _clean_chat_answer(answer: str) -> str:
    """Remove model-facing formatting that should not leak into chat bubbles."""
    text = answer or ""
    cleaned_lines: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            if cleaned_lines and cleaned_lines[-1]:
                cleaned_lines.append("")
            continue
        line = re.sub(r"^\s*(?:[•\-*]|\d+[.)])\s+", "", line)
        line = re.sub(r"\s*\([^()]*\)", "", line)
        line = re.sub(r"\s{2,}", " ", line).strip()
        if line:
            cleaned_lines.append(line)

    while cleaned_lines and not cleaned_lines[0]:
        cleaned_lines.pop(0)
    while cleaned_lines and not cleaned_lines[-1]:
        cleaned_lines.pop()
    return "\n".join(cleaned_lines)


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


def _local_knowledge_answer(message: str) -> dict | None:
    msg = message.lower().replace("ё", "е")
    has_sds_plus = "sds plus" in msg or "sds-plus" in msg or "сдс плюс" in msg
    has_sds_max = "sds max" in msg or "sds-max" in msg or "сдс макс" in msg
    asks_difference = any(token in msg for token in ["отлич", "разниц", "чем"])

    if has_sds_plus and has_sds_max and (asks_difference or " vs " in msg or "или" in msg):
        return {
            "answer": (
                "SDS Plus и SDS Max отличаются хвостовиком, мощностью инструмента и задачами.\n"
                "• SDS Plus — легче, обычно для отверстий малого/среднего диаметра и бытового/монтажного перфоратора.\n"
                "• SDS Max — крупнее и прочнее, для тяжёлых перфораторов, буров большого диаметра и демонтажа.\n"
                "Оснастка между ними напрямую не совместима: бур SDS Plus не ставится в SDS Max без переходника."
            ),
            "suggested_actions": [],
            "used_products": [],
        }

    if has_sds_plus and not has_sds_max:
        return {
            "answer": "SDS Plus — распространённый тип хвостовика для лёгких и средних перфораторов. Подходит для бурения бетона и кирпича обычными бурами небольшого/среднего диаметра.",
            "suggested_actions": [],
            "used_products": [],
        }

    if has_sds_max and not has_sds_plus:
        return {
            "answer": "SDS Max — усиленный тип хвостовика для тяжёлых перфораторов и демонтажных работ. Его используют с крупными бурами, коронками и долотами.",
            "suggested_actions": [],
            "used_products": [],
        }

    return None


def _is_low_signal_chatter(message: str) -> bool:
    normalized = re.sub(r"[^a-zа-яё0-9\s]", " ", message.lower()).strip()
    words = re.findall(r"[a-zа-яё0-9]+", normalized)
    if not words or len(words) > 4:
        return False
    if _looks_like_warehouse_question(normalized):
        return False
    chatter_words = {
        "ага",
        "ахаха",
        "бред",
        "вау",
        "да",
        "жесть",
        "класс",
        "ладно",
        "лол",
        "нет",
        "ну",
        "ого",
        "ок",
        "окей",
        "понял",
        "поняла",
        "понятно",
        "супер",
        "угу",
        "ужас",
        "ха",
        "хм",
        "ясно",
        "lol",
        "ogo",
        "ok",
    }
    return any(word in chatter_words for word in words)


def _requires_external_reasoning(message: str) -> bool:
    normalized = re.sub(r"[^a-zа-яё0-9\s]", " ", message.lower()).strip()
    if not normalized:
        return False

    heavy_tokens = [
        "abc",
        "xyz",
        "анализ",
        "артикул",
        "бюджет",
        "выгруз",
        "добав",
        "заказ",
        "закуп",
        "измени",
        "инвентар",
        "комплект",
        "марж",
        "налич",
        "обзор",
        "обнови",
        "остат",
        "отчет",
        "отчёт",
        "подбери",
        "подбор",
        "поставщик",
        "прайс",
        "прогноз",
        "продаж",
        "размести",
        "рекоменд",
        "рассч",
        "риск",
        "склад",
        "создай",
        "составь",
        "списать",
        "спиши",
        "сформируй",
        "товар",
        "удали",
        "цена",
        "ячей",
    ]
    if any(token in normalized for token in heavy_tokens):
        return True

    # Catalog/data lookups are operational even when the user uses a short form.
    if re.search(r"\b(есть ли|сколько|где|найди|покажи|какой остаток|на каком)\b", normalized):
        return True

    return False


def _is_direct_warehouse_command(message: str) -> bool:
    msg = message.lower()
    direct_phrases = [
        "что заказать",
        "что закуп",
        "что не закуп",
        "не закупать",
        "что распрод",
        "распродать",
        "что продать",
        "план на неделю",
        "план недели",
        "риски склада",
        "какие риски",
        "что с рисками",
    ]
    if any(phrase in msg for phrase in direct_phrases):
        return True
    normalized = re.sub(r"[^a-zа-яё0-9\s]", " ", msg)
    return bool(re.search(r"\b(заказ|закупки|риски|распродажа|скидки|план)\b", normalized))


def _is_budget_question(message: str) -> bool:
    msg = message.lower()
    if not any(c.isdigit() for c in msg):
        return False
    if any(token in msg for token in ["бюджет", "₽", "руб", "тыс", "тысяч"]):
        return True
    return bool(re.search(r"\d[\d\s]*(?:к|k)\b", msg))


def _extract_budget(message: str) -> int:
    msg = message.lower()
    digits = re.findall(r"\d[\d\s]*", message)
    try:
        budget = int(re.sub(r"\D", "", digits[0])) if digits else 100_000
    except (ValueError, IndexError):
        budget = 100_000
    if budget < 1000 and re.search(r"\d[\d\s]*(тыс|тысяч|к|k)", msg):
        budget *= 1000
    elif budget < 1000:
        budget *= 1000
    return budget


def _budget_chat_answer(message: str, products: list[Product]) -> dict:
    budget = _extract_budget(message)
    signals = [(p, product_signal(p)) for p in products if not p.excluded_from_ai]
    urgent = [
        (p, s)
        for p, s in signals
        if s["severity"] in {"critical", "warning"} and not p.do_not_order
    ]
    urgent.sort(key=lambda x: (0 if x[1]["severity"] == "critical" else 1, x[1].get("days_left") or 9999))

    if not urgent:
        return {
            "answer": (
                f"{_format_rub(budget)} — нормальный резерв: по текущим данным срочных закупок нет. "
                "Можно держать бюджет на ближайшие риски или направить его на позиции с растущим спросом."
            ),
            "suggested_actions": ["Риски склада", "План на неделю"],
            "used_products": [],
        }

    min_required = 0.0
    priced_urgent = []
    for product, signal in urgent:
        if product.purchase_price > 0:
            min_qty = max(product.min_stock - product.stock, 1)
            min_required += min_qty * product.purchase_price
            priced_urgent.append((product, signal))

    if min_required <= 0:
        return {
            "answer": (
                f"{_format_rub(budget)} оценить сложно: есть срочные позиции, но у них не заполнена закупочная цена. "
                "Заполните закупочные цены, и я посчитаю, хватает ли бюджета."
            ),
            "suggested_actions": ["Открыть Закупки", "Открыть Риски"],
            "used_products": [p.name for p, _ in urgent[:5]],
        }

    coverage = budget / min_required
    if coverage >= 1:
        verdict = "хорошо: бюджета хватает на минимальное закрытие срочных позиций"
    elif coverage >= 0.5:
        verdict = "частично нормально: часть срочных позиций закрыть можно, но запас маленький"
    else:
        verdict = "скорее плохо: бюджета заметно не хватает даже на минимальную срочную закупку"

    remaining = budget
    lines = []
    used_products: list[str] = []
    for product, signal in priced_urgent:
        if remaining < product.purchase_price:
            continue
        qty = min(_recommended_qty(product), int(remaining // product.purchase_price))
        if qty <= 0:
            continue
        cost = qty * product.purchase_price
        days = signal.get("days_left")
        days_text = f", хватит на {days} дн." if days is not None else ""
        lines.append(f"{product.name}: {qty} шт. на {_format_rub(cost)}; {signal['status']}{days_text}")
        used_products.append(product.name)
        remaining -= cost
        if len(lines) >= 5:
            break

    answer = (
        f"{_format_rub(budget)} — {verdict}.\n"
        f"Минимально по текущим срочным позициям нужно примерно {_format_rub(min_required)}."
    )
    if lines:
        answer += "\nЧто можно закрыть сейчас:\n" + "\n".join(lines)
        if remaining > 100:
            answer += f"\nОстаток бюджета: {_format_rub(remaining)}"
    else:
        answer += "\nСейчас этот бюджет не закрывает ни одну срочную позицию с известной закупочной ценой."

    return {
        "answer": answer,
        "suggested_actions": ["Открыть Закупки", "Риски склада"],
        "used_products": used_products,
    }


def _intent_text(message: str) -> str:
    return re.sub(r"\s+", " ", message.lower().replace("ё", "е")).strip()


def _is_no_order_intent(message: str) -> bool:
    msg = _intent_text(message)
    return any(
        token in msg
        for token in [
            "что не закуп",
            "не закупать",
            "не заказывать",
            "не стоит закуп",
            "не стоит покуп",
            "что не покупать",
        ]
    )


def _is_procurement_intent(message: str) -> bool:
    msg = _intent_text(message)
    return any(
        token in msg
        for token in [
            "что заказать",
            "что закупить",
            "кого заказать",
            "закупить",
            "закупка",
            "закупки",
            "план закуп",
            "срочно заказать",
            "заканчивается",
            "заканчива",
        ]
    )


def _is_risk_intent(message: str) -> bool:
    msg = _intent_text(message)
    return any(token in msg for token in ["риски", "риск", "проблем", "опасн", "критич"])


def _is_selloff_intent(message: str) -> bool:
    msg = _intent_text(message)
    return any(token in msg for token in ["распрод", "скид", "залеж", "мертв", "избавиться"])


def _is_week_plan_intent(message: str) -> bool:
    msg = _intent_text(message)
    return "план" in msg and any(token in msg for token in ["недел", "7 дней", "ближайш"])


def _calculated_procurement_answer(products: list[Product]) -> dict:
    plan = build_procurement_plan(p for p in products if not p.excluded_from_ai)
    if not plan:
        return {
            "answer": "Срочных закупок нет: по текущим остаткам, продажам и срокам поставки план пустой.",
            "suggested_actions": ["Открыть Закупки", "Риски склада"],
            "used_products": [],
        }

    total = sum(float(row["total_cost"] or 0) for row in plan)
    critical = sum(1 for row in plan if row["severity"] == "critical")
    warning = sum(1 for row in plan if row["severity"] == "warning")

    lines = []
    for row in plan[:7]:
        days = row.get("days_left")
        days_text = f"; хватит на {days} дн." if days is not None else ""
        cost_text = f"; сумма {_format_rub(row['total_cost'])}" if row.get("total_cost") else ""
        supplier_text = f"; поставщик: {row['supplier']}" if row.get("supplier") else ""
        lines.append(
            f"{row['name']}: заказать {row['recommended_qty']} шт.; "
            f"остаток {row['stock']} шт.; {row['status']}{days_text}{cost_text}{supplier_text}"
        )

    answer = (
        "План закупки рассчитан по остаткам, продажам, минимальному запасу и срокам поставки.\n"
        f"В плане {len(plan)} поз.; критичных {critical}; предупреждений {warning}; сумма примерно {_format_rub(total)}.\n"
        "Сначала закройте:\n"
        + "\n".join(lines)
    )
    if len(plan) > 7:
        answer += f"\nЕще {len(plan) - 7} поз. есть во вкладке закупок."

    return {
        "answer": answer,
        "suggested_actions": ["Открыть Закупки", "Создать заказ"],
        "used_products": [row["name"] for row in plan[:7]],
    }


def _risk_groups(products: list[Product]) -> tuple[list[tuple[Product, dict]], list[tuple[Product, dict]], list[tuple[Product, dict]], list[tuple[Product, dict]]]:
    signals = [(p, product_signal(p)) for p in products if not p.excluded_from_ai]
    critical = [item for item in signals if item[1]["severity"] == "critical"]
    warning = [item for item in signals if item[1]["severity"] == "warning"]
    dead = [item for item in signals if item[1]["status_code"] in {"dead_stock", "discount"}]
    growing = [item for item in signals if item[1]["status_code"] == "growing"]
    critical.sort(key=lambda item: item[1].get("days_left") or 9999)
    warning.sort(key=lambda item: item[1].get("days_left") or 9999)
    dead.sort(key=lambda item: item[1].get("days_without_sales") or 0, reverse=True)
    growing.sort(key=lambda item: item[0].sold_month, reverse=True)
    return critical, warning, dead, growing


def _calculated_risk_answer(products: list[Product]) -> dict:
    critical, warning, dead, _ = _risk_groups(products)
    lines = [
        "Риски рассчитаны по тем же данным, что и вкладка «Риски»: остатки, спрос, сроки поставки и дата последней продажи.",
        f"Критичные: {len(critical)}; предупреждения: {len(warning)}; залежалые или под скидку: {len(dead)}.",
    ]

    used_products: list[str] = []
    focus = (critical + warning + dead)[:7]
    if focus:
        lines.append("Самое важное сейчас:")
        for product, signal in focus:
            days_left = signal.get("days_left")
            days_without_sales = signal.get("days_without_sales")
            tail = ""
            if days_left is not None:
                tail = f"; хватит на {days_left} дн."
            elif days_without_sales is not None:
                tail = f"; без продаж {days_without_sales} дн."
            lines.append(f"{product.name}: {signal['status']}; остаток {product.stock} шт.{tail}")
            used_products.append(product.name)
    else:
        lines.append("Серьезных рисков сейчас нет.")

    return {
        "answer": "\n".join(lines),
        "suggested_actions": ["Открыть Риски", "Открыть Закупки"],
        "used_products": used_products,
    }


def _calculated_specific_risk_answer(message: str, products: list[Product]) -> dict | None:
    msg = _intent_text(message)
    if not any(token in msg for token in ["почему", "зачем", "попал", "статус"]):
        return None

    for product in products:
        if product.excluded_from_ai:
            continue
        if not _product_matches_message(product, msg):
            continue
        signal = product_signal(product)
        answer = signal["recommendation"]
        if signal.get("is_manual_risk"):
            answer = f"Ручной статус: {answer}"
        return {
            "answer": answer,
            "suggested_actions": ["Открыть карточку товара", "Открыть Риски"],
            "used_products": [product.name],
        }

    return {
        "answer": "Уточните название товара — не нашел подходящую позицию в данных склада.",
        "suggested_actions": ["Открыть Риски"],
        "used_products": [],
    }


def _calculated_selloff_answer(products: list[Product]) -> dict:
    _, _, dead, _ = _risk_groups(products)
    if not dead:
        return {
            "answer": "Нет товаров с признаками мертвого груза или слабых продаж. Распродажу сейчас можно не запускать.",
            "suggested_actions": ["Открыть Риски"],
            "used_products": [],
        }

    lines = []
    used_products: list[str] = []
    for product, signal in dead[:7]:
        days = signal.get("days_without_sales")
        days_text = f"; без продаж {days} дн." if days is not None else ""
        lines.append(f"{product.name}: остаток {product.stock} шт.; {signal['status']}{days_text}")
        used_products.append(product.name)

    return {
        "answer": "Рекомендую распродать или дать скидку:\n" + "\n".join(lines),
        "suggested_actions": ["Открыть Риски", "Сделать скидку"],
        "used_products": used_products,
    }


def _calculated_no_order_answer(products: list[Product]) -> dict:
    _, _, dead, _ = _risk_groups(products)
    no_order = [p for p in products if not p.excluded_from_ai and p.do_not_order]
    used_products: list[str] = []

    if no_order:
        lines = []
        for product in no_order[:10]:
            reason = product.risk_note.strip() if product.risk_note else "помечен вручную как «не закупать»"
            lines.append(f"{product.name}: {reason}; остаток {product.stock} шт.")
            used_products.append(product.name)
        answer = "Не закупать сейчас:\n" + "\n".join(lines)
    elif dead:
        lines = []
        for product, signal in dead[:7]:
            lines.append(f"{product.name}: {signal['status']}; остаток {product.stock} шт.")
            used_products.append(product.name)
        answer = "Явных запретов нет, но эти позиции лучше не докупать без проверки спроса:\n" + "\n".join(lines)
    else:
        answer = "Явных товаров «не закупать» сейчас нет. Для запрета нужны слабые продажи, ручная пометка или риск залеживания."

    return {
        "answer": answer,
        "suggested_actions": ["Открыть Риски"],
        "used_products": used_products,
    }


def _calculated_week_plan_answer(products: list[Product]) -> dict:
    procurement = build_procurement_plan(p for p in products if not p.excluded_from_ai)
    _, _, dead, growing = _risk_groups(products)
    actions = []
    used_products: list[str] = []

    for row in procurement[:5]:
        actions.append(f"Закупить: {row['name']} — {row['recommended_qty']} шт.; {row['status']}")
        used_products.append(row["name"])
    for product, signal in dead[:3]:
        actions.append(f"Скидка или ревизия: {product.name} — {signal['status']}")
        used_products.append(product.name)
    for product, _ in growing[:2]:
        actions.append(f"Усилить запас: {product.name} — спрос выше среднего")
        used_products.append(product.name)

    if actions:
        answer = "Приоритетный план на неделю по расчетам склада:\n" + "\n".join(actions)
    else:
        answer = "Приоритетный план на неделю спокойный: срочных закупок и рисков по текущим данным нет."

    return {
        "answer": answer,
        "suggested_actions": ["Открыть Закупки", "Открыть Риски"],
        "used_products": list(dict.fromkeys(used_products))[:10],
    }


def _calculated_warehouse_answer(message: str, products: list[Product]) -> dict | None:
    if _is_no_order_intent(message):
        return _calculated_no_order_answer(products)
    if _is_week_plan_intent(message):
        return _calculated_week_plan_answer(products)
    if _is_selloff_intent(message):
        return _calculated_selloff_answer(products)
    if _is_risk_intent(message):
        specific_risk = _calculated_specific_risk_answer(message, products)
        if specific_risk:
            return specific_risk
        return _calculated_risk_answer(products)
    if _is_procurement_intent(message):
        return _calculated_procurement_answer(products)
    return None


def _fast_local_chat(message: str, products: list[Product]) -> dict | None:
    knowledge = _local_knowledge_answer(message)
    if knowledge:
        return knowledge

    if _is_budget_question(message):
        return _budget_chat_answer(message, products)

    calculated = _calculated_warehouse_answer(message, products)
    if calculated:
        return calculated

    if _is_direct_warehouse_command(message):
        return _rule_based_chat(message, products)

    if (
        _is_greeting(message)
        or _is_thanks(message)
        or _is_capabilities_question(message)
        or _is_weather_question(message)
        or _is_low_signal_chatter(message)
    ):
        return _rule_based_chat(message, products)

    if not _requires_external_reasoning(message):
        return {
            "answer": "Понял. Если нужен склад — спросите про остатки, закупки, риски, продажи или отчёт.",
            "suggested_actions": ["Что заказать?", "Риски склада", "Что распродать?"],
            "used_products": [],
        }

    return None


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

    if _is_low_signal_chatter(msg):
        return {
            "answer": "Понял. Чем помочь по складу: закупки, остатки, риски или продажи?",
            "suggested_actions": ["Что заказать?", "Риски склада", "Что распродать?"],
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
                    supplier_text = f"; поставщик: {p.supplier}" if p.supplier else ""
                    items.append(f"{p.name}: {qty} шт. на {_format_rub(cost)}{supplier_text}")
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
            lines = []
            for p in no_order[:10]:
                reason = p.risk_note.strip() if p.risk_note else "помечен вручную как «не закупать»"
                lines.append(f"{p.name}: {reason}")
            used_products = [p.name for p in no_order[:10]]
            answer = "Не закупать сейчас:\n" + "\n".join(lines)
        elif dead:
            lines = []
            for p, s in dead[:7]:
                reason = "залежался" if s["status_code"] == "dead_stock" else "слабые продажи, лучше проверить цену"
                lines.append(f"{p.name}: {reason}; остаток {p.stock} шт.")
                used_products.append(p.name)
            answer = "Явных запретов нет, но эти позиции лучше не докупать без проверки спроса:\n" + "\n".join(lines)
        else:
            answer = (
                "Явных товаров «не закупать» сейчас нет. "
                "Нулевой остаток сам по себе не причина запрещать закупку: сначала смотрим продажи, маржу и срок поставки."
            )
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
            details = "; ".join(part for part in [s["status"] + days_txt, cost_txt.lstrip(", "), supplier.lstrip(", ")] if part)
            lines.append(f"{p.name}: заказать {qty} шт.; {details}")
            used_products.append(p.name)
        answer = f"К срочному заказу: {len(urgent)} поз.\n" + "\n".join(lines)
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
            lines.append(f"{p.name}: {p.stock} шт. на складе{txt}")
            used_products.append(p.name)
        answer = f"Рекомендую распродать или дать скидку: {len(dead)} поз.\n" + "\n".join(lines)
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
            f"Критичных нет или заканчивается: {n_crit}",
            f"Предупреждений: {n_warn}",
            f"Залежавшихся: {len(dead)}",
        ]
        if urgent:
            lines.append("\nСамые срочные:")
            for p, s in urgent[:4]:
                lines.append(f"{p.name}: {s['status']}")
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
            answer = "Приоритетный план на неделю:\n" + "\n".join(actions)
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

    fast_answer = _fast_local_chat(message, products)
    if fast_answer:
        return _with_agent_meta(fast_answer, "StoreAI", "rule_based")

    if _ollama_available():
        try:
            raw = _ollama_chat(build_model_prompt(message, _compact_product_context(context_products), history))
        except Exception:
            raw = ""
        if raw:
            agent_answer = _clean_chat_answer(_normalize_agent_answer(raw))
            return _with_agent_meta(
                {
                    "answer": agent_answer,
                    "suggested_actions": _actions_from_agent_answer(agent_answer),
                    "used_products": _products_mentioned_in_answer(agent_answer, context_products),
                },
                "Локальная модель",
                "ollama",
            )

    return _with_agent_meta(_rule_based_chat(message, products), "StoreAI", "rule_based")


def _format_history(history: list[dict] | None) -> str:
    if not history:
        return ""
    lines = []
    for turn in history:
        role = "Пользователь" if turn.get("role") == "user" else "Ассистент"
        content = (turn.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    if not lines:
        return ""
    return "Предыдущий диалог (для контекста уточняющих вопросов):\n" + "\n".join(lines) + "\n\n"


def build_model_prompt(message: str, warehouse_context: list[dict], history: list[dict] | None = None) -> str:
    """Build the single-prompt instruction sent to the local model.

    `/no_think` disables qwen3-style chain-of-thought: it roughly halves latency
    and stops the model wandering off-task. Harmless for models that ignore it.
    """
    no_think = "\n\n/no_think" if settings.ai_no_think else ""
    return (
        "Ты AI-ассистент склада строительных инструментов в приложении СкладAI.\n"
        "Отвечай владельцу склада на русском языке.\n"
        "Используй только JSON-контекст склада ниже: не выдумывай товары, цены, остатки или поставщиков.\n"
        "Отвечай кратко, практично, списками и цифрами. Если данных не хватает, честно скажи каких.\n\n"
        "Не возвращай JSON, YAML, Markdown-таблицы или служебные поля. Пользователь должен увидеть готовый человеческий ответ.\n\n"
        f"Контекст склада JSON:\n{json.dumps(warehouse_context, ensure_ascii=False, separators=(',', ':'))}\n\n"
        f"{_format_history(history)}"
        f"Текущий вопрос пользователя:\n{message}"
        f"{no_think}"
    )


def _ollama_available() -> bool:
    return bool(settings.ollama_host and settings.ai_model)


def _ollama_chat(prompt: str) -> str:
    """Non-streaming Ollama chat: returns the full answer text."""
    url = settings.ollama_host.rstrip("/") + "/api/chat"
    payload = {
        "model": settings.ai_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": settings.ai_num_predict},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=max(10, settings.ai_timeout_seconds)) as response:
        data = json.loads(response.read().decode("utf-8", errors="replace"))
    return (data.get("message") or {}).get("content", "")


def _ollama_chat_stream(prompt: str):
    """Yield content deltas from Ollama's /api/chat streaming response.

    The prompt already carries /no_think when enabled, so we don't pass the
    think flag (keeps it model-agnostic).
    """
    url = settings.ollama_host.rstrip("/") + "/api/chat"
    payload = {
        "model": settings.ai_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "options": {"num_predict": settings.ai_num_predict},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=max(10, settings.ai_timeout_seconds)) as response:
        for raw in response:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            chunk = (obj.get("message") or {}).get("content", "")
            if chunk:
                yield chunk
            if obj.get("done"):
                break


def chat_stream(db: Session, message: str, history: list[dict] | None = None):
    """Generator of SSE-ready events: {'type':'delta','text':..} then
    {'type':'done', answer/agent/source/suggested_actions/used_products}.

    Fast local answers are emitted as a single delta. Otherwise tokens stream
    live from Ollama; if Ollama is unreachable we fall back to the rule-based
    path and emit it as one delta.
    """
    products = db.query(Product).order_by(Product.updated_at.desc()).limit(120).all()
    context_products = [p for p in products if not p.excluded_from_ai]
    history = _trim_history(history)

    fast_answer = _fast_local_chat(message, products)
    if fast_answer:
        result = _with_agent_meta(fast_answer, "StoreAI", "rule_based")
        yield {"type": "delta", "text": result["answer"]}
        yield {"type": "done", **result}
        return

    if _ollama_available():
        prompt = build_model_prompt(message, _compact_product_context(context_products), history)
        collected: list[str] = []
        try:
            for chunk in _ollama_chat_stream(prompt):
                collected.append(chunk)
                yield {"type": "delta", "text": chunk}
        except Exception:
            collected = []  # connection failed mid-stream -> fall back below
        if collected:
            answer = _clean_chat_answer(_normalize_agent_answer("".join(collected)))
            done = _with_agent_meta(
                {
                    "answer": answer,
                    "suggested_actions": _actions_from_agent_answer(answer),
                    "used_products": _products_mentioned_in_answer(answer, context_products),
                },
                "Локальная модель",
                "ollama",
            )
            # The streamed deltas were raw tokens; tell the client to replace
            # the bubble with the cleaned final answer.
            yield {"type": "done", "replace": True, **done}
            return

    # Fallback when Ollama is unreachable: buffered non-streaming path / rules.
    result = chat_with_ai(db, message, history)
    yield {"type": "delta", "text": result["answer"]}
    yield {"type": "done", "replace": True, **result}


def ai_status() -> dict:
    available = _ollama_available()
    return {
        "active_agent": "Локальная модель" if available else "StoreAI",
        "fallback_agent": "StoreAI",
        "ollama": {
            "available": available,
            "host": settings.ollama_host,
            "model": settings.ai_model,
        },
    }
