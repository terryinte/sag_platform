from analysis_engine.models import ScoreBreakdown
from analysis_engine.scoring.composite import compute_composite_score


def _breakdown(dimension: str, score: float | None) -> ScoreBreakdown:
    return ScoreBreakdown(dimension=dimension, score=score, data_complete=score is not None)


def test_compute_composite_score_all_dimensions_present():
    report = compute_composite_score(
        domain="example.com",
        seo=_breakdown("seo", 80.0),
        aeo=_breakdown("aeo", 60.0),
        geo=_breakdown("geo", 90.0),
        website_audit=_breakdown("website_audit", 70.0),
    )
    assert report.overall_score == 78.0
    assert report.domain == "example.com"
    assert set(report.dimension_scores.keys()) == {"seo", "aeo", "geo", "website_audit"}
    assert report.recommendations == []


def test_compute_composite_score_renormalizes_when_dimension_missing():
    report = compute_composite_score(
        domain="example.com",
        seo=_breakdown("seo", 80.0),
        aeo=_breakdown("aeo", None),
        geo=_breakdown("geo", 90.0),
        website_audit=_breakdown("website_audit", 70.0),
    )
    assert report.overall_score == 82.5


def test_compute_composite_score_all_missing_returns_none():
    report = compute_composite_score(
        domain="example.com",
        seo=_breakdown("seo", None),
        aeo=_breakdown("aeo", None),
        geo=_breakdown("geo", None),
        website_audit=_breakdown("website_audit", None),
    )
    assert report.overall_score is None
