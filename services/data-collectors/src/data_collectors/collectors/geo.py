from __future__ import annotations

from analysis_engine.models import GeoInput

from data_collectors.errors import ProviderError
from data_collectors.mappers.geo import map_geo_result
from data_collectors.models import CollectionError, GeoQuerySpec


def collect_geo_input(
    brand_name: str,
    domain: str,
    queries: list[GeoQuerySpec],
    openrouter_client,
    qianfan_client,
) -> tuple[GeoInput, list[CollectionError]]:
    raw_results = []
    errors: list[CollectionError] = []

    for item in queries:
        try:
            raw_results.append({"query": item.query, **openrouter_client.query(item.query)})
        except ProviderError as exc:
            errors.append(exc.to_collection_error())

        try:
            raw_results.append({"query": item.query, **qianfan_client.query(item.query)})
        except ProviderError as exc:
            errors.append(exc.to_collection_error())

    return map_geo_result(brand_name=brand_name, domain=domain, query_results=raw_results), errors
