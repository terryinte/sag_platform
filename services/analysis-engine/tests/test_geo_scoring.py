from analysis_engine.models import BrandMentionResult, GeoInput
from analysis_engine.scoring.geo import score_geo


def test_score_geo_returns_none_when_no_queries():
    result = score_geo(GeoInput(brand_name="Acme", domain="acme.com"))
    assert result.score is None
    assert result.data_complete is False
    assert result.dimension == "geo"


def test_score_geo_not_mentioned_scores_zero():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(query="best widget", engine="chatgpt", brand_mentioned=False),
        ],
    )
    result = score_geo(geo_input)
    assert result.score == 0.0
    assert result.data_complete is True


def test_score_geo_first_position_mention_scores_100():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(
                query="best widget", engine="chatgpt", brand_mentioned=True, mention_position=1
            ),
        ],
    )
    result = score_geo(geo_input)
    assert result.score == 100.0


def test_score_geo_second_or_third_position_scores_80():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(
                query="best widget", engine="chatgpt", brand_mentioned=True, mention_position=3
            ),
        ],
    )
    result = score_geo(geo_input)
    assert result.score == 80.0


def test_score_geo_mentioned_without_position_scores_60():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(query="best widget", engine="chatgpt", brand_mentioned=True),
        ],
    )
    result = score_geo(geo_input)
    assert result.score == 60.0


def test_score_geo_citation_bonus_caps_at_100():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(
                query="best widget",
                engine="chatgpt",
                brand_mentioned=True,
                mention_position=1,
                cited_as_source=True,
            ),
        ],
    )
    result = score_geo(geo_input)
    assert result.score == 100.0


def test_score_geo_citation_bonus_applies_to_lower_base_score():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(
                query="best widget",
                engine="chatgpt",
                brand_mentioned=True,
                mention_position=3,
                cited_as_source=True,
            ),
        ],
    )
    result = score_geo(geo_input)
    assert result.score == 100.0


def test_score_geo_averages_across_multiple_queries():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(
                query="q1", engine="chatgpt", brand_mentioned=True, mention_position=1
            ),
            BrandMentionResult(query="q2", engine="claude", brand_mentioned=False),
        ],
    )
    result = score_geo(geo_input)
    assert result.score == 50.0


def test_score_geo_detail_counts():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(
                query="q1",
                engine="chatgpt",
                brand_mentioned=True,
                mention_position=1,
                cited_as_source=True,
            ),
            BrandMentionResult(query="q2", engine="claude", brand_mentioned=False),
        ],
    )
    result = score_geo(geo_input)
    assert result.detail["queries_checked"] == 2
    assert result.detail["mentioned_count"] == 1
    assert result.detail["cited_as_source_count"] == 1
