from __future__ import annotations

from urllib.parse import urlencode

import httpx

from data_collectors.errors import ProviderError


class QianfanClient:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        token_url: str = "https://aip.baidubce.com/oauth/2.0/token",
        chat_url: str = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions",
        http_client: httpx.Client | None = None,
    ) -> None:
        self.access_key = access_key
        self.secret_key = secret_key
        self.token_url = token_url
        self.chat_url = chat_url
        self.http_client = http_client or httpx.Client(timeout=30.0)

    def _fetch_token(self) -> str:
        response = self.http_client.post(
            self.token_url,
            params={
                "grant_type": "client_credentials",
                "client_id": self.access_key,
                "client_secret": self.secret_key,
            },
        )
        if response.status_code >= 400:
            raise ProviderError("qianfan", "oauth_token", False, "token fetch failed")
        token = response.json().get("access_token")
        if not token:
            raise ProviderError("qianfan", "oauth_token", False, "missing access token")
        return token

    def query(self, prompt: str) -> dict:
        token = self._fetch_token()
        response = self.http_client.post(
            f"{self.chat_url}?{urlencode({'access_token': token})}",
            json={"messages": [{"role": "user", "content": prompt}]},
        )
        if response.status_code >= 400:
            raise ProviderError("qianfan", "geo_query_batch", False, f"http {response.status_code}")
        result = response.json().get("result")
        if not result:
            raise ProviderError("qianfan", "geo_query_batch", False, "unexpected response shape")
        return {"provider": "qianfan", "content": result}
