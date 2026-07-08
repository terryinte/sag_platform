from __future__ import annotations

import httpx

from data_collectors.errors import ProviderError


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-4.1-mini",
        base_url: str = "https://openrouter.ai/api/v1",
        http_client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client or httpx.Client(timeout=30.0)
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def query(self, prompt: str) -> dict:
        response = self.http_client.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            },
            headers=self.headers,
        )
        if response.status_code == 429:
            raise ProviderError("openrouter", "geo_query_batch", True, "rate limited")
        if response.status_code >= 400:
            raise ProviderError("openrouter", "geo_query_batch", False, f"http {response.status_code}")

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("openrouter", "geo_query_batch", False, "unexpected response shape")
        return {"provider": "openrouter", "content": choices[0]["message"]["content"]}
