from api.models import AnalyzeRequest, CollectRequest, GeoQueryInput, KeywordSpecInput
from api.services import analyze_service, collect_service
from data_collectors.models import CollectionError, CollectionPayload


def test_collect_service_returns_serialized_payload(monkeypatch):
    request = CollectRequest(
        domain="example.com",
        url="https://example.com",
        brand_name="Acme",
        keywords=[KeywordSpecInput(keyword="best crm", engine="google")],
        geo_queries=[GeoQueryInput(query="best crm for factories")],
    )
    monkeypatch.setattr(
        "api.services._build_collection_payload",
        lambda req: CollectionPayload(domain=req.domain, seo=None, aeo=None, geo=None, errors=[]),
    )

    result = collect_service(request)
    assert result["domain"] == "example.com"
    assert result["errors"] == []


def test_analyze_service_returns_report(monkeypatch):
    request = AnalyzeRequest(
        domain="example.com",
        url="https://example.com",
        brand_name="Acme",
        keywords=[],
        geo_queries=[],
    )
    monkeypatch.setattr(
        "api.services._build_collection_payload",
        lambda req: CollectionPayload(domain=req.domain, seo=None, aeo=None, geo=None, errors=[]),
    )

    result = analyze_service(request)
    assert result["domain"] == "example.com"
    assert "dimensions" in result


def test_analyze_service_preserves_collection_errors(monkeypatch):
    request = AnalyzeRequest(
        domain="example.com",
        url="https://example.com",
        brand_name="Acme",
        keywords=[],
        geo_queries=[],
    )
    monkeypatch.setattr(
        "api.services._build_collection_payload",
        lambda req: CollectionPayload(
            domain=req.domain,
            seo=None,
            aeo=None,
            geo=None,
            errors=[
                CollectionError(
                    provider="openrouter",
                    operation="geo_query_batch",
                    retryable=True,
                    message="rate limited",
                )
            ],
        ),
    )

    result = analyze_service(request)
    assert result["collection_errors"][0]["provider"] == "openrouter"
