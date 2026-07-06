from analysis_engine.models import (
    AeoInput,
    BrandMentionResult,
    CompositeReport,
    FeaturedSnippetHit,
    GeoInput,
    KeywordRanking,
    Recommendation,
    ScoreBreakdown,
    SeoInput,
)


def test_seo_input_defaults_to_empty_rankings():
    seo_input = SeoInput(domain="example.com")
    assert seo_input.keyword_rankings == []
    assert seo_input.indexed_pages_count is None
    assert seo_input.total_pages_count is None


def test_keyword_ranking_holds_expected_fields():
    ranking = KeywordRanking(keyword="widgets", engine="google", position=3, search_volume=500)
    assert ranking.keyword == "widgets"
    assert ranking.engine == "google"
    assert ranking.position == 3
    assert ranking.search_volume == 500


def test_aeo_input_defaults():
    aeo_input = AeoInput(domain="example.com")
    assert aeo_input.snippet_hits == []
    assert aeo_input.total_keywords_checked == 0


def test_featured_snippet_hit_fields():
    hit = FeaturedSnippetHit(keyword="widgets", engine="google", snippet_type="paa")
    assert hit.snippet_type == "paa"


def test_geo_input_defaults():
    geo_input = GeoInput(brand_name="Acme", domain="acme.com")
    assert geo_input.mention_results == []


def test_brand_mention_result_defaults():
    mention = BrandMentionResult(query="best widget", engine="chatgpt", brand_mentioned=True)
    assert mention.mention_position is None
    assert mention.cited_as_source is False


def test_score_breakdown_fields():
    breakdown = ScoreBreakdown(dimension="seo", score=75.0, data_complete=True)
    assert breakdown.detail == {}


def test_recommendation_fields():
    rec = Recommendation(priority="high", dimension="seo", title="t", description="d")
    assert rec.priority == "high"


def test_composite_report_fields():
    report = CompositeReport(
        domain="example.com",
        overall_score=80.0,
        dimension_scores={},
        recommendations=[],
    )
    assert report.overall_score == 80.0
