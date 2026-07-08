from __future__ import annotations

from analysis_engine.models import AeoInput

from data_collectors.mappers.aeo import map_aeo_result
from data_collectors.models import KeywordSpec


def collect_aeo_input(domain: str, keywords: list[KeywordSpec], client) -> AeoInput:
    rows = client.post(
        "/v3/serp/google/organic/live/advanced",
        [{"keyword": item.keyword} for item in keywords],
    )
    return map_aeo_result(
        domain=domain,
        snippet_rows=rows,
        total_keywords_checked=len(keywords),
    )
