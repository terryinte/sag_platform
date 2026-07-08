from data_collectors.mappers.aeo import map_aeo_result


def test_map_aeo_result_builds_aeo_input():
    result = map_aeo_result(
        domain="example.com",
        snippet_rows=[
            {"keyword": "best crm", "serp_item_type": "featured_snippet"},
            {"keyword": "erp crm", "serp_item_type": "people_also_ask"},
        ],
        total_keywords_checked=2,
    )
    assert result.total_keywords_checked == 2
    assert result.snippet_hits[0].snippet_type == "featured_snippet"
    assert result.snippet_hits[1].snippet_type == "paa"
