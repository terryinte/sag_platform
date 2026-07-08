from __future__ import annotations

from analysis_engine.models import AeoInput, FeaturedSnippetHit


def map_aeo_result(domain: str, snippet_rows: list[dict], total_keywords_checked: int) -> AeoInput:
    snippet_type_map = {
        "featured_snippet": "featured_snippet",
        "people_also_ask": "paa",
    }
    hits = [
        FeaturedSnippetHit(
            keyword=row["keyword"],
            engine=row.get("engine", "google"),
            snippet_type=snippet_type_map.get(row.get("serp_item_type"), "none"),
        )
        for row in snippet_rows
    ]
    return AeoInput(domain=domain, snippet_hits=hits, total_keywords_checked=total_keywords_checked)
