from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import threading
import time

from ..config import ROOT_DIR, settings


ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

# Bound how many Claw subprocesses run at once. Each call ties up a request
# threadpool worker for up to claw_timeout_seconds, so without this a burst of
# chat requests could exhaust the pool and stall the whole app.
_CLAW_SLOTS = threading.BoundedSemaphore(max(1, settings.claw_max_concurrent))

# Cache the status probe (filesystem + env scans) so every chat/status call
# doesn't re-stat the binary and re-scan provider env vars.
_status_cache: dict | None = None
_status_cache_at: float = 0.0
_status_lock = threading.Lock()


@dataclass(frozen=True)
class ClawAgentResult:
    answer: str | None
    error: str | None = None


def _resolve_storeai_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (ROOT_DIR / path).resolve()


def _claw_binary() -> Path:
    return _resolve_storeai_path(settings.claw_binary_path)


def _claw_workspace() -> Path:
    return _resolve_storeai_path(settings.claw_workspace)


def claw_agent_status(*, use_cache: bool = True) -> dict:
    """Return the agent status, cached for claw_status_cache_seconds."""
    global _status_cache, _status_cache_at
    ttl = max(0, settings.claw_status_cache_seconds)
    now = time.monotonic()
    if use_cache and _status_cache is not None and (now - _status_cache_at) < ttl:
        return _status_cache

    status = _probe_claw_agent_status()
    with _status_lock:
        _status_cache = status
        _status_cache_at = now
    return status


def _probe_claw_agent_status() -> dict:
    binary = _claw_binary()
    enabled = settings.claw_agent_enabled
    binary_exists = binary.is_file()
    cargo_available = shutil.which("cargo") is not None
    provider_configured = any(
        os.getenv(name)
        for name in [
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OLLAMA_HOST",
        ]
    )
    available = enabled and binary_exists and provider_configured
    if not enabled:
        state = "disabled"
    elif not binary_exists:
        state = "missing_binary"
    elif not provider_configured:
        state = "missing_provider"
    elif available:
        state = "ready"
    else:
        state = "not_ready"

    setup_steps: list[str] = []
    if not enabled:
        setup_steps.append("Set CLAW_AGENT_ENABLED=true in StoreAI .env")
    if not cargo_available and not binary_exists:
        setup_steps.append("Install Rust/Cargo or add cargo to PATH")
    if not binary_exists:
        setup_steps.append("Run: cd ../claw-code-main/rust && cargo build --workspace")
    if not provider_configured:
        setup_steps.append("Set ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, OPENAI_BASE_URL, or OLLAMA_HOST")

    return {
        "enabled": enabled,
        "available": available,
        "state": state,
        "binary_exists": binary_exists,
        "cargo_available": cargo_available,
        "provider_configured": provider_configured,
        "binary_path": str(binary),
        "workspace": str(_claw_workspace()),
        "model": settings.claw_model or None,
        "permission_mode": settings.claw_permission_mode,
        "timeout_seconds": settings.claw_timeout_seconds,
        "setup_steps": setup_steps,
    }


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


def build_claw_prompt(message: str, warehouse_context: list[dict], history: list[dict] | None = None) -> str:
    return (
        "Ты Claw Code агент, встроенный как AI-ассистент в веб-приложение StoreAI/СкладAI.\n"
        "Отвечай владельцу склада строительных инструментов на русском языке.\n"
        "Используй только JSON-контекст склада ниже: не выдумывай товары, цены, остатки или поставщиков.\n"
        "Не изменяй файлы, не запускай команды и не проси доступы: сейчас нужен только аналитический ответ.\n"
        "Отвечай кратко, практично, списками и цифрами. Если данных не хватает, честно скажи каких.\n\n"
        f"Контекст склада JSON:\n{json.dumps(warehouse_context, ensure_ascii=False, separators=(',', ':'))}\n\n"
        f"{_format_history(history)}"
        f"Текущий вопрос пользователя:\n{message}"
    )


def clean_claw_output(value: str) -> str:
    text = ANSI_RE.sub("", value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()


def call_claw_agent(
    message: str,
    warehouse_context: list[dict],
    history: list[dict] | None = None,
) -> ClawAgentResult:
    status = claw_agent_status()
    if not status["enabled"]:
        return ClawAgentResult(answer=None, error="Claw agent disabled")
    if not status["available"]:
        if not status["binary_exists"]:
            return ClawAgentResult(answer=None, error=f"Claw binary not found: {status['binary_path']}")
        if not status["provider_configured"]:
            return ClawAgentResult(answer=None, error="Claw provider is not configured")
        return ClawAgentResult(answer=None, error=f"Claw agent is not ready: {status['state']}")

    # Bound concurrency: if every slot is busy, fall back rather than queueing up
    # and holding a request worker hostage.
    acquire_timeout = max(0, settings.claw_acquire_timeout_seconds)
    if not _CLAW_SLOTS.acquire(timeout=acquire_timeout):
        return ClawAgentResult(answer=None, error="Claw agent busy")

    try:
        args = [
            status["binary_path"],
            "--permission-mode",
            settings.claw_permission_mode,
        ]
        if settings.claw_model:
            args.extend(["--model", settings.claw_model])
        args.append("prompt")

        env = os.environ.copy()
        env.setdefault("NO_COLOR", "1")
        env.setdefault("CLAW_OUTPUT_FORMAT", "text")

        try:
            completed = subprocess.run(
                args,
                input=build_claw_prompt(message, warehouse_context, history),
                cwd=status["workspace"],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(5, settings.claw_timeout_seconds),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ClawAgentResult(answer=None, error="Claw agent timeout")
        except OSError as exc:
            return ClawAgentResult(answer=None, error=str(exc))
    finally:
        _CLAW_SLOTS.release()

    output = clean_claw_output(completed.stdout)
    error = clean_claw_output(completed.stderr)
    if completed.returncode != 0:
        return ClawAgentResult(answer=None, error=error or output or f"Claw exited with {completed.returncode}")
    if not output:
        return ClawAgentResult(answer=None, error=error or "Claw returned empty answer")
    return ClawAgentResult(answer=output)
