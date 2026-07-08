from __future__ import annotations

from analysis_engine.models import SeoInput

from data_collectors.mappers.seo import map_seo_result
from data_collectors.models import KeywordSpec


def collect_seo_input(domain: str, keywords: list[KeywordSpec], client) -> SeoInput:
    rows = client.post(
        "/v3/serp/google/organic/live/advanced",
        [{"keyword": item.keyword} for item in keywords],
    )
    return map_seo_result(
        domain=domain,
        keyword_specs=[{"keyword": item.keyword, "engine": item.engine} for item in keywords],
        ranking_rows=rows,
        indexed_pages_count=None,
        total_pages_count=None,
    )
