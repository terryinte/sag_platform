from __future__ import annotations

from analysis_engine.models import AeoInput, GeoInput, SeoInput
from analysis_engine.recommendations import generate_recommendations
from analysis_engine.scoring.aeo import score_aeo
from analysis_engine.scoring.composite import compute_composite_score
from analysis_engine.scoring.geo import score_geo
from analysis_engine.scoring.seo import score_seo
from analysis_engine.scoring.website_audit import score_website_audit
from data_collectors.collectors.pipeline import run_collection_pipeline
from data_collectors.models import CollectionPayload
from data_collectors.providers.dataforseo import DataForSEOClient
from data_collectors.providers.openrouter import OpenRouterClient
from data_collectors.providers.qianfan import QianfanClient

from api.adapters import analyze_response_to_dict, collect_payload_to_dict, collect_request_to_inputs
from api.models import AnalyzeRequest, CollectRequest
from api.settings import settings


def _require_credentials() -> None:
    missing = [
        name
        for name, value in {
            "DATAFORSEO_LOGIN": settings.dataforseo_login,
            "DATAFORSEO_PASSWORD": settings.dataforseo_password,
            "OPENROUTER_API_KEY": settings.openrouter_api_key,
            "QIANFAN_ACCESS_KEY": settings.qianfan_access_key,
            "QIANFAN_SECRET_KEY": settings.qianfan_secret_key,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


def _build_collection_payload(request: CollectRequest) -> CollectionPayload:
    _require_credentials()
    keywords, geo_queries = collect_request_to_inputs(request)
    return run_collection_pipeline(
        domain=request.domain,
        brand_name=request.brand_name,
        keywords=keywords,
        geo_queries=geo_queries,
        dataforseo_client=DataForSEOClient(
            login=settings.dataforseo_login,
            password=settings.dataforseo_password,
        ),
        openrouter_client=OpenRouterClient(api_key=settings.openrouter_api_key),
        qianfan_client=QianfanClient(
            access_key=settings.qianfan_access_key,
            secret_key=settings.qianfan_secret_key,
        ),
    )


def collect_service(request: CollectRequest) -> dict:
    payload = _build_collection_payload(request)
    return collect_payload_to_dict(payload)


def analyze_service(request: AnalyzeRequest) -> dict:
    payload = _build_collection_payload(request)
    seo = payload.seo or SeoInput(domain=request.domain)
    aeo = payload.aeo or AeoInput(domain=request.domain)
    geo = payload.geo or GeoInput(brand_name=request.brand_name, domain=request.domain)
    report = compute_composite_score(
        request.domain,
        score_seo(seo),
        score_aeo(aeo),
        score_geo(geo),
        score_website_audit(request.url),
    )
    report.recommendations = generate_recommendations(report)
    return analyze_response_to_dict(report, [item.__dict__ for item in payload.errors])
