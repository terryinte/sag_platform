import httpx
import pytest

from data_collectors.errors import ProviderError
from data_collectors.providers.qianfan import QianfanClient


def test_qianfan_query_returns_message_text():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/2.0/token"):
            return httpx.Response(200, json={"access_token": "access-token"})
        return httpx.Response(200, json={"result": "1. Acme CRM\n来源: https://acme.com"})

    client = QianfanClient(
        access_key="ak",
        secret_key="sk",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.query("best crm for factories")
    assert result["provider"] == "qianfan"
    assert "Acme CRM" in result["content"]


def test_qianfan_query_raises_provider_error_on_bad_token_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error_description": "invalid client"})

    client = QianfanClient(
        access_key="ak",
        secret_key="sk",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderError) as exc:
        client.query("best crm for factories")

    assert exc.value.provider == "qianfan"
    assert exc.value.operation == "oauth_token"
