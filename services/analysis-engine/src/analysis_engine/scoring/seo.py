"""SEO dimension scoring: keyword-ranking distribution + indexation health."""

from __future__ import annotations

from analysis_engine.models import ScoreBreakdown, SeoInput

# (max_position_inclusive, score) buckets, checked in order.
_POSITION_BUCKETS: tuple[tuple[int, float], ...] = (
    (3, 100.0),
    (10, 80.0),
    (20, 60.0),
    (50, 40.0),
    (100, 20.0),
)

_RANKING_WEIGHT = 0.7
_INDEXATION_WEIGHT = 0.3


def _position_score(position: int | None) -> float:
    if position is None:
        return 0.0
    for max_position, score in _POSITION_BUCKETS:
        if position <= max_position:
            return score
    return 0.0


def _ranking_score(seo_input: SeoInput) -> float | None:
    if not seo_input.keyword_rankings:
        return None
    total_weight = 0.0
    weighted_sum = 0.0
    for ranking in seo_input.keyword_rankings:
        weight = ranking.search_volume if ranking.search_volume else 1
        weighted_sum += _position_score(ranking.position) * weight
        total_weight += weight
    if total_weight == 0:
        return None
    return weighted_sum / total_weight


def _indexation_score(seo_input: SeoInput) -> float | None:
    if seo_input.indexed_pages_count is None or not seo_input.total_pages_count:
        return None
    ratio = seo_input.indexed_pages_count / seo_input.total_pages_count
    return min(ratio, 1.0) * 100.0


def score_seo(seo_input: SeoInput) -> ScoreBreakdown:
    ranking_score = _ranking_score(seo_input)
    indexation_score = _indexation_score(seo_input)

    components: list[tuple[float, float]] = []
    if ranking_score is not None:
        components.append((ranking_score, _RANKING_WEIGHT))
    if indexation_score is not None:
        components.append((indexation_score, _INDEXATION_WEIGHT))

    if not components:
        return ScoreBreakdown(
            dimension="seo",
            score=None,
            data_complete=False,
            detail={"reason": "no keyword ranking or indexation data available"},
        )

    total_weight = sum(weight for _, weight in components)
    final_score = sum(score * weight for score, weight in components) / total_weight

    return ScoreBreakdown(
        dimension="seo",
        score=round(final_score, 2),
        data_complete=ranking_score is not None and indexation_score is not None,
        detail={
            "ranking_score": ranking_score,
            "indexation_score": indexation_score,
            "keywords_evaluated": len(seo_input.keyword_rankings),
        },
    )
