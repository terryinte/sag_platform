from analysis_engine.models import CompositeReport, ScoreBreakdown
from analysis_engine.recommendations import generate_recommendations


def _report(seo=90.0, aeo=90.0, geo=90.0, website_audit=90.0, website_audit_detail=None):
    return CompositeReport(
        domain="example.com",
        overall_score=90.0,
        dimension_scores={
            "seo": ScoreBreakdown(dimension="seo", score=seo, data_complete=seo is not None),
            "aeo": ScoreBreakdown(dimension="aeo", score=aeo, data_complete=aeo is not None),
            "geo": ScoreBreakdown(dimension="geo", score=geo, data_complete=geo is not None),
            "website_audit": ScoreBreakdown(
                dimension="website_audit",
                score=website_audit,
                data_complete=website_audit is not None,
                detail=website_audit_detail or {},
            ),
        },
        recommendations=[],
    )


def test_generate_recommendations_flags_missing_data_as_high_priority():
    report = _report(seo=None)
    recs = generate_recommendations(report)
    assert any(r.dimension == "seo" and r.priority == "high" for r in recs)


def test_generate_recommendations_skips_high_scoring_dimensions():
    report = _report(seo=95.0, aeo=90.0, geo=90.0, website_audit=90.0)
    recs = generate_recommendations(report)
    assert recs == []


def test_generate_recommendations_medium_priority_between_40_and_70():
    report = _report(seo=50.0)
    recs = generate_recommendations(report)
    seo_recs = [r for r in recs if r.dimension == "seo"]
    assert len(seo_recs) == 1
    assert seo_recs[0].priority == "medium"


def test_generate_recommendations_high_priority_below_40():
    report = _report(seo=20.0)
    recs = generate_recommendations(report)
    seo_recs = [r for r in recs if r.dimension == "seo"]
    assert len(seo_recs) == 1
    assert seo_recs[0].priority == "high"


def test_generate_recommendations_includes_website_audit_raw_recommendations():
    report = _report(
        website_audit=30.0,
        website_audit_detail={"recommendations": ["Add an llms.txt file"]},
    )
    recs = generate_recommendations(report)
    audit_recs = [r for r in recs if r.title == "Add an llms.txt file"]
    assert len(audit_recs) == 1
    assert audit_recs[0].priority == "high"
    assert audit_recs[0].dimension == "website_audit"


def test_generate_recommendations_sorted_by_priority_then_dimension():
    report = _report(seo=50.0, aeo=20.0, geo=90.0, website_audit=90.0)
    recs = generate_recommendations(report)
    assert [r.dimension for r in recs] == ["aeo", "seo"]
