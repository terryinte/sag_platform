from __future__ import annotations

from base64 import b64encode

import httpx

from data_collectors.errors import ProviderError


class DataForSEOClient:
    def __init__(
        self,
        login: str,
        password: str,
        base_url: str = "https://api.dataforseo.com",
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client or httpx.Client(timeout=30.0)
        token = b64encode(f"{login}:{password}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}"}

    def post(self, path: str, payload: list[dict]) -> list[dict]:
        response = self.http_client.post(
            f"{self.base_url}{path}",
            json=payload,
            headers=self.headers,
        )
        if response.status_code == 401:
            raise ProviderError("dataforseo", "post", False, "authentication failed")
        if response.status_code >= 400:
            raise ProviderError("dataforseo", "post", True, f"http {response.status_code}")

        data = response.json()
        tasks = data.get("tasks") or []
        if not tasks or "result" not in tasks[0]:
            raise ProviderError("dataforseo", "post", False, "unexpected response shape")
        return tasks[0]["result"]
