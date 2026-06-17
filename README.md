# СкладAI

Веб-приложение для аналитики склада строительных инструментов: загрузка Excel, история импортов, AI-статусы товаров, роли пользователей и PDF-отчет по рискам.

## Что внутри

- Backend: Python, FastAPI, SQLAlchemy.
- База: PostgreSQL через `DATABASE_URL`; для быстрой локальной демонстрации есть fallback SQLite.
- Frontend: React + HTML + CSS без сборщика, отдается тем же FastAPI-сервером.
- AI: локальный StoreAI-режим работает сразу; для открытых вопросов подключается локальная модель через Ollama (со стримингом).
- Авторизация: логин/пароль, роли `admin`, `manager`, `buyer`.
- Отчеты: выгрузка PDF по рискам.

## Быстрый локальный запуск

```powershell
.\run-local.ps1
```

Откройте:

```text
http://127.0.0.1:8000
```

Тестовый вход:

```text
Логин: admin
Пароль: admin123
```

Локального администратора можно переопределить в `.env`:

```env
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=admin123
DEFAULT_ADMIN_FULL_NAME=Администратор
```

## Запуск с PostgreSQL

1. Скопируйте `.env.example` в `.env`.
2. Поднимите базу:

```powershell
docker compose up -d db
```

3. Установите зависимости и запустите API:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

## Миграции базы данных

Схема управляется через Alembic. При старте приложение само прогоняет
`alembic upgrade head` (см. `init_db` в `backend/app/database.py`), поэтому для
обычного запуска ничего делать не нужно — база создаётся из миграций.

Базовая миграция строит всю текущую схему из моделей. При изменении моделей
создавайте новую ревизию:

```powershell
# сгенерировать ревизию по изменениям моделей
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini revision --autogenerate -m "describe change"
# применить
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
# текущая версия / история
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini current
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini history
```

URL базы Alembic берёт из настроек приложения (`DATABASE_URL`), отдельно его
прописывать в `alembic.ini` не нужно.

## Проверка проекта

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend
.\.venv\Scripts\python.exe -m pytest backend\tests
```

Smoke-тесты проверяют логин, дашборд, импорт Excel, запрет загрузки для роли `buyer` и скачивание PDF.

## Excel-структура

В приложении есть кнопка `Скачать шаблон`. Минимально нужны колонки:

- `Название товара`
- `Остаток`

Рекомендуемые колонки:

- `Артикул`
- `Категория`
- `Продано за месяц`
- `Средние продажи в месяц`
- `Закупочная цена`
- `Продажная цена`
- `Дата последней продажи`
- `Поставщик`
- `Минимальный остаток`
- `Срок поставки`

## Роли

- `admin`: загрузка Excel, отчеты, пользователи.
- `manager`: загрузка Excel, склад, дашборд, отчеты.
- `buyer`: просмотр аналитики, склад, история, отчеты.

## AI-ассистент (локальная модель через Ollama)

Чат всегда работает на локальных правилах StoreAI (мгновенно, без модели).
Открытые/аналитические вопросы дополнительно идут в **локальную модель через
[Ollama](https://ollama.com)** — напрямую, без посредников. Если Ollama не
запущена, чат остаётся на правилах: приложение полностью функционально без модели.

**1. Установить Ollama и скачать модель:**

```powershell
ollama pull qwen3:latest
ollama serve   # обычно уже запущена как сервис на http://127.0.0.1:11434
```

**2. Указать в `.env` StoreAI** (см. `.env.example`):

```env
OLLAMA_HOST=http://127.0.0.1:11434
AI_MODEL=qwen3:latest
AI_NO_THINK=true          # для qwen3: отключает «размышления» — ~2x быстрее и без срывов
AI_TIMEOUT_SECONDS=120
```

После этого:
- `/api/ai/chat/stream` (SSE) — потоковый ответ модели по токенам (это использует чат в UI);
- `/api/ai/chat` — тот же ответ, но целиком;
- `/api/ai/status` — показывает `ollama.available` и имя модели (видно в шапке чата).

Проверка модели напрямую: `curl http://127.0.0.1:11434/api/tags` (должна вернуть список
моделей). Реасонинг-модели (как qwen3) на большом контексте отвечают не мгновенно —
первый токен может идти ~15-20 сек, это нормально; стриминг показывает ответ по мере
генерации.

## Подготовка к серверу

Перед деплоем замените:

- `SECRET_KEY`
- `DEFAULT_ADMIN_PASSWORD`
- `DATABASE_URL`
- `CORS_ORIGINS`

Для production лучше запускать backend через `gunicorn`/`uvicorn workers`, а PostgreSQL держать отдельно или через управляемый сервис.
