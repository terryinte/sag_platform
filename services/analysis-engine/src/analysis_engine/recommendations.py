"""Turns a CompositeReport's dimension scores into a prioritized action list."""

from __future__ import annotations

from analysis_engine.models import CompositeReport, Recommendation, ScoreBreakdown

_PRIORITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}
_DIMENSION_LABELS: dict[str, str] = {
    "seo": "SEO",
    "aeo": "AEO",
    "geo": "GEO",
    "website_audit": "Website AI-friendliness",
}
_HIGH_PRIORITY_THRESHOLD = 40.0
_MEDIUM_PRIORITY_THRESHOLD = 70.0
_RECOMMENDATION_THRESHOLD = 80.0


def _priority_for_score(score: float) -> str:
    if score < _HIGH_PRIORITY_THRESHOLD:
        return "high"
    if score < _MEDIUM_PRIORITY_THRESHOLD:
        return "medium"
    return "low"


def _dimension_recommendation(name: str, breakdown: ScoreBreakdown) -> Recommendation | None:
    label = _DIMENSION_LABELS[name]

    if breakdown.score is None:
        return Recommendation(
            priority="high",
            dimension=name,
            title=f"{label} data missing",
            description=(
                f"No {label} data was collected for this domain. Connect the relevant data source before this score can be computed."
            ),
        )

    if breakdown.score >= _RECOMMENDATION_THRESHOLD:
        return None

    return Recommendation(
        priority=_priority_for_score(breakdown.score),
        dimension=name,
        title=f"Improve {label} score ({breakdown.score:.0f}/100)",
        description=f"{label} score is below target; review the {label} data breakdown for specific gaps.",
    )


def generate_recommendations(report: CompositeReport) -> list[Recommendation]:
    recommendations: list[Recommendation] = []

    for name, breakdown in report.dimension_scores.items():
        rec = _dimension_recommendation(name, breakdown)
        if rec is not None:
            recommendations.append(rec)

    website_audit = report.dimension_scores.get("website_audit")
    if website_audit is not None and website_audit.score is not None:
        audit_priority = _priority_for_score(website_audit.score)
        for raw_recommendation in website_audit.detail.get("recommendations", []):
            recommendations.append(
                Recommendation(
                    priority=audit_priority,
                    dimension="website_audit",
                    title=raw_recommendation,
                    description=raw_recommendation,
                )
            )

    recommendations.sort(key=lambda r: (_PRIORITY_ORDER[r.priority], r.dimension))
    return recommendations
