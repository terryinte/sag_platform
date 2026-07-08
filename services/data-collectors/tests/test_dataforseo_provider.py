import httpx
import pytest

from data_collectors.errors import ProviderError
from data_collectors.providers.dataforseo import DataForSEOClient


def test_dataforseo_post_returns_task_result():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"tasks": [{"result": [{"keyword": "best crm", "ranked_serp_element": {"position": 2}}]}]},
        )

    client = DataForSEOClient(
        login="login",
        password="password",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.post("/v3/serp/google/organic/live/advanced", [{"keyword": "best crm"}])
    assert result == [{"keyword": "best crm", "ranked_serp_element": {"position": 2}}]


def test_dataforseo_post_raises_provider_error_on_auth_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status_message": "auth failed"})

    client = DataForSEOClient(
        login="login",
        password="password",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderError) as exc:
        client.post("/v3/serp/google/organic/live/advanced", [{"keyword": "best crm"}])

    assert exc.value.provider == "dataforseo"
    assert exc.value.retryable is False
