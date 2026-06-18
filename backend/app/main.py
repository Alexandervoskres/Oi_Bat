"""ГЛАВНЫЙ ФАЙЛ ПРИЛОЖЕНИЯ — здесь всё собирается воедино («рубильник»).

Что делает:
  • при старте готовит базу (init_db: миграции + создание админа);
  • разрешает браузеру обращаться к API (CORS);
  • подключает все группы адресов из папки routers/ (include_router);
  • отдаёт фронтенд (файлы из frontend/ и саму страницу index.html).

Запуск:  uvicorn backend.app.main:app --reload --port 8000
ВАЖНО: добавил новый файл-роутер в routers/ — не забудь подключить его здесь,
иначе его адреса (/api/...) работать не будут.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIR, settings
from .database import init_db
from .routers import (
    ai_chat,
    analytics,
    audit,
    auth,
    imports,
    notifications,
    orders,
    procurement,
    products,
    reports,
    suppliers,
    users,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Код до yield выполняется ОДИН раз при запуске сервера: готовим базу.
    init_db()
    yield
    # Код после yield выполнился бы при остановке (сейчас ничего не нужно).


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# CORS: с каких адресов браузеру разрешено стучаться в API (из настроек).
origins = settings.cors_origin_list or ["http://localhost:8000", "http://127.0.0.1:8000"]
allow_credentials = "*" not in origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем все группы адресов. Каждый router — отдельный файл в routers/.
app.include_router(auth.router)          # вход / смена пароля
app.include_router(users.router)         # пользователи (только админ)
app.include_router(products.router)      # товары + движения склада
app.include_router(suppliers.router)     # поставщики
app.include_router(orders.router)        # заказы поставщикам
app.include_router(imports.router)       # загрузка Excel
app.include_router(analytics.router)     # дашборд + ABC/XYZ
app.include_router(procurement.router)   # план закупок
app.include_router(ai_chat.router)       # AI-советник
app.include_router(audit.router)         # журнал действий (только админ)
app.include_router(notifications.router) # уведомления
app.include_router(reports.router)       # PDF-отчёты


# Отдаём статику фронтенда (JS/CSS) по адресу /static/...
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def index():
    """Главная страница сайта — отдаём frontend/index.html."""
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found")
    return FileResponse(index_path)
