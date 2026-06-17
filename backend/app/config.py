from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "backend" / "data"
FRONTEND_DIR = ROOT_DIR / "frontend"


def load_dotenv() -> None:
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "СкладAI")
    environment: str = os.getenv("APP_ENV", "local")
    secret_key: str = os.getenv("SECRET_KEY", "change-me-in-production")
    access_token_minutes: int = _env_int("ACCESS_TOKEN_MINUTES", 720)
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(DATA_DIR / 'dev.db').as_posix()}",
    )
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:8000")
    default_admin_username: str = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
    default_admin_password: str = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")
    default_admin_full_name: str = os.getenv("DEFAULT_ADMIN_FULL_NAME", "Администратор")
    claw_agent_enabled: bool = _env_bool("CLAW_AGENT_ENABLED")
    claw_binary_path: str = os.getenv(
        "CLAW_BINARY_PATH",
        str(ROOT_DIR.parent / "claw-code-main" / "rust" / "target" / "debug" / "claw.exe"),
    )
    claw_workspace: str = os.getenv("CLAW_WORKSPACE", str(ROOT_DIR))
    claw_model: str = os.getenv("CLAW_MODEL", "")
    claw_permission_mode: str = os.getenv("CLAW_PERMISSION_MODE", "read-only")
    claw_timeout_seconds: int = _env_int("CLAW_TIMEOUT_SECONDS", 45)
    # Max Claw subprocesses running at once; extra requests fall back instead of
    # piling up and exhausting the request threadpool.
    claw_max_concurrent: int = _env_int("CLAW_MAX_CONCURRENT", 2)
    # How long an extra request waits for a free Claw slot before falling back.
    claw_acquire_timeout_seconds: int = _env_int("CLAW_ACQUIRE_TIMEOUT_SECONDS", 2)
    # Cache the agent status probe (filesystem + env checks) for this long.
    claw_status_cache_seconds: int = _env_int("CLAW_STATUS_CACHE_SECONDS", 30)
    # Number of recent chat turns forwarded to the model for follow-up context.
    ai_history_turns: int = _env_int("AI_HISTORY_TURNS", 6)
    # Append /no_think to the agent prompt (qwen3): ~halves latency and stops
    # the model wandering into tool calls. Harmless for models that ignore it.
    claw_no_think: bool = _env_bool("CLAW_NO_THINK", True)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"prod", "production"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def validate(self) -> None:
        if self.is_production and self.secret_key == "change-me-in-production":
            raise RuntimeError("SECRET_KEY must be changed before production startup")
        if self.is_production and self.default_admin_password == "admin123":
            raise RuntimeError("DEFAULT_ADMIN_PASSWORD must be changed before production startup")


settings = Settings()
settings.validate()
DATA_DIR.mkdir(parents=True, exist_ok=True)
