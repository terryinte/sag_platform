"""Global collection channels and per-project sampling strategy.

Stored API keys are encrypted. Responses only include the last four characters.
An environment variable for the same channel wins over the stored key.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from api.database import Database
from api.mvp_models import BudgetEstimateRequest, ChannelUpdate, StrategyUpdate
from api.secret_box import SecretNotConfigured, decrypt_text, encrypt_text, mask_last4
from data_collectors.providers.answers import (
    ClaudeWebSearchProvider,
    DeepSeekSearchProvider,
    GeminiGroundingProvider,
    KimiSearchProvider,
    OpenAIWebSearchProvider,
    OpenRouterAnswerProvider,
    PerplexityAgentProvider,
    QianfanAnswerProvider,
    ScrapeResult,
)
from data_collectors.providers.browser import collect_browser_answer, browser_runtime_status

API_UNIT_USD = 0.01

_API = [
    {"id": "openai", "label": "OpenAI（web_search）", "engine": "ChatGPT", "env": ["OPENAI_API_KEY"], "model": "gpt-4.1-mini", "kind": "api", "phase": "P0"},
    {"id": "perplexity", "label": "Perplexity", "engine": "Perplexity", "env": ["PERPLEXITY_API_KEY"], "model": "sonar", "kind": "api", "phase": "P0"},
    {"id": "gemini", "label": "Gemini grounding", "engine": "Gemini", "env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"], "model": "gemini-2.0-flash", "kind": "api", "phase": "P0"},
    {"id": "claude", "label": "Claude web_search", "engine": "Claude", "env": ["ANTHROPIC_API_KEY"], "model": "claude-sonnet-4-5", "kind": "api", "phase": "P0"},
    {"id": "deepseek", "label": "DeepSeek", "engine": "DeepSeek", "env": ["DEEPSEEK_API_KEY"], "model": "deepseek-chat", "kind": "api", "phase": "P0"},
    {"id": "kimi", "label": "Kimi", "engine": "Kimi", "env": ["KIMI_API_KEY", "MOONSHOT_API_KEY"], "model": "moonshot-v1-auto", "kind": "api", "phase": "P0"},
    {"id": "openrouter", "label": "OpenRouter", "engine": "OpenRouter", "env": ["OPENROUTER_API_KEY"], "model": "openai/gpt-4.1-mini", "kind": "api", "phase": "P0"},
    {"id": "qianfan", "label": "千帆", "engine": "文心", "env": ["QIANFAN_ACCESS_KEY", "QIANFAN_SECRET_KEY"], "model": "qianfan-chat", "kind": "api", "phase": "P0", "dual": True},
]

_WEB = [
    {"id": "chatgpt_web", "label": "ChatGPT网页", "engine": "ChatGPT 网页", "env": [], "model": "", "kind": "web", "phase": "P1"},
    {"id": "perplexity_web", "label": "Perplexity网页", "engine": "Perplexity 网页", "env": [], "model": "", "kind": "web", "phase": "P1"},
    {"id": "gemini_web", "label": "Gemini网页", "engine": "Gemini 网页", "env": [], "model": "", "kind": "web", "phase": "P1"},
    {"id": "doubao", "label": "豆包", "engine": "豆包", "env": [], "model": "", "kind": "web", "phase": "P1"},
    {"id": "yuanbao", "label": "元宝", "engine": "元宝", "env": [], "model": "", "kind": "web", "phase": "P1"},
    {"id": "kimi_web", "label": "Kimi网页", "engine": "Kimi 网页", "env": [], "model": "", "kind": "web", "phase": "P1"},
]

_LEGACY_WEB = ("Google AI 概览", "Google AI Mode", "Copilot")
CHANNEL_SPECS = _API + _WEB
_BY_ID = {item["id"]: item for item in CHANNEL_SPECS}
_BY_ENGINE = {item["engine"]: item for item in CHANNEL_SPECS}
WEB_ENGINES = {item["engine"] for item in _WEB} | set(_LEGACY_WEB)

_PROVIDERS = {
    "openai": OpenAIWebSearchProvider,
    "perplexity": PerplexityAgentProvider,
    "gemini": GeminiGroundingProvider,
    "claude": ClaudeWebSearchProvider,
    "deepseek": DeepSeekSearchProvider,
    "kimi": KimiSearchProvider,
    "openrouter": OpenRouterAnswerProvider,
}


def is_web_engine(engine: str) -> bool:
    return engine in WEB_ENGINES


def env_from_settings() -> dict[str, str]:
    from api.settings import settings

    return {
        "OPENAI_API_KEY": settings.openai_api_key,
        "PERPLEXITY_API_KEY": settings.perplexity_api_key,
        "GEMINI_API_KEY": settings.gemini_api_key,
        "GOOGLE_API_KEY": "",
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        "DEEPSEEK_API_KEY": settings.deepseek_api_key,
        "KIMI_API_KEY": settings.kimi_api_key,
        "MOONSHOT_API_KEY": "",
        "OPENROUTER_API_KEY": settings.openrouter_api_key,
        "QIANFAN_ACCESS_KEY": settings.qianfan_access_key,
        "QIANFAN_SECRET_KEY": settings.qianfan_secret_key,
    }


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_channels(db: Database) -> None:
    for spec in CHANNEL_SPECS:
        existing = db.fetch_one("SELECT channel_id FROM collection_channels WHERE channel_id = ?", (spec["id"],))
        if existing is None:
            concurrency = 1 if spec["kind"] == "web" else 2
            db.execute(
                """
                INSERT INTO collection_channels (channel_id, model, web_search, concurrency, rate_limit_rpm)
                VALUES (?, ?, 1, ?, 30)
                """,
                (spec["id"], spec.get("model") or "", concurrency),
            )


def _rows(db: Database) -> dict[str, dict]:
    _ensure_channels(db)
    return {row["channel_id"]: row for row in db.fetch_all("SELECT * FROM collection_channels")}


def _decrypt_blob(enc: str) -> dict:
    if not enc:
        return {}
    try:
        payload = json.loads(decrypt_text(enc))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _first_env(env: dict, names: list[str]) -> str:
    for name in names:
        value = (env.get(name) or "").strip()
        if value:
            return value
    return ""


def _effective(spec: dict, row: dict | None, env: dict) -> dict:
    stored = _decrypt_blob(row["api_key_enc"]) if row else {}
    if spec.get("dual"):
        access_env = _first_env(env, ["QIANFAN_ACCESS_KEY"])
        secret_env = _first_env(env, ["QIANFAN_SECRET_KEY"])
        access = access_env or str(stored.get("api_key") or "")
        secret = secret_env or str(stored.get("api_secret") or "")
        source = "env" if access_env or secret_env else ("stored" if access or secret else "")
        return {
            "api_key": access,
            "api_secret": secret,
            "key_last4": mask_last4(access),
            "secret_last4": mask_last4(secret),
            "key_source": source,
            "has_key": bool(access and secret),
        }
    env_value = _first_env(env, list(spec.get("env") or []))
    stored_value = str(stored.get("api_key") or "")
    value = env_value or stored_value
    return {
        "api_key": value,
        "api_secret": "",
        "key_last4": mask_last4(value),
        "secret_last4": "",
        "key_source": "env" if env_value else ("stored" if stored_value else ""),
        "has_key": bool(value),
    }


def _public_status(spec: dict, row: dict | None, effective: dict) -> str:
    if spec["kind"] == "web":
        if not row or not row.get("enabled"):
            return "未实现"
        last = (row or {}).get("last_status") or ""
        if last == "ok":
            return "已连接"
        if last == "unavailable":
            return "浏览器不可用"
        if last == "error":
            return "错误"
        return "已启用"
    if not effective["has_key"]:
        return "未配置"
    last = (row or {}).get("last_status") or ""
    if last == "ok":
        return "已连接"
    if last == "error":
        return "错误"
    return "未配置"


def _public(spec: dict, row: dict | None, env: dict) -> dict:
    effective = _effective(spec, row, env)
    row = row or {}
    model = row.get("model") or spec.get("model") or ""
    return {
        "id": spec["id"],
        "label": spec["label"],
        "engine": spec["engine"],
        "kind": spec["kind"],
        "phase": spec["phase"],
        "implemented": spec["kind"] in {"api", "web"},
        "env_vars": list(spec.get("env") or []),
        "dual_key": bool(spec.get("dual")),
        "enabled": bool(row.get("enabled")),
        "model": model,
        "web_search": bool(row.get("web_search", 1)),
        "region": row.get("region") or "",
        "language": row.get("language") or "",
        "concurrency": int(row.get("concurrency") or 2),
        "rate_limit_rpm": int(row.get("rate_limit_rpm") or 30),
        "budget_cap_usd": row.get("budget_cap_usd"),
        "session_note": row.get("session_note") or "",
        "timeout_seconds": int(row["timeout_seconds"]) if row.get("timeout_seconds") else (45 if spec["kind"] == "web" else None),
        "proxy_env": "GEO_BROWSER_PROXY" if spec["kind"] == "web" else "",
        "key_last4": effective["key_last4"],
        "secret_last4": effective["secret_last4"],
        "key_source": effective["key_source"],
        "has_key": effective["has_key"],
        "status": _public_status(spec, row, effective),
        "last_latency_ms": row.get("last_latency_ms"),
        "last_error": row.get("last_error") or "",
        "last_tested_at": row.get("last_tested_at"),
    }


def list_channels(db: Database, env: dict | None = None) -> list[dict]:
    env = env_from_settings() if env is None else env
    rows = _rows(db)
    return [_public(spec, rows.get(spec["id"]), env) for spec in CHANNEL_SPECS]


def _require_spec(channel_id: str) -> dict:
    spec = _BY_ID.get(channel_id)
    if spec is None:
        raise LookupError("channel")
    return spec


def update_channel(db: Database, channel_id: str, payload: ChannelUpdate, env: dict | None = None) -> dict:
    spec = _require_spec(channel_id)
    env = env_from_settings() if env is None else env
    rows = _rows(db)
    row = rows[channel_id]
    values: dict = {"updated_at": _now()}
    data = payload.model_dump(exclude_unset=True)
    if "enabled" in data and data["enabled"] is not None:
        values["enabled"] = int(bool(data["enabled"]))
    if data.get("model") is not None:
        values["model"] = data["model"].strip()
    if data.get("web_search") is not None:
        values["web_search"] = int(bool(data["web_search"]))
    if data.get("region") is not None:
        values["region"] = data["region"].strip()
    if data.get("language") is not None:
        values["language"] = data["language"].strip()
    if data.get("concurrency") is not None:
        if data["concurrency"] < 1 or data["concurrency"] > 32:
            raise ValueError("并发需在 1 到 32 之间")
        values["concurrency"] = data["concurrency"]
    if data.get("rate_limit_rpm") is not None:
        if data["rate_limit_rpm"] < 1 or data["rate_limit_rpm"] > 1000:
            raise ValueError("速率限制需在 1 到 1000 之间")
        values["rate_limit_rpm"] = data["rate_limit_rpm"]
    if "budget_cap_usd" in data:
        cap = data["budget_cap_usd"]
        if cap is not None and cap < 0:
            raise ValueError("单次预算上限不能为负数")
        values["budget_cap_usd"] = cap
    if data.get("session_note") is not None:
        note = data["session_note"].strip()
        if len(note) > 4000:
            raise ValueError("会话备注过长")
        values["session_note"] = note
    if data.get("timeout_seconds") is not None:
        timeout = int(data["timeout_seconds"])
        if timeout < 5 or timeout > 180:
            raise ValueError("超时需在 5 到 180 秒之间")
        values["timeout_seconds"] = timeout
    if data.get("clear_key"):
        values["api_key_enc"] = ""
        values["key_last4"] = ""
        values["secret_last4"] = ""
    elif data.get("api_key") or data.get("api_secret"):
        blob = _decrypt_blob(row["api_key_enc"])
        if data.get("api_key"):
            blob["api_key"] = str(data["api_key"]).strip()
        if data.get("api_secret"):
            blob["api_secret"] = str(data["api_secret"]).strip()
        if len(blob.get("api_key") or "") > 4000 or len(blob.get("api_secret") or "") > 4000:
            raise ValueError("密钥过长")
        try:
            values["api_key_enc"] = encrypt_text(json.dumps(blob, ensure_ascii=False))
        except SecretNotConfigured:
            raise
        values["key_last4"] = mask_last4(blob.get("api_key") or "")
        values["secret_last4"] = mask_last4(blob.get("api_secret") or "")
    assignments = ", ".join(f"{column} = ?" for column in values)
    db.execute(
        f"UPDATE collection_channels SET {assignments} WHERE channel_id = ?",
        (*values.values(), channel_id),
    )
    updated = db.fetch_one("SELECT * FROM collection_channels WHERE channel_id = ?", (channel_id,))
    return _public(spec, updated, env)


def _save_probe(db: Database, channel_id: str, status: str, latency: int | None, error: str) -> None:
    db.execute(
        """
        UPDATE collection_channels
        SET last_status = ?, last_latency_ms = ?, last_error = ?, last_tested_at = ?, updated_at = ?
        WHERE channel_id = ?
        """,
        (status, latency, error[:300], _now(), _now(), channel_id),
    )


def _safe_error(result, secrets: list[str]) -> str:
    extra = ""
    raw = result.raw_output if isinstance(result.raw_output, dict) else {}
    extra = str(raw.get("message") or raw.get("error") or "")[:180]
    text = " ".join(part for part in (result.error_code or result.status, extra) if part).strip()
    for secret in secrets:
        if secret:
            text = text.replace(secret, "****")
    return text[:300]


def probe_channel(db: Database, channel_id: str, env: dict | None = None, http_client=None) -> dict:
    spec = _require_spec(channel_id)
    env = env_from_settings() if env is None else env
    rows = _rows(db)
    row = rows[channel_id]
    if spec["kind"] == "web":
        if not row.get("enabled"):
            _save_probe(db, channel_id, "unimplemented", None, "网页通道未启用，未打开浏览器")
            fresh = db.fetch_one("SELECT * FROM collection_channels WHERE channel_id = ?", (channel_id,))
            return {"ok": False, "status": "未实现", "latency_ms": None, "error": "网页通道未启用，未打开浏览器", "channel": _public(spec, fresh, env)}
        available, detail = browser_runtime_status()
        if available:
            _save_probe(db, channel_id, "ok", None, "")
            fresh = db.fetch_one("SELECT * FROM collection_channels WHERE channel_id = ?", (channel_id,))
            return {"ok": True, "status": "已连接", "latency_ms": None, "error": "", "channel": _public(spec, fresh, env)}
        _save_probe(db, channel_id, "unavailable", None, detail)
        fresh = db.fetch_one("SELECT * FROM collection_channels WHERE channel_id = ?", (channel_id,))
        return {"ok": False, "status": "浏览器不可用", "latency_ms": None, "error": detail, "channel": _public(spec, fresh, env)}
    effective = _effective(spec, row, env)
    if not effective["has_key"]:
        _save_probe(db, channel_id, "unconfigured", None, "没有环境变量或已保存的密钥")
        fresh = db.fetch_one("SELECT * FROM collection_channels WHERE channel_id = ?", (channel_id,))
        return {"ok": False, "status": "未配置", "latency_ms": None, "error": "没有环境变量或已保存的密钥", "channel": _public(spec, fresh, env)}
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=25.0)
    model = row.get("model") or spec.get("model") or None
    try:
        if spec["id"] == "qianfan":
            provider = QianfanAnswerProvider(effective["api_key"], effective["api_secret"], client)
        else:
            provider = _PROVIDERS[spec["id"]](effective["api_key"], client, model)
        started = time.perf_counter()
        result = provider.run(
            spec["engine"],
            "Reply with the single word pong.",
            country=row.get("region") or "US",
            language=row.get("language") or "en-US",
            web_search=bool(row.get("web_search", 1)),
        )
        latency = int((time.perf_counter() - started) * 1000)
    finally:
        if owns_client:
            client.close()
    secrets = [effective["api_key"], effective["api_secret"]]
    if result.status == "ok":
        _save_probe(db, channel_id, "ok", latency, "")
        ok, status, error = True, "已连接", ""
    else:
        error = _safe_error(result, secrets)
        code = "unconfigured" if result.error_code == "missing_api_key" else "error"
        _save_probe(db, channel_id, code, latency, error)
        ok, status = False, "未配置" if code == "unconfigured" else "错误"
    fresh = db.fetch_one("SELECT * FROM collection_channels WHERE channel_id = ?", (channel_id,))
    public = _public(spec, fresh, env)
    return {"ok": ok, "status": status, "latency_ms": latency, "error": error, "channel": public}


def effective_provider_env(db: Database, base_env: dict) -> dict:
    """Environment variables win. Stored keys fill only the blanks."""
    merged = dict(base_env)
    rows = _rows(db)
    for spec in _API:
        row = rows.get(spec["id"])
        stored = _decrypt_blob(row["api_key_enc"]) if row else {}
        if spec.get("dual"):
            if not (merged.get("QIANFAN_ACCESS_KEY") or "").strip() and stored.get("api_key"):
                merged["QIANFAN_ACCESS_KEY"] = stored["api_key"]
            if not (merged.get("QIANFAN_SECRET_KEY") or "").strip() and stored.get("api_secret"):
                merged["QIANFAN_SECRET_KEY"] = stored["api_secret"]
            continue
        primary = spec["env"][0]
        if (merged.get(primary) or "").strip():
            continue
        if stored.get("api_key"):
            merged[primary] = stored["api_key"]
    return merged


def apply_channel_runtime(db: Database, providers: list) -> dict[str, dict]:
    rows = _rows(db)
    runtime: dict[str, dict] = {}
    for spec in CHANNEL_SPECS:
        row = rows.get(spec["id"])
        model = (row.get("model") if row and row.get("model") else spec.get("model")) or ""
        runtime[spec["engine"]] = {
            "web_search": True if row is None else bool(row.get("web_search", 1)),
            "region": (row.get("region") if row else "") or "",
            "language": (row.get("language") if row else "") or "",
            "model": model,
            "kind": spec["kind"],
        }
        if spec["kind"] != "api" or not model:
            continue
        for provider in providers:
            engines = getattr(provider, "engines", ())
            if spec["engine"] in engines and hasattr(provider, "model"):
                provider.model = model
    return runtime


def channel_settings_for_hash(db: Database, engines: list[str], env: dict | None = None) -> list[dict]:
    env = env_from_settings() if env is None else env
    rows = _rows(db)
    items = []
    for engine in sorted(set(engines)):
        spec = _BY_ENGINE.get(engine)
        if spec is None:
            items.append({"engine": engine})
            continue
        row = rows.get(spec["id"])
        effective = _effective(spec, row, env)
        items.append(
            {
                "id": spec["id"],
                "engine": engine,
                "enabled": int(row["enabled"]) if row else 0,
                "model": (row.get("model") if row and row.get("model") else spec.get("model")) or "",
                "web_search": int(row["web_search"]) if row else 1,
                "region": (row.get("region") if row else "") or "",
                "language": (row.get("language") if row else "") or "",
                "concurrency": int(row["concurrency"]) if row else 2,
                "rate_limit_rpm": int(row["rate_limit_rpm"]) if row else 30,
                "budget_cap_usd": row.get("budget_cap_usd") if row else None,
                "timeout_seconds": int(row["timeout_seconds"]) if row and row.get("timeout_seconds") else None,
                "key_last4": effective["key_last4"],
                "key_source": effective["key_source"],
            }
        )
    return items


def get_strategy(db: Database, project_id: int) -> dict:
    row = db.fetch_one("SELECT * FROM project_collection_strategies WHERE project_id = ?", (project_id,))
    if row is None:
        return {
            "project_id": project_id,
            "channels": [],
            "sample_count": 1,
            "cadence": "monthly",
            "web_sample_percent": 15,
        }
    return {
        "project_id": project_id,
        "channels": json.loads(row["channels_json"] or "[]"),
        "sample_count": int(row["sample_count"] or 1),
        "cadence": row["cadence"] or "monthly",
        "web_sample_percent": int(row["web_sample_percent"] if row["web_sample_percent"] is not None else 15),
    }


def strategy_web_percent(db: Database, project_id: int) -> int | None:
    row = db.fetch_one(
        "SELECT web_sample_percent FROM project_collection_strategies WHERE project_id = ?",
        (project_id,),
    )
    if row is None:
        return None
    return int(row["web_sample_percent"] if row["web_sample_percent"] is not None else 15)


def save_strategy(db: Database, project_id: int, payload: StrategyUpdate) -> dict:
    if payload.sample_count < 1 or payload.sample_count > 5:
        raise ValueError("每题采样次数需在 1 到 5 之间")
    if payload.web_sample_percent < 0 or payload.web_sample_percent > 100:
        raise ValueError("网页抽样比例需在 0 到 100 之间")
    if payload.cadence not in {"weekly", "monthly"}:
        raise ValueError("频率只支持 weekly 或 monthly")
    channels = json.dumps(list(payload.channels), ensure_ascii=False)
    existing = db.fetch_one("SELECT project_id FROM project_collection_strategies WHERE project_id = ?", (project_id,))
    if existing is None:
        db.execute(
            """
            INSERT INTO project_collection_strategies
                (project_id, channels_json, sample_count, cadence, web_sample_percent, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, channels, payload.sample_count, payload.cadence, payload.web_sample_percent, _now()),
        )
    else:
        db.execute(
            """
            UPDATE project_collection_strategies
            SET channels_json = ?, sample_count = ?, cadence = ?, web_sample_percent = ?, updated_at = ?
            WHERE project_id = ?
            """,
            (channels, payload.sample_count, payload.cadence, payload.web_sample_percent, _now(), project_id),
        )
    return get_strategy(db, project_id)


