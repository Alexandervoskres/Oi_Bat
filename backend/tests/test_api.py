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
