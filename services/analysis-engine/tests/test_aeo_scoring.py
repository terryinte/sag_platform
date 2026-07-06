from analysis_engine.models import AeoInput, FeaturedSnippetHit
from analysis_engine.scoring.aeo import score_aeo


def test_score_aeo_returns_none_when_no_keywords_checked():
    result = score_aeo(AeoInput(domain="example.com", total_keywords_checked=0))
    assert result.score is None
    assert result.data_complete is False
    assert result.dimension == "aeo"


def test_score_aeo_full_featured_snippet_coverage():
    aeo_input = AeoInput(
        domain="example.com",
        total_keywords_checked=2,
        snippet_hits=[
            FeaturedSnippetHit(keyword="a", engine="google", snippet_type="featured_snippet"),
            FeaturedSnippetHit(keyword="b", engine="google", snippet_type="featured_snippet"),
        ],
    )
    result = score_aeo(aeo_input)
    assert result.score == 100.0
    assert result.data_complete is True


def test_score_aeo_paa_gives_partial_credit():
    aeo_input = AeoInput(
        domain="example.com",
        total_keywords_checked=2,
        snippet_hits=[
            FeaturedSnippetHit(keyword="a", engine="google", snippet_type="paa"),
        ],
    )
    result = score_aeo(aeo_input)
    assert result.score == 25.0


def test_score_aeo_no_hits_scores_zero():
    aeo_input = AeoInput(domain="example.com", total_keywords_checked=3, snippet_hits=[])
    result = score_aeo(aeo_input)
    assert result.score == 0.0


def test_score_aeo_detail_counts_hit_types():
    aeo_input = AeoInput(
        domain="example.com",
        total_keywords_checked=3,
        snippet_hits=[
            FeaturedSnippetHit(keyword="a", engine="google", snippet_type="featured_snippet"),
            FeaturedSnippetHit(keyword="b", engine="google", snippet_type="paa"),
        ],
    )
    result = score_aeo(aeo_input)
    assert result.detail["featured_snippet_hits"] == 1
    assert result.detail["paa_hits"] == 1
    assert result.detail["total_keywords_checked"] == 3


def test_score_aeo_caps_at_100_when_hits_exceed_total_keywords():
    # Defensive case: more snippet hits reported than total_keywords_checked
    # (e.g. duplicate/overlapping hits) must not push the score above 100.
    aeo_input = AeoInput(
        domain="example.com",
        total_keywords_checked=2,
        snippet_hits=[
            FeaturedSnippetHit(keyword="a", engine="google", snippet_type="featured_snippet"),
            FeaturedSnippetHit(keyword="a", engine="google", snippet_type="paa"),
            FeaturedSnippetHit(keyword="b", engine="google", snippet_type="featured_snippet"),
            FeaturedSnippetHit(keyword="b", engine="google", snippet_type="paa"),
        ],
    )
    result = score_aeo(aeo_input)
    assert result.score == 100.0
