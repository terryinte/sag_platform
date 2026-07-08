from data_collectors.mappers.geo import map_geo_result


def test_map_geo_result_builds_geo_input():
    result = map_geo_result(
        brand_name="Acme",
        domain="acme.com",
        query_results=[
            {
                "query": "best crm for factories",
                "provider": "openrouter",
                "content": "1. Acme CRM\nSource: https://acme.com\n2. Other Brand",
            }
        ],
    )
    assert result.brand_name == "Acme"
    assert result.mention_results[0].brand_mentioned is True
    assert result.mention_results[0].mention_position == 1
    assert result.mention_results[0].cited_as_source is True
