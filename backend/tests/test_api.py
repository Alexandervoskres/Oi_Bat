from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import tempfile

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
    assert body["active_agent"] in {"StoreAI", "Claude API", "Claw Code"}
    assert "claw" in body
    assert {"enabled", "available", "state", "binary_path"}.issubset(body["claw"])


def test_ai_chat_greeting_does_not_return_warehouse_summary():
    with TestClient(app) as client:
        headers = _login(client)
        _create_product(client, headers, "HELLO-001", name="Тестовый товар привет", stock=0, sold_month=8)
        response = client.post("/api/ai/chat", headers=headers, json={"message": "Привет"})

    assert response.status_code == 200
    body = response.json()
    assert "Привет" in body["answer"]
    assert "Сначала проверьте закупку" not in body["answer"]


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
        response = client.post("/api/ai/chat", headers=headers, json={"message": "Что не закупать?"})

    assert response.status_code == 200
    body = response.json()
    assert "Не закупать тест" in body["answer"]
    assert "Не закупать тест" in body["used_products"]


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
