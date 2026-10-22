"""Official-API answer collectors behind one interface.

Missing credentials return a skipped mock result. Transport and parse failures
return an error result. Callers can persist either outcome; ``run`` does not raise.

P1 browser collection is only a stub. It does not launch Playwright or Camoufox.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol

import httpx

from data_collectors.errors import ProviderError
from data_collectors.providers.extractors import (
    extract_chat_completions,
    extract_claude_response,
    extract_gemini_response,
    extract_openai_response,
    extract_perplexity_response,
)
from data_collectors.providers.openrouter import OpenRouterClient
from data_collectors.providers.qianfan import QianfanClient


@dataclass
class ScrapeResult:
    provider_id: str
    engine: str
    access: str
    status: str
    error_code: str = ""
    text: str = ""
    raw_output: dict = field(default_factory=dict)
    web_queries: list[str] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    model_version: str | None = None
    cost_usd: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


class AnswerProvider(Protocol):
    id: str
    access: str

    def supports(self, engine: str) -> bool: ...

    def run(
        self,
        engine: str,
        prompt: str,
        *,
        country: str = "US",
        language: str = "en-US",
        web_search: bool = True,
    ) -> ScrapeResult: ...


def _mock_text(env_key: str, engine: str, prompt: str) -> str:
    return (
        f"[模拟回答·缺少密钥] 未配置 {env_key}，{engine} 本次没有发起真实联网请求。"
        f"问题：{prompt[:180]}"
    )


class _HTTPProvider:
    id = ""
    access = "api"
    engines: tuple[str, ...] = ()
    env_key = ""
    default_model = ""

    def __init__(self, api_key: str = "", http_client: httpx.Client | None = None, model: str | None = None) -> None:
        self.api_key = api_key or ""
        self.http = http_client or httpx.Client(timeout=45.0)
        self.model = model or self.default_model

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def supports(self, engine: str) -> bool:
        return engine in self.engines

    def run(
        self,
        engine: str,
        prompt: str,
        *,
        country: str = "US",
        language: str = "en-US",
        web_search: bool = True,
    ) -> ScrapeResult:
        if not self.configured:
            return ScrapeResult(
                provider_id=self.id,
                engine=engine,
                access="mock",
                status="skipped",
                error_code="missing_api_key",
                text=_mock_text(self.env_key, engine, prompt),
                raw_output={"mock": True, "reason": "missing_api_key", "env": self.env_key},
                model_version=None,
            )
        try:
            result = self._call(engine, prompt, country=country, language=language, web_search=web_search)
        except Exception as exc:  # noqa: BLE001 - collectors must not crash a batch
            return ScrapeResult(
                provider_id=self.id,
                engine=engine,
                access="api",
                status="error",
                error_code="provider_error",
                raw_output={"error": type(exc).__name__, "message": str(exc)[:300]},
                model_version=self.model,
            )
        return result

    def _call(self, engine: str, prompt: str, *, country: str, language: str, web_search: bool) -> ScrapeResult:
        raise NotImplementedError

    def _error(self, engine: str, code: str, raw: dict) -> ScrapeResult:
        return ScrapeResult(
            provider_id=self.id,
            engine=engine,
            access="api",
            status="error",
            error_code=code,
            raw_output=raw,
            model_version=self.model,
        )

    def _ok(
        self,
        engine: str,
        text: str,
        raw: dict,
        citations: list[dict],
        queries: list[str],
        model_version: str | None = None,
    ) -> ScrapeResult:
        if not text.strip():
            return self._error(engine, "empty_output", raw)
        return ScrapeResult(
            provider_id=self.id,
            engine=engine,
            access="api",
            status="ok",
            text=text,
            raw_output=raw,
            citations=citations,
            web_queries=queries,
            model_version=model_version or self.model,
        )

    def _read_json(self, response: httpx.Response) -> dict | None:
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            return None
        return payload if isinstance(payload, dict) else None


class OpenAIWebSearchProvider(_HTTPProvider):
    id = "openai"
    engines = ("ChatGPT",)
    env_key = "OPENAI_API_KEY"
    default_model = "gpt-4.1-mini"

    def _call(self, engine: str, prompt: str, *, country: str, language: str, web_search: bool) -> ScrapeResult:
        body: dict = {"model": self.model, "input": prompt}
        if web_search:
            body["tools"] = [{"type": "web_search"}]
        response = self.http.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=body,
        )
        payload = self._read_json(response) or {}
        if response.status_code >= 400:
            return self._error(engine, f"http_{response.status_code}", {"http_status": response.status_code})
        text, citations, queries = extract_openai_response(payload)
        return self._ok(engine, text, payload, citations, queries, payload.get("model"))


class PerplexityAgentProvider(_HTTPProvider):
    id = "perplexity"
    engines = ("Perplexity",)
    env_key = "PERPLEXITY_API_KEY"
    default_model = "sonar"

    def _call(self, engine: str, prompt: str, *, country: str, language: str, web_search: bool) -> ScrapeResult:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = self.http.post(
            "https://api.perplexity.ai/v1/agent",
            headers=headers,
            json={
                "model": self.model,
                "input": prompt,
                "tools": [{"type": "web_search"}] if web_search else [],
            },
        )
        payload = self._read_json(response) or {}
        if response.status_code == 404:
            response = self.http.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json={"model": self.model, "messages": [{"role": "user", "content": prompt}]},
            )
            payload = self._read_json(response) or {}
            payload["_endpoint"] = "chat/completions"
        if response.status_code >= 400:
            return self._error(engine, f"http_{response.status_code}", {"http_status": response.status_code})
        text, citations, queries = extract_perplexity_response(payload)
        return self._ok(engine, text, payload, citations, queries, payload.get("model"))


class GeminiGroundingProvider(_HTTPProvider):
    id = "gemini"
    engines = ("Gemini",)
    env_key = "GEMINI_API_KEY"
    default_model = "gemini-2.0-flash"

    def _call(self, engine: str, prompt: str, *, country: str, language: str, web_search: bool) -> ScrapeResult:
        body: dict = {"contents": [{"parts": [{"text": prompt}]}]}
        if web_search:
            body["tools"] = [{"google_search": {}}]
        response = self.http.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            params={"key": self.api_key},
            json=body,
        )
        payload = self._read_json(response) or {}
        if response.status_code >= 400:
            return self._error(engine, f"http_{response.status_code}", {"http_status": response.status_code})
        text, citations, queries = extract_gemini_response(payload)
        return self._ok(engine, text, payload, citations, queries, self.model)


class ClaudeWebSearchProvider(_HTTPProvider):
    id = "anthropic"
    engines = ("Claude",)
    env_key = "ANTHROPIC_API_KEY"
    default_model = "claude-sonnet-4-5"

    def _call(self, engine: str, prompt: str, *, country: str, language: str, web_search: bool) -> ScrapeResult:
        body: dict = {
            "model": self.model,
            "max_tokens": 1200,
            "messages": [{"role": "user", "content": prompt}],
        }
        if web_search:
            body["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]
        response = self.http.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
        )
        payload = self._read_json(response) or {}
        if response.status_code >= 400:
            return self._error(engine, f"http_{response.status_code}", {"http_status": response.status_code})
        text, citations, queries = extract_claude_response(payload)
        return self._ok(engine, text, payload, citations, queries, payload.get("model") or self.model)


class _ChatSearchProvider(_HTTPProvider):
    """Chat-completions client plus an optional official search endpoint."""

    base_url = ""
    search_path = ""

    def _call(self, engine: str, prompt: str, *, country: str, language: str, web_search: bool) -> ScrapeResult:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        search_payload: dict = {}
        queries: list[str] = []
        search_citations: list[dict] = []
        if web_search and self.search_path:
            search_response = self.http.post(
                self.base_url.rstrip("/") + self.search_path,
                headers=headers,
                json={"query": prompt, "count": 5},
            )
            search_payload = self._read_json(search_response) or {}
            _, search_citations, queries = extract_chat_completions(search_payload)
            if not queries:
                queries = [prompt[:120]]
        response = self.http.post(
            self.base_url.rstrip("/") + "/chat/completions",
            headers=headers,
            json={"model": self.model, "messages": [{"role": "user", "content": prompt}]},
        )
        payload = self._read_json(response) or {}
        if response.status_code >= 400:
            return self._error(engine, f"http_{response.status_code}", {"http_status": response.status_code})
        text, citations, extra_queries = extract_chat_completions(payload)
        merged = citations or search_citations
        raw = {"chat": payload, "search": search_payload}
        return self._ok(engine, text, raw, merged, queries or extra_queries, payload.get("model") or self.model)


class DeepSeekSearchProvider(_ChatSearchProvider):
    id = "deepseek"
    engines = ("DeepSeek",)
    env_key = "DEEPSEEK_API_KEY"
    default_model = "deepseek-chat"
    base_url = "https://api.deepseek.com"
    search_path = "/v1/tools/search"


class KimiSearchProvider(_ChatSearchProvider):
    id = "kimi"
    engines = ("Kimi",)
    env_key = "KIMI_API_KEY"
    default_model = "moonshot-v1-auto"
    base_url = "https://api.moonshot.cn/v1"
    search_path = "/tools/search"


class OpenRouterAnswerProvider(_HTTPProvider):
    """Reuse the existing OpenRouter client. Access is API, not a consumer UI."""

    id = "openrouter"
    engines = ("OpenRouter",)
    env_key = "OPENROUTER_API_KEY"
    default_model = "openai/gpt-4.1-mini"

    def _call(self, engine: str, prompt: str, *, country: str, language: str, web_search: bool) -> ScrapeResult:
        client = OpenRouterClient(api_key=self.api_key, model=self.model, http_client=self.http)
        try:
            result = client.query(prompt)
        except ProviderError as exc:
            return self._error(engine, "provider_error", {"message": str(exc)[:300]})
        return self._ok(engine, result.get("content") or "", {"provider": "openrouter"}, [], [], self.model)


class QianfanAnswerProvider:
    """Reuse the existing Qianfan client for 文心 / 千帆 chat."""

    id = "qianfan"
    access = "api"
    engines = ("文心", "文心一言", "通义千问")
    env_key = "QIANFAN_ACCESS_KEY"

    def __init__(
        self,
        access_key: str = "",
        secret_key: str = "",
        http_client: httpx.Client | None = None,
    ) -> None:
        self.access_key = access_key or ""
        self.secret_key = secret_key or ""
        self.http = http_client or httpx.Client(timeout=45.0)

    @property
    def configured(self) -> bool:
        return bool(self.access_key and self.secret_key)

    def supports(self, engine: str) -> bool:
        return engine in self.engines

    def run(
        self,
        engine: str,
        prompt: str,
        *,
        country: str = "CN",
        language: str = "zh-CN",
        web_search: bool = True,
    ) -> ScrapeResult:
        if not self.configured:
            return ScrapeResult(
                provider_id=self.id,
                engine=engine,
                access="mock",
                status="skipped",
                error_code="missing_api_key",
                text=_mock_text(self.env_key, engine, prompt),
                raw_output={"mock": True, "reason": "missing_api_key", "env": self.env_key},
            )
        client = QianfanClient(access_key=self.access_key, secret_key=self.secret_key, http_client=self.http)
        try:
            result = client.query(prompt)
        except Exception as exc:  # noqa: BLE001
            return ScrapeResult(
                provider_id=self.id,
                engine=engine,
                access="api",
                status="error",
                error_code="provider_error",
                raw_output={"error": type(exc).__name__, "message": str(exc)[:300]},
            )
        text = result.get("content") or ""
        if not str(text).strip():
            return ScrapeResult(
                provider_id=self.id,
                engine=engine,
                access="api",
                status="error",
                error_code="empty_output",
                raw_output={"provider": "qianfan"},
            )
        return ScrapeResult(
            provider_id=self.id,
            engine=engine,
            access="api",
            status="ok",
            text=str(text),
            raw_output={"provider": "qianfan"},
            model_version="qianfan-chat",
        )


class BrowserCollectorStub:
    """P1 interface stub. Real Playwright + Camoufox collection is not implemented."""

    id = "browser"
    access = "scraped"
    engines = (
        "ChatGPT 网页",
        "Perplexity 网页",
        "Gemini 网页",
        "豆包",
        "元宝",
        "Kimi 网页",
        "Google AI 概览",
        "Google AI Mode",
        "Copilot",
    )
    configured = True

    def supports(self, engine: str) -> bool:
        return engine in self.engines

    def run(
        self,
        engine: str,
        prompt: str,
        *,
        country: str = "US",
        language: str = "en-US",
        web_search: bool = True,
    ) -> ScrapeResult:
        return ScrapeResult(
            provider_id=self.id,
            engine=engine,
            access="scraped",
            status="skipped",
            error_code="browser_stub",
            text="",
            raw_output={
                "implementation": "playwright+camoufox",
                "status": "stub",
                "message": "P1 浏览器采集只保留接口，尚未执行页面自动化。",
                "country": country,
                "language": language,
                "web_search": web_search,
                "prompt_excerpt": prompt[:120],
            },
        )


def build_answer_providers(env: dict | None = None, http_client: httpx.Client | None = None) -> list:
    env = env or {}
    gemini_key = env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY") or ""
    kimi_key = env.get("KIMI_API_KEY") or env.get("MOONSHOT_API_KEY") or ""
    return [
        OpenAIWebSearchProvider(env.get("OPENAI_API_KEY", ""), http_client),
        PerplexityAgentProvider(env.get("PERPLEXITY_API_KEY", ""), http_client),
        GeminiGroundingProvider(gemini_key, http_client),
        ClaudeWebSearchProvider(env.get("ANTHROPIC_API_KEY", ""), http_client),
        DeepSeekSearchProvider(env.get("DEEPSEEK_API_KEY", ""), http_client),
        KimiSearchProvider(kimi_key, http_client),
        OpenRouterAnswerProvider(env.get("OPENROUTER_API_KEY", ""), http_client),
        QianfanAnswerProvider(env.get("QIANFAN_ACCESS_KEY", ""), env.get("QIANFAN_SECRET_KEY", ""), http_client),
        BrowserCollectorStub(),
    ]


def resolve_provider(providers: list, engine: str):
    matches = [provider for provider in providers if provider.supports(engine)]
    if not matches:
        return None
    configured = [provider for provider in matches if getattr(provider, "configured", False)]
    return (configured or matches)[0]
