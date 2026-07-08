from __future__ import annotations

from analysis_engine.models import AeoInput, GeoInput, SeoInput

from data_collectors.collectors.aeo import collect_aeo_input
from data_collectors.collectors.geo import collect_geo_input
from data_collectors.collectors.seo import collect_seo_input
from data_collectors.errors import ProviderError
from data_collectors.models import CollectionError, CollectionPayload, GeoQuerySpec, KeywordSpec


def build_collection_payload(
    domain: str,
    seo: SeoInput | None,
    aeo: AeoInput | None,
    geo: GeoInput | None,
    errors: list[CollectionError],
) -> CollectionPayload:
    return CollectionPayload(domain=domain, seo=seo, aeo=aeo, geo=geo, errors=errors)


def run_collection_pipeline(
    domain: str,
    brand_name: str,
    keywords: list[KeywordSpec],
    geo_queries: list[GeoQuerySpec],
    dataforseo_client,
    openrouter_client,
    qianfan_client,
) -> CollectionPayload:
    errors: list[CollectionError] = []

    try:
        seo = collect_seo_input(domain=domain, keywords=keywords, client=dataforseo_client)
    except ProviderError as exc:
        seo = None
        errors.append(exc.to_collection_error())

    try:
        aeo = collect_aeo_input(domain=domain, keywords=keywords, client=dataforseo_client)
    except ProviderError as exc:
        aeo = None
        errors.append(exc.to_collection_error())

    geo, geo_errors = collect_geo_input(
        brand_name=brand_name,
        domain=domain,
        queries=geo_queries,
        openrouter_client=openrouter_client,
        qianfan_client=qianfan_client,
    )
    errors.extend(geo_errors)

    return build_collection_payload(domain=domain, seo=seo, aeo=aeo, geo=geo, errors=errors)
