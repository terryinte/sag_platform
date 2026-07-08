from analysis_engine.models import AeoInput, GeoInput, SeoInput

from data_collectors.collectors.pipeline import build_collection_payload, run_collection_pipeline
from data_collectors.errors import ProviderError
from data_collectors.models import CollectionError, GeoQuerySpec, KeywordSpec


def test_build_collection_payload_keeps_partial_failures():
    payload = build_collection_payload(
        domain="example.com",
        seo=SeoInput(domain="example.com"),
        aeo=AeoInput(domain="example.com"),
        geo=GeoInput(brand_name="Acme", domain="example.com"),
        errors=[
            CollectionError(
                provider="openrouter",
                operation="geo_query_batch",
                retryable=True,
                message="rate limited",
            )
        ],
    )
    assert payload.domain == "example.com"
    assert payload.geo is not None
    assert payload.errors[0].provider == "openrouter"


class WorkingDataForSEOClient:
    def post(self, path, payload):
        return [{"keyword": payload[0]["keyword"], "ranked_serp_element": {"position": 1}, "search_volume": 1000}]


class FailingOpenRouterClient:
    def query(self, prompt):
        raise ProviderError("openrouter", "geo_query_batch", True, "rate limited")


class WorkingQianfanClient:
    def query(self, prompt):
        return {"provider": "qianfan", "content": "1. Acme CRM\nSource: https://acme.com"}


def test_run_collection_pipeline_keeps_partial_geo_results():
    payload = run_collection_pipeline(
        domain="example.com",
        brand_name="Acme",
        keywords=[KeywordSpec(keyword="best crm", engine="google")],
        geo_queries=[GeoQuerySpec(query="best crm for factories")],
        dataforseo_client=WorkingDataForSEOClient(),
        openrouter_client=FailingOpenRouterClient(),
        qianfan_client=WorkingQianfanClient(),
    )
    assert payload.seo is not None
    assert payload.geo is not None
    assert payload.errors[0].provider == "openrouter"
