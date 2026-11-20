"""Token and request usage tracking for PANDA's model providers.

Two sources of truth, shown side by side in the UI:

* Counted by PANDA: every successful answer's prompt/completion tokens and one
  request, stored per provider, model and day in `<PANDA_STORAGE_DIR>/llm_usage.sqlite`
  so the totals survive redeploys (on Railway the storage volume persists).
  The day is the Pacific-time date, matching Gemini's midnight-Pacific reset.
* Reported by the provider: Groq returns live quota headers on every response
  (daily requests limit/remaining, per-minute tokens limit/remaining). Gemini
  returns no quota headers, so its limits come from configuration instead.

The usage database holds counts only, never prompts, answers or keys.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")
_lock = threading.Lock()

# Free-tier daily limits used when the provider does not report them.
# Groq: published Free plan limits for gpt-oss models (requests/day, tokens/day).
# Gemini: KTPI's documented free-tier allowance for the Flash-Lite default.
# Override per deployment because limits differ by account and change over time.
DEFAULT_DAILY_LIMITS = {
    "groq": {"requests_env": "PANDA_GROQ_DAILY_REQUESTS", "requests": 1000,
             "tokens_env": "PANDA_GROQ_DAILY_TOKENS", "tokens": 200_000},
    "gemini": {"requests_env": "PANDA_GEMINI_DAILY_REQUESTS", "requests": 500,
               "tokens_env": "PANDA_GEMINI_DAILY_TOKENS", "tokens": 0},
}

GROQ_HEADERS = {
    "limit_requests": "x-ratelimit-limit-requests",          # per day
    "remaining_requests": "x-ratelimit-remaining-requests",  # per day
    "reset_requests": "x-ratelimit-reset-requests",
    "limit_tokens": "x-ratelimit-limit-tokens",              # per minute
    "remaining_tokens": "x-ratelimit-remaining-tokens",      # per minute
    "reset_tokens": "x-ratelimit-reset-tokens",
}


def usage_db_path() -> Path:
    root = Path(os.environ.get("PANDA_STORAGE_DIR", "storage"))
    return root / "llm_usage.sqlite"


def usage_day(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(PACIFIC)).astimezone(PACIFIC).date().isoformat()


def _connect() -> sqlite3.Connection:
    path = usage_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS usage_daily (
               day TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
               requests INTEGER NOT NULL DEFAULT 0,
               prompt_tokens INTEGER NOT NULL DEFAULT 0,
               completion_tokens INTEGER NOT NULL DEFAULT 0,
               PRIMARY KEY (day, provider, model))"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS provider_quota (
               provider TEXT PRIMARY KEY, observed_at REAL NOT NULL,
               limit_requests INTEGER, remaining_requests INTEGER, reset_requests TEXT,
               limit_tokens INTEGER, remaining_tokens INTEGER, reset_tokens TEXT)"""
    )
    return conn


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def normalize_usage(raw: Any) -> Dict[str, int]:
    """Accept OpenAI-style usage or Ollama eval counts; return prompt/completion/total."""
    if raw is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    get = raw.get if isinstance(raw, Mapping) else (lambda k, d=None: getattr(raw, k, d))
    prompt = _as_int(get("prompt_tokens", None) or get("prompt_eval_count", None))
    completion = _as_int(get("completion_tokens", None) or get("eval_count", None))
    total = _as_int(get("total_tokens", None)) or prompt + completion
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}


def record(provider: str, model: str, usage: Mapping[str, int]) -> None:
    """Add one successful request. Never raises: usage tracking must not break answers."""
    try:
        with _lock, _connect() as conn:
            conn.execute(
                """INSERT INTO usage_daily (day, provider, model, requests, prompt_tokens, completion_tokens)
                   VALUES (?, ?, ?, 1, ?, ?)
                   ON CONFLICT(day, provider, model) DO UPDATE SET
                     requests = requests + 1,
                     prompt_tokens = prompt_tokens + excluded.prompt_tokens,
                     completion_tokens = completion_tokens + excluded.completion_tokens""",
                (usage_day(), provider, model or "unknown",
                 _as_int(usage.get("prompt_tokens")), _as_int(usage.get("completion_tokens"))),
            )
    except Exception:
        pass


