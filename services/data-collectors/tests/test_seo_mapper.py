from data_collectors.mappers.seo import map_seo_result


def test_map_seo_result_builds_seo_input():
    result = map_seo_result(
        domain="example.com",
        keyword_specs=[{"keyword": "best crm", "engine": "google"}],
        ranking_rows=[{"keyword": "best crm", "ranked_serp_element": {"position": 3}, "search_volume": 500}],
        indexed_pages_count=80,
        total_pages_count=100,
    )
    assert result.domain == "example.com"
    assert result.keyword_rankings[0].position == 3
    assert result.indexed_pages_count == 80
