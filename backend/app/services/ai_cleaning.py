from __future__ import annotations

# ───────────────────────────────────────────────────────────────────────────
# ОЧИСТКА ОТВЕТА МОДЕЛИ
# Локальная нейросеть (qwen3) часто отвечает «по-машинному»: JSON, Markdown,
# маркированные списки, технические поля. Этот модуль превращает такой вывод
# в человеческий текст для пузыря чата. Зовётся из ai_service.py (оркестратор).
# ───────────────────────────────────────────────────────────────────────────

import json
import re


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