def record_quota_headers(provider: str, headers: Mapping[str, str]) -> None:
    """Store the provider's live quota headers, if it sent any (Groq does; Gemini does not)."""
    try:
        values = {key: headers.get(name) for key, name in GROQ_HEADERS.items()}
        if values["limit_requests"] is None and values["limit_tokens"] is None:
            return
        with _lock, _connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO provider_quota
                   (provider, observed_at, limit_requests, remaining_requests, reset_requests,
                    limit_tokens, remaining_tokens, reset_tokens)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (provider, time.time(),
                 _as_int(values["limit_requests"]), _as_int(values["remaining_requests"]),
                 values["reset_requests"],
                 _as_int(values["limit_tokens"]), _as_int(values["remaining_tokens"]),
                 values["reset_tokens"]),
            )
    except Exception:
        pass


def daily_limits(provider: str) -> Dict[str, int]:
    spec = DEFAULT_DAILY_LIMITS.get(provider)
    if not spec:
        return {"requests": 0, "tokens": 0}
    return {
        "requests": _as_int(os.environ.get(spec["requests_env"], spec["requests"])),
        "tokens": _as_int(os.environ.get(spec["tokens_env"], spec["tokens"])),
    }


def summary(day: Optional[str] = None) -> Dict[str, Any]:
    """Usage for one Pacific-time day, per provider, plus Groq's latest live quota."""
    day = day or usage_day()
    providers: Dict[str, Dict[str, Any]] = {}
    quotas: Dict[str, Dict[str, Any]] = {}
    try:
        with _lock, _connect() as conn:
            rows = conn.execute(
                """SELECT provider, model, requests, prompt_tokens, completion_tokens
                   FROM usage_daily WHERE day = ? ORDER BY provider, model""",
                (day,),
            ).fetchall()
            quota_rows = conn.execute("SELECT * FROM provider_quota").fetchall()
            quota_cols = [c[0] for c in conn.execute("SELECT * FROM provider_quota LIMIT 0").description]
    except Exception:
        rows, quota_rows, quota_cols = [], [], []
    for provider, model, requests, prompt, completion in rows:
        entry = providers.setdefault(provider, {"requests": 0, "prompt_tokens": 0,
                                                "completion_tokens": 0, "models": []})
        entry["requests"] += requests
        entry["prompt_tokens"] += prompt
        entry["completion_tokens"] += completion
        entry["models"].append({"model": model, "requests": requests,
                                "tokens": prompt + completion})
    for entry in providers.values():
        entry["total_tokens"] = entry["prompt_tokens"] + entry["completion_tokens"]
    for row in quota_rows:
        record_ = dict(zip(quota_cols, row))
        quotas[record_.pop("provider")] = record_
    return {"day": day, "providers": providers, "quotas": quotas}


def remaining(used: int, limit: int) -> Optional[int]:
    return max(0, limit - used) if limit else None


def provider_rows(day: Optional[str] = None, providers: Optional[List[str]] = None) -> Dict[str, Any]:
    """Flattened rows for display: used, limit and remaining for each provider."""
    data = summary(day)
    names = providers or sorted(set(data["providers"]) | set(data["quotas"]))
    rows = []
    for name in names:
        used = data["providers"].get(name, {"requests": 0, "total_tokens": 0, "models": []})
        limits = daily_limits(name)
        quota = data["quotas"].get(name)
        row = {
            "provider": name,
            "requests_used": used["requests"],
            "tokens_used": used["total_tokens"],
            "models": used["models"],
            "requests_limit": limits["requests"],
            "tokens_limit": limits["tokens"],
            "requests_remaining": remaining(used["requests"], limits["requests"]),
            "tokens_remaining": remaining(used["total_tokens"], limits["tokens"]),
            "source": "counted by PANDA",
            "live": None,
        }
        if quota and quota.get("limit_requests"):
            # The provider's own numbers beat PANDA's count (they include other apps on the key).
            row["requests_limit"] = quota["limit_requests"]
            row["requests_remaining"] = quota["remaining_requests"]
            row["source"] = "reported by provider"
            row["live"] = quota
        rows.append(row)
    return {"day": data["day"], "rows": rows}
