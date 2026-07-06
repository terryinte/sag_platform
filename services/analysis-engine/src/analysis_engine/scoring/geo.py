"""GEO dimension scoring: brand mention rate/position across LLM answer engines."""

from __future__ import annotations

from analysis_engine.models import BrandMentionResult, GeoInput, ScoreBreakdown

_CITATION_MULTIPLIER = 1.3
_MAX_SCORE = 100.0


def _mention_score(mention: BrandMentionResult) -> float:
    if not mention.brand_mentioned:
        return 0.0

    if mention.mention_position is not None and mention.mention_position <= 1:
        base = 100.0
    elif mention.mention_position is not None and mention.mention_position <= 3:
        base = 80.0
    else:
        base = 60.0

    if mention.cited_as_source:
        base = min(base * _CITATION_MULTIPLIER, _MAX_SCORE)

    return base


def score_geo(geo_input: GeoInput) -> ScoreBreakdown:
    if not geo_input.mention_results:
        return ScoreBreakdown(
            dimension="geo",
            score=None,
            data_complete=False,
            detail={"reason": "no LLM brand mention queries were run"},
        )

    scores = [_mention_score(mention) for mention in geo_input.mention_results]
    final_score = sum(scores) / len(scores)

    return ScoreBreakdown(
        dimension="geo",
        score=round(final_score, 2),
        data_complete=True,
        detail={
            "queries_checked": len(geo_input.mention_results),
            "mentioned_count": sum(1 for m in geo_input.mention_results if m.brand_mentioned),
            "cited_as_source_count": sum(
                1 for m in geo_input.mention_results if m.cited_as_source
            ),
        },
    )