def estimate_budget(db: Database, project_id: int, payload: BudgetEstimateRequest) -> dict:
    question_set_id = payload.question_set_id
    if question_set_id is None:
        latest = db.fetch_one(
            "SELECT id FROM geo_question_sets WHERE project_id = ? ORDER BY id DESC LIMIT 1",
            (project_id,),
        )
        question_set_id = latest["id"] if latest else None
    question_count = 0
    if question_set_id is not None:
        counted = db.fetch_one("SELECT COUNT(*) AS n FROM geo_questions WHERE question_set_id = ?", (question_set_id,))
        question_count = int(counted["n"] if counted else 0)
    api_engines = [engine for engine in payload.engines if not is_web_engine(engine)]
    calls = question_count * payload.sample_count * len(api_engines)
    estimated = round(calls * API_UNIT_USD, 4)
    spent_row = db.fetch_one(
        "SELECT COALESCE(SUM(COALESCE(actual_cost_usd, est_cost_usd, 0)), 0) AS n FROM budget_ledger WHERE project_id = ?",
        (project_id,),
    )
    spent = round(float(spent_row["n"] if spent_row else 0), 4)
    rows = _rows(db)
    caps = []
    for engine in api_engines:
        spec = _BY_ENGINE.get(engine)
        if spec is None:
            continue
        row = rows.get(spec["id"])
        cap = row.get("budget_cap_usd") if row else None
        if cap is not None:
            caps.append({"engine": engine, "budget_cap_usd": cap})
    over = [item for item in caps if estimated > float(item["budget_cap_usd"])]
    return {
        "estimated_cost_usd": estimated,
        "spent_usd": spent,
        "question_count": question_count,
        "sample_count": payload.sample_count,
        "api_calls": calls,
        "unit_usd": API_UNIT_USD,
        "budget_caps": caps,
        "over_cap": bool(over),
        "note": "按每次官方 API 调用 0.01 美元粗估。网页抽样不产生费用。已花费来自预算流水。",
    }


