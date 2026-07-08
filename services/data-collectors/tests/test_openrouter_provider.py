import httpx
import pytest

from data_collectors.errors import ProviderError
from data_collectors.providers.openrouter import OpenRouterClient


def test_openrouter_query_returns_message_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "1. Acme CRM\nSource: https://acme.com"}}]},
        )

    client = OpenRouterClient(
        api_key="token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.query("best crm for factories")
    assert result["provider"] == "openrouter"
    assert "Acme CRM" in result["content"]


def test_openrouter_query_raises_retryable_error_on_429():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    client = OpenRouterClient(
        api_key="token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderError) as exc:
        client.query("best crm for factories")

    assert exc.value.provider == "openrouter"
    assert exc.value.retryable is True
