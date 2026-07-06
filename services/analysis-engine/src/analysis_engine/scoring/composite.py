"""Combines the SEO/AEO/GEO/website-audit dimension scores into one overall score."""

from __future__ import annotations

from analysis_engine.models import CompositeReport, ScoreBreakdown

DIMENSION_WEIGHTS: dict[str, float] = {
    "seo": 0.30,
    "aeo": 0.20,
    "geo": 0.35,
    "website_audit": 0.15,
}


def compute_composite_score(
    domain: str,
    seo: ScoreBreakdown,
    aeo: ScoreBreakdown,
    geo: ScoreBreakdown,
    website_audit: ScoreBreakdown,
) -> CompositeReport:
    dimension_scores = {
        "seo": seo,
        "aeo": aeo,
        "geo": geo,
        "website_audit": website_audit,
    }

    available = [
        (breakdown.score, DIMENSION_WEIGHTS[name])
        for name, breakdown in dimension_scores.items()
        if breakdown.score is not None
    ]

    if not available:
        overall_score = None
    else:
        total_weight = sum(weight for _, weight in available)
        overall_score = round(sum(score * weight for score, weight in available) / total_weight, 2)

    return CompositeReport(
        domain=domain,
        overall_score=overall_score,
        dimension_scores=dimension_scores,
        recommendations=[],
    )
