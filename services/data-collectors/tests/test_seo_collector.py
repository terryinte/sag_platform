from data_collectors.collectors.seo import collect_seo_input
from data_collectors.models import KeywordSpec


class FakeDataForSEOClient:
    def post(self, path, payload):
        return [{"keyword": "best crm", "ranked_serp_element": {"position": 2}, "search_volume": 500}]


def test_collect_seo_input_returns_mapped_seo_input():
    result = collect_seo_input(
        domain="example.com",
        keywords=[KeywordSpec(keyword="best crm", engine="google")],
        client=FakeDataForSEOClient(),
    )
    assert result.domain == "example.com"
    assert result.keyword_rankings[0].position == 2
