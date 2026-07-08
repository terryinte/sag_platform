from __future__ import annotations

from analysis_engine.models import KeywordRanking, SeoInput


def map_seo_result(
    domain: str,
    keyword_specs: list[dict],
    ranking_rows: list[dict],
    indexed_pages_count: int | None,
    total_pages_count: int | None,
) -> SeoInput:
    ranking_by_keyword = {row["keyword"]: row for row in ranking_rows}
    rankings = []
    for spec in keyword_specs:
        row = ranking_by_keyword.get(spec["keyword"], {})
        serp = row.get("ranked_serp_element") or {}
        rankings.append(
            KeywordRanking(
                keyword=spec["keyword"],
                engine=spec["engine"],
                position=serp.get("position"),
                search_volume=row.get("search_volume"),
            )
        )
    return SeoInput(
        domain=domain,
        keyword_rankings=rankings,
        indexed_pages_count=indexed_pages_count,
        total_pages_count=total_pages_count,
    )
