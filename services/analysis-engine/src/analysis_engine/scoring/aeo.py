"""AEO dimension scoring: featured snippet / People-Also-Ask hit rate."""

from __future__ import annotations

from analysis_engine.models import AeoInput, ScoreBreakdown

_SNIPPET_POINTS: dict[str, float] = {
    "featured_snippet": 1.0,
    "paa": 0.5,
    "none": 0.0,
}


def score_aeo(aeo_input: AeoInput) -> ScoreBreakdown:
    if aeo_input.total_keywords_checked <= 0:
        return ScoreBreakdown(
            dimension="aeo",
            score=None,
            data_complete=False,
            detail={"reason": "no keywords checked for featured snippets/PAA"},
        )

    total_points = sum(_SNIPPET_POINTS.get(hit.snippet_type, 0.0) for hit in aeo_input.snippet_hits)
    score = min(total_points / aeo_input.total_keywords_checked * 100.0, 100.0)

    return ScoreBreakdown(
        dimension="aeo",
        score=round(score, 2),
        data_complete=True,
        detail={
            "featured_snippet_hits": sum(
                1 for hit in aeo_input.snippet_hits if hit.snippet_type == "featured_snippet"
            ),
            "paa_hits": sum(1 for hit in aeo_input.snippet_hits if hit.snippet_type == "paa"),
            "total_keywords_checked": aeo_input.total_keywords_checked,
        },
    )
