from analysis_engine.models import KeywordRanking, SeoInput
from analysis_engine.scoring.seo import score_seo


def test_score_seo_returns_none_when_no_data():
    result = score_seo(SeoInput(domain="example.com"))
    assert result.score is None
    assert result.data_complete is False
    assert result.dimension == "seo"


def test_score_seo_top_ranking_with_no_indexation_data_scores_100():
    seo_input = SeoInput(
        domain="example.com",
        keyword_rankings=[
            KeywordRanking(keyword="widgets", engine="google", position=1, search_volume=1000),
        ],
    )
    result = score_seo(seo_input)
    # Only the ranking component (weight 0.7) has data, so it is renormalized to 100%.
    assert result.score == 100.0
    assert result.data_complete is False


def test_score_seo_combines_ranking_and_indexation():
    seo_input = SeoInput(
        domain="example.com",
        keyword_rankings=[
            KeywordRanking(keyword="widgets", engine="google", position=1, search_volume=1000),
        ],
        indexed_pages_count=80,
        total_pages_count=100,
    )
    result = score_seo(seo_input)
    # ranking_score=100 (weight 0.7) + indexation_score=80 (weight 0.3) = 94.0
    assert result.score == 94.0
    assert result.data_complete is True


def test_score_seo_weights_by_search_volume():
    seo_input = SeoInput(
        domain="example.com",
        keyword_rankings=[
            KeywordRanking(keyword="high-volume", engine="google", position=1, search_volume=9000),
            KeywordRanking(keyword="low-volume", engine="google", position=None, search_volume=1000),
        ],
    )
    result = score_seo(seo_input)
    # weighted ranking: (100*9000 + 0*1000) / 10000 = 90.0; renormalized to 100% weight -> 90.0
    assert result.score == 90.0


def test_score_seo_not_ranked_scores_zero():
    seo_input = SeoInput(
        domain="example.com",
        keyword_rankings=[KeywordRanking(keyword="widgets", engine="google", position=None)],
    )
    result = score_seo(seo_input)
    assert result.score == 0.0


def test_score_seo_position_bucket_boundaries():
    def _position_result(position):
        seo_input = SeoInput(
            domain="example.com",
            keyword_rankings=[KeywordRanking(keyword="k", engine="google", position=position)],
        )
        return score_seo(seo_input).score

    assert _position_result(3) == 100.0
    assert _position_result(4) == 80.0
    assert _position_result(10) == 80.0
    assert _position_result(11) == 60.0
    assert _position_result(20) == 60.0
    assert _position_result(21) == 40.0
    assert _position_result(50) == 40.0
    assert _position_result(51) == 20.0
    assert _position_result(100) == 20.0
    assert _position_result(101) == 0.0


def test_score_seo_zero_indexed_pages_is_known_bad_data_not_missing():
    # indexed_pages_count=0 is a real, known-bad indexation signal (site is
    # fully de-indexed) and must be scored as 0, not silently dropped as
    # "no data" the way indexed_pages_count=None would be.
    seo_input = SeoInput(
        domain="example.com",
        keyword_rankings=[KeywordRanking(keyword="widgets", engine="google", position=1)],
        indexed_pages_count=0,
        total_pages_count=100,
    )
    result = score_seo(seo_input)
    assert result.detail["indexation_score"] == 0.0
    assert result.data_complete is True
    # ranking=100 (weight 0.7) + indexation=0 (weight 0.3) = 70.0
    assert result.score == 70.0
