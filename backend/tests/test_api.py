from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

import pandas as pd

fd, db_path = tempfile.mkstemp(prefix="storeai-test-", suffix=".db")
os.close(fd)
os.environ["DATABASE_URL"] = f"sqlite:///{Path(db_path).as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DEFAULT_ADMIN_USERNAME"] = "admin"
os.environ["DEFAULT_ADMIN_PASSWORD"] = "admin123"

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402


def _login(client: TestClient, username: str = "admin", password: str = "admin123") -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _xlsx_bytes(rows: list[dict]) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False)
    output.seek(0)
    return output.getvalue()


def test_login_and_empty_dashboard():
    with TestClient(app) as client:
        headers = _login(client)
        response = client.get("/api/dashboard", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["products"] >= 0
    assert "ai_summary" in payload


def test_excel_upload_creates_products_and_returns_warnings():
    with TestClient(app) as client:
        headers = _login(client)
        content = _xlsx_bytes(
            [
                {
                    "Артикул": "",
                    "Название товара": "Перфоратор тестовый",
                    "Категория": "Дрели",
                    "Остаток": "bad-number",
                    "Продано за месяц": 4,
                    "Средние продажи в месяц": "7,5",
                    "Закупочная цена": 1000,
                    "Продажная цена": 1500,
                    "Дата последней продажи": "10.06.2026",
                    "Минимальный остаток": 2,
                    "Срок поставки": 5,
                }
            ]
        )
        response = client.post(
            "/api/imports/upload",
            headers=headers,
            files={
                "file": (
                    "products.xlsx",
                    content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        products = client.get("/api/products", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["imported"] == 1
    assert payload["created"] == 1
    assert payload["warnings"]
    assert products.status_code == 200
    assert any(item["name"] == "Перфоратор тестовый" for item in products.json())


def test_buyer_cannot_upload_excel():
    with TestClient(app) as client:
        admin_headers = _login(client)
        create = client.post(
            "/api/users",
            headers=admin_headers,
            json={
                "username": "buyer_smoke",
                "full_name": "Buyer Smoke",
                "password": "buyer123",
                "role": "buyer",
            },
        )
        assert create.status_code in {201, 409}
        buyer_headers = _login(client, "buyer_smoke", "buyer123")
        response = client.post(
            "/api/imports/upload",
            headers=buyer_headers,
            files={"file": ("products.xlsx", _xlsx_bytes([]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

    assert response.status_code == 403


def test_risk_pdf_download():
    with TestClient(app) as client:
        headers = _login(client)
        response = client.get("/api/reports/risk.pdf", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF")


def _ensure_buyer(client: TestClient, admin_headers: dict[str, str]) -> dict[str, str]:
    client.post(
        "/api/users",
        headers=admin_headers,
        json={"username": "buyer_edit", "full_name": "Buyer Edit", "password": "buyer123", "role": "buyer"},
    )
    return _login(client, "buyer_edit", "buyer123")


def _ensure_manager(client: TestClient, admin_headers: dict[str, str]) -> dict[str, str]:
    client.post(
        "/api/users",
        headers=admin_headers,
        json={"username": "manager_edit", "full_name": "Manager Edit", "password": "manager123", "role": "manager"},
    )
    return _login(client, "manager_edit", "manager123")


def _create_product(client: TestClient, headers: dict[str, str], sku: str, **overrides) -> dict:
    payload = {"sku": sku, "name": f"Товар {sku}", "stock": 10, "sold_month": 5}
    payload.update(overrides)
    response = client.post("/api/products", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_product_and_get():
    with TestClient(app) as client:
        headers = _login(client)
        created = _create_product(client, headers, "MANUAL-001", name="Ручной товар", purchase_price=500)
        fetched = client.get(f"/api/products/{created['id']}", headers=headers)

    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Ручной товар"
    assert fetched.json()["sku"] == "MANUAL-001"


def test_buyer_cannot_create_or_edit_product():
    with TestClient(app) as client:
        admin_headers = _login(client)
        target = _create_product(client, admin_headers, "BUYER-RO-1")
        buyer_headers = _ensure_buyer(client, admin_headers)

        create = client.post(
            "/api/products",
            headers=buyer_headers,
            json={"sku": "BUYER-NEW", "name": "Запрещено"},
        )
        patch = client.patch(
            f"/api/products/{target['id']}",
            headers=buyer_headers,
            json={"name": "Изменено"},
        )

    assert create.status_code == 403
    assert patch.status_code == 403


def test_update_product_fields():
    with TestClient(app) as client:
        headers = _login(client)
        created = _create_product(client, headers, "UPD-001")
        response = client.patch(
            f"/api/products/{created['id']}",
            headers=headers,
            json={"name": "Новое имя", "stock": 99},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Новое имя"
    assert body["stock"] == 99


def test_delete_product_admin_only():
    with TestClient(app) as client:
        admin_headers = _login(client)
        manager_headers = _ensure_manager(client, admin_headers)
        target = _create_product(client, admin_headers, "DEL-001")

        manager_delete = client.delete(f"/api/products/{target['id']}", headers=manager_headers)
        admin_delete = client.delete(f"/api/products/{target['id']}", headers=admin_headers)
        gone = client.get(f"/api/products/{target['id']}", headers=admin_headers)

    assert manager_delete.status_code == 403
    assert admin_delete.status_code == 204
    assert gone.status_code == 404


def test_risk_override_replaces_auto_signal():
    with TestClient(app) as client:
        headers = _login(client)
        # Healthy product: plenty of stock, steady sales -> auto status "Норма".
        created = _create_product(client, headers, "RISK-001", stock=100, sold_month=2, min_stock=5)
        risk = client.patch(
            f"/api/products/{created['id']}/risk",
            headers=headers,
            json={"risk_status_override": "order_now", "risk_priority": "high", "risk_note": "Поставщик предупредил о дефиците"},
        )
        listing = client.get("/api/products?search=RISK-001", headers=headers)

    assert risk.status_code == 200
    assert risk.json()["status"] == "Срочно заказать"
    assert risk.json()["is_manual_risk"] is True
    row = next(item for item in listing.json() if item["sku"] == "RISK-001")
    assert row["status"] == "Срочно заказать"
    assert row["recommendation"] == "Поставщик предупредил о дефиците"

    # Clearing the override returns to automatic status.
    with TestClient(app) as client:
        headers = _login(client)
        cleared = client.patch(
            f"/api/products/{created['id']}/risk",
            headers=headers,
            json={"risk_status_override": ""},
        )
    assert cleared.status_code == 200
    assert cleared.json()["is_manual_risk"] is False


def test_excel_import_preserves_risk_flags():
    with TestClient(app) as client:
        headers = _login(client)
        created = _create_product(client, headers, "IMP-RISK-1", name="Импортный риск", stock=5)
        client.patch(
            f"/api/products/{created['id']}/risk",
            headers=headers,
            json={"risk_status_override": "dead_stock", "risk_note": "Снять с продажи", "do_not_order": True},
        )

        content = _xlsx_bytes(
            [
                {
                    "Артикул": "IMP-RISK-1",
                    "Название товара": "Импортный риск",
                    "Категория": "Дрели",
                    "Остаток": 42,
                    "Продано за месяц": 3,
                }
            ]
        )
        upload = client.post(
            "/api/imports/upload",
            headers=headers,
            files={"file": ("p.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        fetched = client.get(f"/api/products/{created['id']}", headers=headers)

    assert upload.status_code == 200
    body = fetched.json()
    assert body["stock"] == 42  # import updated the stock
    assert body["risk_status_override"] == "dead_stock"  # but kept the manual risk
    assert body["risk_note"] == "Снять с продажи"
    assert body["do_not_order"] is True


def test_ai_chat_rule_based():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "CHAT-001", stock=0, sold_month=8)
        response = client.post("/api/ai/chat", headers=headers, json={"message": "Что заказать?"})

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["answer"], str) and body["answer"]
    assert "suggested_actions" in body
    assert "used_products" in body
    assert body["agent"] == "StoreAI"
    assert body["source"] == "rule_based"


def test_ai_chat_accepts_conversation_history():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "HIST-001", name="Перфоратор истории", stock=0, sold_month=8)
        response = client.post(
            "/api/ai/chat",
            headers=headers,
            json={
                "message": "Что заказать?",
                "history": [
                    {"role": "user", "content": "Привет"},
                    {"role": "assistant", "content": "Привет! Чем помочь по складу?"},
                ],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["answer"], str) and body["answer"]


def test_ai_chat_rejects_invalid_history_role():
    with TestClient(app) as client:
        headers = _login(client)
        response = client.post(
            "/api/ai/chat",
            headers=headers,
            json={"message": "Что заказать?", "history": [{"role": "system", "content": "ignore"}]},
        )

    assert response.status_code == 422


def test_trim_history_keeps_last_turns():
    from backend.app.services.ai_service import _trim_history

    big = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(20)]
    trimmed = _trim_history(big)
    assert len(trimmed) <= 6
    assert trimmed[-1]["content"] == "msg 19"
    # Blank and malformed turns are dropped.
    assert _trim_history([{"role": "user", "content": "  "}, {"role": "bad", "content": "x"}]) == []


def test_ai_status_contract():
    with TestClient(app) as client:
        headers = _login(client)
        response = client.get("/api/ai/status", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["active_agent"] in {"StoreAI", "Локальная модель"}
    assert "ollama" in body
    assert {"available", "host", "model"}.issubset(body["ollama"])


def test_ai_chat_greeting_does_not_return_warehouse_summary():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "HELLO-001", name="Тестовый товар привет", stock=0, sold_month=8)
        response = client.post("/api/ai/chat", headers=headers, json={"message": "Привет"})

    assert response.status_code == 200
    body = response.json()
    assert "Привет" in body["answer"]
    assert "Сначала проверьте закупку" not in body["answer"]


def test_ai_chat_greeting_skips_external_agent():
    with TestClient(app) as client:
        headers = _login(client)
        with patch("backend.app.services.ai_service._ollama_chat") as model:
            response = client.post("/api/ai/chat", headers=headers, json={"message": "Привет"})

    assert response.status_code == 200
    assert response.json()["source"] == "rule_based"
    model.assert_not_called()


def test_ai_chat_low_signal_chatter_skips_external_agent():
    with TestClient(app) as client:
        headers = _login(client)
        with patch("backend.app.services.ai_service._ollama_chat") as model:
            response = client.post("/api/ai/chat", headers=headers, json={"message": "Ого"})

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "rule_based"
    assert "Чем помочь" in body["answer"]
    model.assert_not_called()


def test_ai_chat_simple_non_operational_question_skips_external_agent():
    with TestClient(app) as client:
        headers = _login(client)
        with patch("backend.app.services.ai_service._ollama_chat") as model:
            response = client.post("/api/ai/chat", headers=headers, json={"message": "Как дела?"})

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "rule_based"
    assert "Если нужен склад" in body["answer"]
    model.assert_not_called()


def test_ai_chat_local_knowledge_skips_external_agent():
    with TestClient(app) as client:
        headers = _login(client)
        with patch("backend.app.services.ai_service._ollama_chat") as model:
            response = client.post(
                "/api/ai/chat",
                headers=headers,
                json={"message": "Чем отличается SDS Plus от SDS Max?"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "rule_based"
    assert "SDS Plus" in body["answer"]
    assert "SDS Max" in body["answer"]
    model.assert_not_called()


def test_ai_chat_budget_question_uses_fast_local_answer():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "BUDGET-FAST", name="Бюджетный тест", stock=0, min_stock=5, purchase_price=3000, sold_month=4)
        with patch("backend.app.services.ai_service._ollama_chat") as model:
            response = client.post("/api/ai/chat", headers=headers, json={"message": "бюджет 10 тысяч это хорошо или плохо?"})

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "rule_based"
    assert "10 000" in body["answer"]
    assert not body["answer"].lstrip().startswith("{")
    model.assert_not_called()


def test_ai_chat_week_plan_uses_local_warehouse_rules():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "PLAN-FAST", name="Плановый товар", stock=0, min_stock=4, purchase_price=1200, sold_month=6)
        with patch("backend.app.services.ai_service._ollama_chat") as model:
            response = client.post("/api/ai/chat", headers=headers, json={"message": "План на неделю"})

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "rule_based"
    assert "Приоритетный план" in body["answer"]
    assert "Плановый товар" in body["answer"]
    assert "Если нужен склад" not in body["answer"]
    assert "1." not in body["answer"]
    model.assert_not_called()


def test_ai_chat_selloff_uses_local_warehouse_rules():
    with TestClient(app) as client:
        headers = _login(client)
        created = _create_product(client, headers, "SELL-FAST", name="Распродажный товар", stock=12, sold_month=0)
        client.patch(f"/api/products/{created['id']}/risk", headers=headers, json={"risk_status_override": "dead_stock"})
        with patch("backend.app.services.ai_service._ollama_chat") as model:
            response = client.post("/api/ai/chat", headers=headers, json={"message": "Что распродать?"})

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "rule_based"
    assert "Рекомендую распродать" in body["answer"]
    assert "Распродажный товар" in body["answer"]
    assert "Если нужен склад" not in body["answer"]
    model.assert_not_called()


def test_ai_chat_risks_use_local_calculated_answer():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "RISK-FAST", name="Рискованный товар", stock=0, min_stock=4, sold_month=6)
        with patch("backend.app.services.ai_service._ollama_chat") as model:
            response = client.post("/api/ai/chat", headers=headers, json={"message": "Какие риски на складе?"})

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "rule_based"
    assert "Критичные" in body["answer"]
    assert "Рискованный товар" in body["answer"]
    model.assert_not_called()


def test_ai_chat_weather_question_is_not_warehouse_summary():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "WEATHER-001", name="Товар для погоды", stock=0, sold_month=8)
        response = client.post("/api/ai/chat", headers=headers, json={"message": "Какая погода?"})

    assert response.status_code == 200
    body = response.json()
    assert "погод" in body["answer"].lower()
    assert "Сначала проверьте закупку" not in body["answer"]
    assert "claw" not in body["answer"].lower()
    assert "claw.exe" not in (body.get("agent_status") or "").lower()


def test_ai_chat_no_order_branch_has_priority():
    with TestClient(app) as client:
        headers = _login(client)
        created = _create_product(client, headers, "CHAT-NO-ORDER", name="Не закупать тест", stock=0, sold_month=8)
        client.patch(f"/api/products/{created['id']}/risk", headers=headers, json={"do_not_order": True})
        with patch("backend.app.services.ai_service._ollama_chat") as model:
            response = client.post("/api/ai/chat", headers=headers, json={"message": "Что не закупать?"})

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "rule_based"
    assert "Не закупать тест" in body["answer"]
    assert "Не закупать тест" in body["used_products"]
    assert "(" not in body["answer"]
    assert "severity" not in body["answer"]
    assert "•" not in body["answer"]
    model.assert_not_called()


def test_ai_chat_finds_product_by_partial_name():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "CHAT-PARTIAL", name="Перфоратор Bosch GBH", stock=0, sold_month=8)
        response = client.post("/api/ai/chat", headers=headers, json={"message": "Почему перфоратор в рисках?"})

    assert response.status_code == 200
    body = response.json()
    assert body["used_products"] == ["Перфоратор Bosch GBH"]
    assert "Уточните название" not in body["answer"]


def test_dashboard_uses_manual_risk_status():
    with TestClient(app) as client:
        headers = _login(client)
        created = _create_product(client, headers, "DASH-001", name="Дашборд риск", stock=100, sold_month=1, min_stock=5)
        client.patch(
            f"/api/products/{created['id']}/risk",
            headers=headers,
            json={"risk_status_override": "out_of_stock"},
        )
        dashboard = client.get("/api/dashboard", headers=headers)

    assert dashboard.status_code == 200
    urgent_names = [item["name"] for item in dashboard.json()["urgent_actions"]]
    assert "Дашборд риск" in urgent_names


# ─── Stock movements ──────────────────────────────────────────────────────────


def test_movement_receipt_increases_stock():
    with TestClient(app) as client:
        headers = _login(client)
        created = _create_product(client, headers, "MOV-001", stock=10)
        response = client.post(
            f"/api/products/{created['id']}/movements",
            headers=headers,
            json={"movement_type": "receipt", "quantity": 5, "note": "Поставка"},
        )
        product = client.get(f"/api/products/{created['id']}", headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["quantity"] == 5
    assert body["stock_before"] == 10
    assert body["stock_after"] == 15
    assert product.json()["stock"] == 15


def test_movement_sale_decreases_stock_and_lists():
    with TestClient(app) as client:
        headers = _login(client)
        created = _create_product(client, headers, "MOV-002", stock=10)
        client.post(
            f"/api/products/{created['id']}/movements",
            headers=headers,
            json={"movement_type": "sale", "quantity": 3},
        )
        movements = client.get(f"/api/products/{created['id']}/movements", headers=headers)

    assert movements.status_code == 200
    rows = movements.json()
    assert len(rows) == 1
    assert rows[0]["movement_type"] == "sale"
    assert rows[0]["quantity"] == -3
    assert rows[0]["stock_after"] == 7


def test_movement_cannot_drive_stock_negative():
    with TestClient(app) as client:
        headers = _login(client)
        created = _create_product(client, headers, "MOV-003", stock=2)
        response = client.post(
            f"/api/products/{created['id']}/movements",
            headers=headers,
            json={"movement_type": "write_off", "quantity": 5},
        )
        product = client.get(f"/api/products/{created['id']}", headers=headers)

    assert response.status_code == 400
    assert product.json()["stock"] == 2  # unchanged


def test_movement_adjustment_allows_negative():
    with TestClient(app) as client:
        headers = _login(client)
        created = _create_product(client, headers, "MOV-004", stock=10)
        response = client.post(
            f"/api/products/{created['id']}/movements",
            headers=headers,
            json={"movement_type": "adjustment", "quantity": -4, "note": "Пересчёт"},
        )

    assert response.status_code == 201
    assert response.json()["stock_after"] == 6


def test_buyer_cannot_create_movement():
    with TestClient(app) as client:
        admin_headers = _login(client)
        created = _create_product(client, admin_headers, "MOV-005", stock=10)
        buyer_headers = _ensure_buyer(client, admin_headers)
        response = client.post(
            f"/api/products/{created['id']}/movements",
            headers=buyer_headers,
            json={"movement_type": "receipt", "quantity": 1},
        )

    assert response.status_code == 403


# ─── Audit log ────────────────────────────────────────────────────────────────


def test_audit_records_product_lifecycle():
    with TestClient(app) as client:
        headers = _login(client)
        created = _create_product(client, headers, "AUD-001", name="Аудит товар", stock=5)
        client.post(
            f"/api/products/{created['id']}/movements",
            headers=headers,
            json={"movement_type": "receipt", "quantity": 2},
        )
        audit = client.get("/api/audit", headers=headers)

    assert audit.status_code == 200
    actions = [row["action"] for row in audit.json()]
    assert "product.create" in actions
    assert "stock.movement" in actions


def test_audit_admin_only():
    with TestClient(app) as client:
        admin_headers = _login(client)
        buyer_headers = _ensure_buyer(client, admin_headers)
        response = client.get("/api/audit", headers=buyer_headers)

    assert response.status_code == 403


def test_audit_filter_by_action():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "AUD-FILTER-1", stock=1)
        response = client.get("/api/audit?action=product.create", headers=headers)

    assert response.status_code == 200
    assert response.json()
    assert all(row["action"] == "product.create" for row in response.json())


# ─── AI model path (direct Ollama) and rule-based fallback ────────────────────

# Tests patch _ollama_available + _ollama_chat so they never touch a real model.
_OLLAMA_OK = "backend.app.services.ai_service._ollama_available"
_OLLAMA_CHAT = "backend.app.services.ai_service._ollama_chat"


def test_chat_uses_model_when_available():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "MODEL-1", name="Модельный товар", stock=0, sold_month=5)
        with patch(_OLLAMA_OK, return_value=True), patch(
            _OLLAMA_CHAT, return_value="Ответ модели: закажите Модельный товар"
        ):
            response = client.post("/api/ai/chat", headers=headers, json={"message": "обзор"})

    body = response.json()
    assert body["source"] == "ollama"
    assert body["agent"] == "Локальная модель"
    assert "Модельный товар" in body["used_products"]


def test_chat_humanizes_json_answer_from_model():
    raw_json = (
        '{"analysis":{"budget_status":"Недостаточно",'
        '"reasons":[{"category":"Товары с нулевым остатком","details":"Нужно закрыть срочную закупку"}]},'
        '"recommendations":["Увеличить бюджет или выбрать самые критичные позиции"]}'
    )
    with TestClient(app) as client:
        headers = _login(client)
        with patch(_OLLAMA_OK, return_value=True), patch(_OLLAMA_CHAT, return_value=raw_json):
            response = client.post("/api/ai/chat", headers=headers, json={"message": "обзор бюджета"})

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "ollama"
    assert not body["answer"].lstrip().startswith("{")
    assert "budget_status" not in body["answer"]
    assert "Оценка бюджета" in body["answer"]
    assert "Недостаточно" in body["answer"]


def test_chat_cleans_model_technical_parentheses_and_markers():
    raw_answer = '• Шуруповёрт (статус: "Нет в наличии", severity: "critical", остаток: 0).\n1. Перфоратор (остаток: 0).'
    with TestClient(app) as client:
        headers = _login(client)
        with patch(_OLLAMA_OK, return_value=True), patch(_OLLAMA_CHAT, return_value=raw_answer):
            response = client.post("/api/ai/chat", headers=headers, json={"message": "обзор"})

    assert response.status_code == 200
    body = response.json()
    assert "Шуруповёрт" in body["answer"]
    assert "Перфоратор" in body["answer"]
    assert "(" not in body["answer"]
    assert "severity" not in body["answer"]
    assert "•" not in body["answer"]
    assert "1." not in body["answer"]


def test_chat_excludes_flagged_products_from_model_context():
    captured: dict = {}

    def fake_ollama(prompt):
        captured["prompt"] = prompt
        return "ok"

    with TestClient(app) as client:
        headers = _login(client)
        visible = _create_product(client, headers, "AG-VISIBLE", name="Виден агенту", stock=1)
        hidden = _create_product(client, headers, "AG-HIDDEN", name="Скрыт от агента", stock=1)
        client.patch(f"/api/products/{hidden['id']}/risk", headers=headers, json={"excluded_from_ai": True})
        with patch(_OLLAMA_OK, return_value=True), patch(_OLLAMA_CHAT, side_effect=fake_ollama):
            response = client.post(
                "/api/ai/chat",
                headers=headers,
                json={
                    "message": "обзор",
                    "history": [
                        {"role": "user", "content": "привет-история"},
                        {"role": "assistant", "content": "ответ-история"},
                    ],
                },
            )

    assert response.status_code == 200
    prompt = captured["prompt"]
    assert "AG-VISIBLE" in prompt
    assert "AG-HIDDEN" not in prompt  # excluded_from_ai filtered out of the context
    assert "привет-история" in prompt  # history forwarded into the prompt
    assert visible["id"] != hidden["id"]


def test_chat_falls_back_to_rule_based_when_model_unavailable():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "RB-1", name="Правило товар", stock=0, sold_month=5)
        # No Ollama configured in tests -> StoreAI answers with local warehouse rules.
        response = client.post("/api/ai/chat", headers=headers, json={"message": "что заказать?"})

    body = response.json()
    assert body["source"] == "rule_based"
    assert body["agent"] == "StoreAI"


# ─── Suppliers ────────────────────────────────────────────────────────────────


def test_supplier_crud_and_product_link():
    with TestClient(app) as client:
        headers = _login(client)
        created = client.post(
            "/api/suppliers",
            headers=headers,
            json={"name": "Bosch Pro", "contact_person": "Иван", "reliability": 5, "lead_time_days": 7},
        )
        assert created.status_code == 201
        sup = created.json()
        assert sup["reliability"] == 5
        assert sup["product_count"] == 0

        # Link a product to the supplier.
        product = _create_product(client, headers, "SUP-LINK-1", supplier_id=sup["id"])
        assert product["supplier_id"] == sup["id"]

        listing = client.get("/api/suppliers", headers=headers)
        row = next(s for s in listing.json() if s["id"] == sup["id"])
        assert row["product_count"] == 1

        # Update.
        upd = client.patch(f"/api/suppliers/{sup['id']}", headers=headers, json={"reliability": 3})
        assert upd.status_code == 200
        assert upd.json()["reliability"] == 3


def test_supplier_duplicate_name_rejected():
    with TestClient(app) as client:
        headers = _login(client)
        client.post("/api/suppliers", headers=headers, json={"name": "DeWalt"})
        dup = client.post("/api/suppliers", headers=headers, json={"name": "DeWalt"})

    assert dup.status_code == 409


def test_supplier_delete_admin_only_and_detaches_products():
    with TestClient(app) as client:
        admin_headers = _login(client)
        created = client.post("/api/suppliers", headers=admin_headers, json={"name": "Makita"})
        sup_id = created.json()["id"]
        product = _create_product(client, admin_headers, "SUP-DET-1", supplier_id=sup_id)

        manager_headers = _ensure_manager(client, admin_headers)
        forbidden = client.delete(f"/api/suppliers/{sup_id}", headers=manager_headers)
        assert forbidden.status_code == 403

        deleted = client.delete(f"/api/suppliers/{sup_id}", headers=admin_headers)
        assert deleted.status_code == 204

        # Product survives, detached from the supplier.
        fetched = client.get(f"/api/products/{product['id']}", headers=admin_headers)
        assert fetched.json()["supplier_id"] is None


def test_buyer_cannot_create_supplier():
    with TestClient(app) as client:
        admin_headers = _login(client)
        buyer_headers = _ensure_buyer(client, admin_headers)
        response = client.post("/api/suppliers", headers=buyer_headers, json={"name": "Запрещено"})

    assert response.status_code == 403


# ─── Dashboard period comparison ──────────────────────────────────────────────


def test_dashboard_comparison_reflects_latest_two_imports():
    # Two single-row imports become the latest two batches, so the comparison
    # aggregates are deterministic regardless of batches left by other tests.
    with TestClient(app) as client:
        headers = _login(client)
        first = _xlsx_bytes([{"Название товара": "Сравн товар", "Остаток": 5, "Продано за месяц": 2, "Продажная цена": 100}])
        client.post(
            "/api/imports/upload",
            headers=headers,
            files={"file": ("cmp1.xlsx", first, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        second = _xlsx_bytes([{"Название товара": "Сравн товар", "Остаток": 8, "Продано за месяц": 6, "Продажная цена": 100}])
        client.post(
            "/api/imports/upload",
            headers=headers,
            files={"file": ("cmp2.xlsx", second, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        dashboard = client.get("/api/dashboard", headers=headers).json()

    comp = dashboard["comparison"]
    assert comp is not None
    assert comp["sold_units"]["current"] == 6
    assert comp["sold_units"]["previous"] == 2
    assert comp["sold_units"]["change"] == 4
    assert comp["revenue"]["current"] == 600  # 6 * 100
    assert comp["sold_units"]["percent"] == 200.0  # (6-2)/2 * 100


def test_period_comparison_none_on_empty_db():
    # Unit-level: a session with no import batches yields no comparison.
    from backend.app.database import SessionLocal
    from backend.app.models import ImportBatch
    from backend.app.services.analytics import _period_comparison

    db = SessionLocal()
    try:
        had_batches = db.query(ImportBatch).count() > 0
        result = _period_comparison(db)
    finally:
        db.close()
    # If the shared DB already has >=2 batches we get a dict; otherwise None.
    if not had_batches:
        assert result is None
    else:
        assert result is None or isinstance(result, dict)


# ─── ABC/XYZ analysis ─────────────────────────────────────────────────────────


def test_abc_xyz_classifies_by_revenue():
    with TestClient(app) as client:
        headers = _login(client)
        # A clearly dominant revenue item + a tiny one.
        big = _create_product(client, headers, "ABC-BIG", name="ABC дорогой", sold_month=100, sale_price=1000)
        small = _create_product(client, headers, "ABC-SMALL", name="ABC дешёвый", sold_month=1, sale_price=10)
        response = client.get("/api/analytics/abc-xyz", headers=headers)

    assert response.status_code == 200
    body = response.json()
    rows = {r["sku"]: r for r in body["rows"]}
    assert rows["ABC-BIG"]["abc"] == "A"
    assert rows["ABC-BIG"]["revenue"] == 100000
    # The negligible item lands in C.
    assert rows["ABC-SMALL"]["abc"] == "C"
    assert "matrix" in body and "totals" in body


def test_abc_xyz_xyz_needs_history():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "XYZ-NEW", name="Без истории", sold_month=5, sale_price=100)
        response = client.get("/api/analytics/abc-xyz", headers=headers)

    row = next(r for r in response.json()["rows"] if r["sku"] == "XYZ-NEW")
    # No snapshots for a manually created product -> XYZ undefined.
    assert row["xyz"] is None
    assert row["cv"] is None


def test_abc_xyz_computes_cv_from_snapshots():
    from backend.app.services.abc_xyz import _demand_cv, _xyz_class

    assert _demand_cv([10, 10, 10]) == 0.0
    assert _xyz_class(0.0) == "X"
    assert _xyz_class(0.2) == "Y"
    assert _xyz_class(0.5) == "Z"
    assert _demand_cv([5]) is None  # insufficient history


# ─── Notifications ────────────────────────────────────────────────────────────


def test_notification_scan_flags_out_of_stock():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "NOTIF-OOS", name="Закончился товар", stock=0, sold_month=8)
        scan = client.post("/api/notifications/scan", headers=headers)

    assert scan.status_code == 200
    body = scan.json()
    low = [n for n in body["items"] if n["type"] == "low_stock" and "Закончился товар" in n["title"]]
    assert low
    assert low[0]["severity"] == "critical"
    assert body["unread"] >= 1


def test_notification_mark_read_decrements_unread():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "NOTIF-READ", name="Прочитать товар", stock=0, sold_month=8)
        scan = client.post("/api/notifications/scan", headers=headers).json()
        before = scan["unread"]
        target = next(n for n in scan["items"] if not n["is_read"])
        read = client.post(f"/api/notifications/{target['id']}/read", headers=headers)
        after = client.get("/api/notifications", headers=headers).json()["unread"]

    assert read.status_code == 204
    assert after == before - 1


def test_notification_scan_is_idempotent():
    # State alerts are rebuilt each scan, so scanning twice doesn't pile up dupes.
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "NOTIF-DUP", name="Дубль товар", stock=0, sold_month=8)
        first = client.post("/api/notifications/scan", headers=headers).json()
        second = client.post("/api/notifications/scan", headers=headers).json()

    count1 = sum(1 for n in first["items"] if n.get("title") == "Скоро закончится: Дубль товар")
    count2 = sum(1 for n in second["items"] if n.get("title") == "Скоро закончится: Дубль товар")
    assert count1 == 1
    assert count2 == 1


def test_buyer_cannot_scan_notifications():
    with TestClient(app) as client:
        admin_headers = _login(client)
        buyer_headers = _ensure_buyer(client, admin_headers)
        response = client.post("/api/notifications/scan", headers=buyer_headers)

    assert response.status_code == 403


def test_import_creates_notification():
    with TestClient(app) as client:
        headers = _login(client)
        content = _xlsx_bytes([{"Название товара": "Импорт уведомл", "Остаток": 0, "Продано за месяц": 9, "Продажная цена": 100}])
        client.post(
            "/api/imports/upload",
            headers=headers,
            files={"file": ("n.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        notes = client.get("/api/notifications", headers=headers).json()

    assert any(n["type"] == "import_warning" for n in notes["items"])


# ─── Purchase orders ──────────────────────────────────────────────────────────


def test_order_from_plan_groups_by_supplier():
    with TestClient(app) as client:
        headers = _login(client)
        sup = client.post("/api/suppliers", headers=headers, json={"name": "OrderSup"}).json()
        p1 = _create_product(client, headers, "ORD-P1", supplier_id=sup["id"], purchase_price=100)
        p2 = _create_product(client, headers, "ORD-P2", supplier_id=sup["id"], purchase_price=50)
        p3 = _create_product(client, headers, "ORD-P3", purchase_price=10)  # no supplier
        resp = client.post(
            "/api/orders/from-plan",
            headers=headers,
            json={"items": [
                {"product_id": p1["id"], "quantity": 3},
                {"product_id": p2["id"], "quantity": 2},
                {"product_id": p3["id"], "quantity": 5},
            ]},
        )

    assert resp.status_code == 201
    orders = resp.json()
    # One order for OrderSup (p1+p2), one for the no-supplier item.
    assert len(orders) == 2
    sup_order = next(o for o in orders if o["supplier_name"] == "OrderSup")
    assert sup_order["item_count"] == 2
    assert sup_order["total_amount"] == 400  # 3*100 + 2*50
    assert sup_order["status"] == "draft"


def test_order_received_creates_receipt_movement():
    with TestClient(app) as client:
        headers = _login(client)
        p = _create_product(client, headers, "ORD-RCV", stock=5, purchase_price=100)
        order = client.post(
            "/api/orders/from-plan",
            headers=headers,
            json={"items": [{"product_id": p["id"], "quantity": 7}]},
        ).json()[0]
        # draft -> sent -> received
        client.patch(f"/api/orders/{order['id']}/status", headers=headers, json={"status": "sent"})
        recv = client.patch(f"/api/orders/{order['id']}/status", headers=headers, json={"status": "received"})
        product = client.get(f"/api/products/{p['id']}", headers=headers).json()
        movements = client.get(f"/api/products/{p['id']}/movements", headers=headers).json()

    assert recv.status_code == 200
    assert recv.json()["status"] == "received"
    assert recv.json()["received_at"] is not None
    assert product["stock"] == 12  # 5 + 7 received
    assert any(m["movement_type"] == "receipt" and m["quantity"] == 7 for m in movements)


def test_order_illegal_transition_rejected():
    with TestClient(app) as client:
        headers = _login(client)
        p = _create_product(client, headers, "ORD-BAD", purchase_price=10)
        order = client.post(
            "/api/orders/from-plan", headers=headers,
            json={"items": [{"product_id": p["id"], "quantity": 1}]},
        ).json()[0]
        # draft -> received is not allowed (must go through sent)
        resp = client.patch(f"/api/orders/{order['id']}/status", headers=headers, json={"status": "received"})

    assert resp.status_code == 400


def test_buyer_cannot_create_order():
    with TestClient(app) as client:
        admin_headers = _login(client)
        p = _create_product(client, admin_headers, "ORD-BUYER", purchase_price=10)
        buyer_headers = _ensure_buyer(client, admin_headers)
        resp = client.post(
            "/api/orders/from-plan", headers=buyer_headers,
            json={"items": [{"product_id": p["id"], "quantity": 1}]},
        )

    assert resp.status_code == 403


def test_order_create_is_audited():
    with TestClient(app) as client:
        headers = _login(client)
        p = _create_product(client, headers, "ORD-AUDIT", purchase_price=10)
        client.post(
            "/api/orders/from-plan", headers=headers,
            json={"items": [{"product_id": p["id"], "quantity": 1}]},
        )
        audit = client.get("/api/audit?action=order.create", headers=headers).json()

    assert audit


def test_import_auto_links_supplier_by_name():
    with TestClient(app) as client:
        headers = _login(client)
        sup = client.post("/api/suppliers", headers=headers, json={"name": "Makita"}).json()
        content = _xlsx_bytes([{
            "Артикул": "LINK-1", "Название товара": "Дрель Makita", "Остаток": 5,
            "Продано за месяц": 3, "Продажная цена": 6000, "Поставщик": "makita",
        }])
        client.post(
            "/api/imports/upload", headers=headers,
            files={"file": ("s.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        products = client.get("/api/products?search=LINK-1", headers=headers).json()

    linked = next(p for p in products if p["sku"] == "LINK-1")
    assert linked["supplier_id"] == sup["id"]  # case-insensitive name match


# ─── User management & security ───────────────────────────────────────────────


def _create_user(client, admin_headers, username, role="manager", password="passw0rd"):
    resp = client.post(
        "/api/users", headers=admin_headers,
        json={"username": username, "full_name": username.title(), "password": password, "role": role},
    )
    assert resp.status_code in (201, 409)
    users = client.get("/api/users", headers=admin_headers).json()
    return next(u for u in users if u["username"] == username)


def test_admin_can_edit_role_and_deactivate():
    with TestClient(app) as client:
        admin = _login(client)
        u = _create_user(client, admin, "edit_target", role="manager")
        promote = client.patch(f"/api/users/{u['id']}", headers=admin, json={"role": "buyer", "full_name": "Renamed"})
        deact = client.patch(f"/api/users/{u['id']}", headers=admin, json={"is_active": False})

    assert promote.status_code == 200
    assert promote.json()["role"] == "buyer"
    assert promote.json()["full_name"] == "Renamed"
    assert deact.json()["is_active"] is False


def test_deactivated_user_cannot_login():
    with TestClient(app) as client:
        admin = _login(client)
        u = _create_user(client, admin, "to_disable", password="passw0rd")
        client.patch(f"/api/users/{u['id']}", headers=admin, json={"is_active": False})
        resp = client.post("/api/auth/login", json={"username": "to_disable", "password": "passw0rd"})

    assert resp.status_code == 401


def test_admin_cannot_deactivate_self():
    with TestClient(app) as client:
        admin = _login(client)
        me = client.get("/api/auth/me", headers=admin).json()
        resp = client.patch(f"/api/users/{me['id']}", headers=admin, json={"is_active": False})

    assert resp.status_code == 400


def test_admin_password_reset_lets_user_login():
    with TestClient(app) as client:
        admin = _login(client)
        u = _create_user(client, admin, "reset_me", password="oldpass1")
        reset = client.post(f"/api/users/{u['id']}/reset-password", headers=admin, json={"password": "newpass2"})
        ok = client.post("/api/auth/login", json={"username": "reset_me", "password": "newpass2"})

    assert reset.status_code == 204
    assert ok.status_code == 200


def test_self_change_password():
    with TestClient(app) as client:
        admin = _login(client)
        _create_user(client, admin, "selfchg", password="origpass1")
        headers = _login(client, "selfchg", "origpass1")
        wrong = client.post("/api/auth/change-password", headers=headers, json={"current_password": "nope", "new_password": "brandnew1"})
        ok = client.post("/api/auth/change-password", headers=headers, json={"current_password": "origpass1", "new_password": "brandnew1"})
        relog = client.post("/api/auth/login", json={"username": "selfchg", "password": "brandnew1"})

    assert wrong.status_code == 400
    assert ok.status_code == 204
    assert relog.status_code == 200


def test_buyer_cannot_manage_users():
    with TestClient(app) as client:
        admin = _login(client)
        buyer = _ensure_buyer(client, admin)
        target = _create_user(client, admin, "victim")
        resp = client.patch(f"/api/users/{target['id']}", headers=buyer, json={"role": "admin"})

    assert resp.status_code == 403


def test_ai_chat_stream_fast_path_emits_done_event():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "STREAM-1", name="Стрим товар", stock=0, sold_month=8)
        # "Что заказать?" is handled by the fast local router -> no Ollama needed.
        resp = client.post("/api/ai/chat/stream", headers=headers, json={"message": "Что заказать?"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[5:].strip()) for line in resp.text.splitlines() if line.startswith("data:")]
    assert any(e["type"] == "delta" for e in events)
    done = next(e for e in events if e["type"] == "done")
    assert done["source"] == "rule_based"
    assert isinstance(done["answer"], str) and done["answer"]