def select_sampled_questions(questions: list[dict], percent: int) -> list[dict]:
    """Core questions are D-type plus comparison, alternative, and brand K questions."""
    if percent <= 0 or not questions:
        return []
    core = [
        question
        for question in questions
        if (question.get("probe_type") or "K") == "D" or (question.get("intent") or "") in {"对比", "替代", "品牌"}
    ]
    pool = core or list(questions)
    count = math.ceil(len(pool) * percent / 100)
    if count <= 0:
        return []
    return sorted(pool, key=lambda question: question["id"])[:count]


def _engine_slug(engine: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", engine).strip("-")
    return slug or "web"


def _insert_web_attempt(
    db: Database,
    *,
    run_id: int,
    question_id: int,
    engine: str,
    baseline: dict,
    status: str,
    error_code: str,
    text: str,
    payload: dict,
    percent: int,
) -> None:
    request = {
        "engine": engine,
        "provider": "browser",
        "planned_web_sample": True,
        "sampled": True,
        "web_sample_percent": percent,
        "country": baseline.get("region") or "",
        "language": baseline.get("language") or "",
        "web_search": False,
        "sample_index": 0,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256((raw + "\n" + (text or "")).encode()).hexdigest()
    db.execute(
        """
        INSERT INTO geo_attempts (
            response_id, geo_run_id, question_id, platform, provider_id, engine,
            attempt_no, sample_index, status, error_code, access, request_params_json,
            raw_response, raw_payload_json, payload_sha256, web_queries_json,
            model_version, config_hash, cost_usd
        ) VALUES (
            NULL, ?, ?, ?, 'browser', ?, 1, 0, ?, ?, 'scraped', ?,
            ?, ?, ?, '[]', '', ?, NULL
        )
        """,
        (
            run_id,
            question_id,
            engine,
            engine,
            status,
            error_code,
            json.dumps(request, ensure_ascii=False),
            text or "",
            raw,
            digest,
            baseline.get("config_hash") or "",
        ),
    )


def record_planned_web_samples(db: Database, run_id: int, baseline: dict, questions: list[dict]) -> int:
    """Sample core questions for web engines.

    Disabled channels stay on the browser_stub plan so existing batches do not
    launch a browser. Enabled channels run one at a time. A missing browser is
    stored as browser_unavailable and does not abort the batch.
    """
    snapshot = json.loads(baseline.get("snapshot_json") or "{}")
    percent = int(snapshot.get("web_sample_percent") or 0)
    picked = select_sampled_questions(questions, percent)
    if not picked:
        return 0
    engines = list(snapshot.get("web_engines") or []) or ["ChatGPT 网页"]
    rows = _rows(db)
    saved = 0
    for question in picked:
        for engine in engines:
            spec = _BY_ENGINE.get(engine)
            row = rows.get(spec["id"]) if spec else None
            enabled = bool(spec and spec["kind"] == "web" and row and row.get("enabled"))
            if not enabled:
                _insert_web_attempt(
                    db,
                    run_id=run_id,
                    question_id=question["id"],
                    engine=engine,
                    baseline=baseline,
                    status="skipped",
                    error_code="browser_stub",
                    text="",
                    percent=percent,
                    payload={
                        "engine": engine,
                        "provider": "browser",
                        "planned_web_sample": True,
                        "sampled": True,
                        "web_sample_percent": percent,
                        "message": "网页通道未启用，本次只记录计划抽样，没有打开网页。",
                        "country": baseline.get("region") or "",
                        "language": baseline.get("language") or "",
                    },
                )
                saved += 1
                continue
            timeout = int(row.get("timeout_seconds") or 45)
            artifact_dir = Path(os.environ.get("GEO_ARTIFACT_ROOT") or "data/artifacts") / str(run_id) / f"{question['id']}-{_engine_slug(engine)}"
            try:
                result = collect_browser_answer(
                    engine,
                    question.get("question") or "",
                    country=baseline.get("region") or "",
                    language=baseline.get("language") or "",
                    timeout=timeout,
                    proxy=os.environ.get("GEO_BROWSER_PROXY") or "",
                    session_note=row.get("session_note") or "",
                    artifact_dir=artifact_dir,
                )
            except Exception as exc:
                result = ScrapeResult(
                    provider_id="browser",
                    engine=engine,
                    access="scraped",
                    status="skipped",
                    error_code="browser_unavailable",
                    text="",
                    raw_output={"message": str(exc)[:200]},
                )
            raw_output = result.raw_output if isinstance(result.raw_output, dict) else {}
            _insert_web_attempt(
                db,
                run_id=run_id,
                question_id=question["id"],
                engine=engine,
                baseline=baseline,
                status=result.status or "skipped",
                error_code=result.error_code or "",
                text=result.text or "",
                percent=percent,
                payload={
                    "engine": engine,
                    "provider": "browser",
                    "planned_web_sample": True,
                    "sampled": True,
                    "web_sample_percent": percent,
                    "message": str(raw_output.get("message") or "")[:300],
                    "implementation": raw_output.get("implementation") or "",
                    "fallback": raw_output.get("fallback") or "",
                    "html_path": raw_output.get("html_path") or "",
                    "text_path": raw_output.get("text_path") or "",
                    "screenshot_path": raw_output.get("screenshot_path") or "",
                    "screenshot_error": raw_output.get("screenshot_error") or "",
                    "session_note_applied": bool(raw_output.get("session_note_applied")),
                    "country": baseline.get("region") or "",
                    "language": baseline.get("language") or "",
                },
            )
            saved += 1
    return saved


def collection_method_note(db: Database, project_id: int) -> str:
    run = db.fetch_one(
        "SELECT id, baseline_id FROM geo_runs WHERE project_id = ? ORDER BY run_at DESC, id DESC LIMIT 1",
        (project_id,),
    )
    if run is None:
        return "本期还没有采集记录，无法区分实际走过的 API 通道和网页抽样通道。"
    rows = db.fetch_all(
        "SELECT engine, access, error_code, status FROM geo_attempts WHERE geo_run_id = ? ORDER BY id",
        (run["id"],),
    )
    api: list[str] = []
    web: list[str] = []
    executed = 0
    unavailable = 0
    for row in rows:
        engine = row["engine"]
        if row["access"] == "scraped" or row["error_code"] in {"browser_stub", "browser_unavailable"} or is_web_engine(engine):
            if engine not in web:
                web.append(engine)
            if row["access"] == "scraped" and row["status"] == "ok":
                executed += 1
            if row["error_code"] == "browser_unavailable":
                unavailable += 1
        elif engine not in api:
            api.append(engine)
    percent = None
    if run.get("baseline_id"):
        baseline = db.fetch_one("SELECT snapshot_json FROM geo_baselines WHERE id = ?", (run["baseline_id"],))
        if baseline:
            try:
                percent = json.loads(baseline["snapshot_json"] or "{}").get("web_sample_percent")
            except json.JSONDecodeError:
                percent = None
    api_text = "、".join(api) if api else "无"
    web_text = "、".join(web) if web else "无"
    percent_text = (
        f"网页抽样核对比例为 {percent}%，只作用于核心问题。"
        if percent
        else "本次快照没有设置网页抽样比例。"
    )
    if executed:
        web_state = f"其中 {executed} 条网页抽样已用浏览器采集骨架执行，截图失败不会单独让该条失败。"
    elif unavailable:
        web_state = "网页通道已启用，但浏览器不可用，相关尝试记为 browser_unavailable，批次继续。"
    else:
        web_state = "未启用的网页通道只记录计划抽样，不能当成用户在网页或 App 里看到的结果。"
    return (
        f"通道区分：API 通道（含缺少密钥而模拟跳过的官方接口）为 {api_text}。"
        f"网页抽样通道为 {web_text}。"
        f"{web_state}"
        f"{percent_text}"
    )
