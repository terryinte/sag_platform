from data_collectors.collectors.geo import collect_geo_input
from data_collectors.errors import ProviderError
from data_collectors.models import GeoQuerySpec


class FakeOpenRouterClient:
    def query(self, prompt):
        return {"provider": "openrouter", "content": "1. Acme CRM\nSource: https://acme.com"}


class FailingQianfanClient:
    def query(self, prompt):
        raise ProviderError("qianfan", "geo_query_batch", True, "rate limited")


def test_collect_geo_input_returns_partial_success_and_error():
    geo_input, errors = collect_geo_input(
        brand_name="Acme",
        domain="acme.com",
        queries=[GeoQuerySpec(query="best crm for factories")],
        openrouter_client=FakeOpenRouterClient(),
        qianfan_client=FailingQianfanClient(),
    )
    assert len(geo_input.mention_results) == 1
    assert errors[0].provider == "qianfan"
