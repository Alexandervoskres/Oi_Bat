# СкладAI

Веб-приложение для аналитики склада строительных инструментов: загрузка Excel, история импортов, AI-статусы товаров, роли пользователей и PDF-отчет по рискам.

## Что внутри

- Backend: Python, FastAPI, SQLAlchemy.
- База: PostgreSQL через `DATABASE_URL`; для быстрой локальной демонстрации есть fallback SQLite.
- Frontend: React + HTML + CSS без сборщика, отдается тем же FastAPI-сервером.
- AI: локальный StoreAI-режим работает сразу; внешний AI подключается через агент StoreAI/Claw.
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

## Claw Code AI-ассистент

StoreAI умеет подключать локальный агент `claw` из соседнего проекта `claw-code-main`.
Если агент не собран или не настроен, чат продолжит работать через локальные рекомендации.

1. Соберите Claw Code:

```powershell
cd ..\claw-code-main\rust
cargo build --workspace
```

2. В `.env` StoreAI включите адаптер:

```env
CLAW_AGENT_ENABLED=true
CLAW_BINARY_PATH=../claw-code-main/rust/target/debug/claw.exe
CLAW_WORKSPACE=.
CLAW_PERMISSION_MODE=read-only
CLAW_MODEL=
```

3. Передайте параметры вашего AI-провайдера, например OpenAI-compatible endpoint:

```env
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_API_KEY=local-or-your-provider-key
```

После этого `/api/ai/chat` сначала попробует ответить через внешний AI-агент, а если агент недоступен, вернется к локальным правилам StoreAI. Статус агента доступен в `/api/ai/status` и отображается в шапке чата.

## Подготовка к серверу

Перед деплоем замените:

- `SECRET_KEY`
- `DEFAULT_ADMIN_PASSWORD`
- `DATABASE_URL`
- `CORS_ORIGINS`

Для production лучше запускать backend через `gunicorn`/`uvicorn workers`, а PostgreSQL держать отдельно или через управляемый сервис.
