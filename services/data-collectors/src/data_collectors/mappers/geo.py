from __future__ import annotations

from analysis_engine.models import BrandMentionResult, GeoInput


def _detect_position(content: str, brand_name: str) -> int | None:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    for index, line in enumerate(lines, start=1):
        if brand_name.lower() in line.lower():
            return index
    return None


def map_geo_result(brand_name: str, domain: str, query_results: list[dict]) -> GeoInput:
    if not query_results:
        return GeoInput(brand_name=brand_name, domain=domain, mention_results=[])

    mentions = []
    for row in query_results:
        content = row["content"]
        position = _detect_position(content, brand_name)
        mentions.append(
            BrandMentionResult(
                query=row["query"],
                engine=row["provider"],
                brand_mentioned=position is not None,
                mention_position=position,
                cited_as_source=domain.lower() in content.lower(),
            )
        )
    return GeoInput(brand_name=brand_name, domain=domain, mention_results=mentions)
