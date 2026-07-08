from api.adapters import (
    analyze_response_to_dict,
    collect_payload_to_dict,
    collect_request_to_inputs,
)
from api.models import CollectRequest, GeoQueryInput, KeywordSpecInput
from analysis_engine.models import AeoInput, CompositeReport, GeoInput, Recommendation, ScoreBreakdown, SeoInput
from data_collectors.models import CollectionError, CollectionPayload, GeoQuerySpec, KeywordSpec


def test_collect_request_to_inputs_maps_fields():
    request = CollectRequest(
        domain="example.com",
        url="https://example.com",
        brand_name="Acme",
        keywords=[KeywordSpecInput(keyword="best crm", engine="google")],
        geo_queries=[GeoQueryInput(query="best crm for factories", engine_hint="global")],
    )
    keywords, geo_queries = collect_request_to_inputs(request)
    assert keywords == [KeywordSpec(keyword="best crm", engine="google")]
    assert geo_queries == [GeoQuerySpec(query="best crm for factories", engine_hint="global")]


def test_collect_payload_to_dict_serializes_collection_payload():
    payload = CollectionPayload(
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
    result = collect_payload_to_dict(payload)
    assert result["domain"] == "example.com"
    assert result["errors"][0]["provider"] == "openrouter"


def test_analyze_response_to_dict_serializes_report():
    report = CompositeReport(
        domain="example.com",
        overall_score=80.0,
        dimension_scores={
            "seo": ScoreBreakdown(dimension="seo", score=80.0, data_complete=True),
        },
        recommendations=[Recommendation(priority="low", dimension="seo", title="t", description="d")],
    )
    result = analyze_response_to_dict(report, [{"provider": "openrouter"}])
    assert result["domain"] == "example.com"
    assert result["recommendations"][0]["dimension"] == "seo"
    assert result["collection_errors"][0]["provider"] == "openrouter"
