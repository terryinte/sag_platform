"""End-to-end test: feed realistic fixture data through every scoring module
and the composite/recommendations pipeline via the public Python API."""

from unittest.mock import patch

from analysis_engine.models import (
    AeoInput,
    BrandMentionResult,
    FeaturedSnippetHit,
    GeoInput,
    KeywordRanking,
    SeoInput,
)
from analysis_engine.recommendations import generate_recommendations
from analysis_engine.scoring.aeo import score_aeo
from analysis_engine.scoring.composite import compute_composite_score
from analysis_engine.scoring.geo import score_geo
from analysis_engine.scoring.seo import score_seo
from analysis_engine.scoring.website_audit import score_website_audit


def test_full_pipeline_produces_a_complete_report():
    seo_input = SeoInput(
        domain="acme.com",
        keyword_rankings=[
            KeywordRanking(keyword="widgets", engine="google", position=2, search_volume=800),
            KeywordRanking(keyword="gadgets", engine="baidu", position=15, search_volume=200),
        ],
        indexed_pages_count=45,
        total_pages_count=50,
    )
    aeo_input = AeoInput(
        domain="acme.com",
        total_keywords_checked=4,
        snippet_hits=[
            FeaturedSnippetHit(keyword="widgets", engine="google", snippet_type="featured_snippet"),
            FeaturedSnippetHit(keyword="gadgets", engine="google", snippet_type="paa"),
        ],
    )
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(
                query="best widget maker",
                engine="chatgpt",
                brand_mentioned=True,
                mention_position=1,
                cited_as_source=True,
            ),
            BrandMentionResult(query="top gadget brands", engine="claude", brand_mentioned=False),
        ],
    )

    with patch("analysis_engine.scoring.website_audit.run_geo_audit") as mock_audit:
        mock_audit.return_value.score = 68
        mock_audit.return_value.band = "fair"
        mock_audit.return_value.error = None
        mock_audit.return_value.score_breakdown = {"robots": 5, "llms_txt": 0}
        mock_audit.return_value.recommendations = ["Add an llms.txt file"]

        seo_score = score_seo(seo_input)
        aeo_score = score_aeo(aeo_input)
        geo_score = score_geo(geo_input)
        website_audit_score = score_website_audit("https://acme.com")

    report = compute_composite_score(
        "acme.com", seo_score, aeo_score, geo_score, website_audit_score
    )
    report.recommendations = generate_recommendations(report)

    assert report.domain == "acme.com"
    assert report.overall_score is not None
    assert 0.0 <= report.overall_score <= 100.0
    assert set(report.dimension_scores.keys()) == {"seo", "aeo", "geo", "website_audit"}
    for breakdown in report.dimension_scores.values():
        assert breakdown.data_complete is True
        assert breakdown.score is not None

    # website_audit scored 68 (< 80) so its raw recommendation should surface.
    assert any(r.title == "Add an llms.txt file" for r in report.recommendations)
