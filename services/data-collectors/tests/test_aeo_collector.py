from data_collectors.collectors.aeo import collect_aeo_input
from data_collectors.models import KeywordSpec


class FakeDataForSEOClient:
    def post(self, path, payload):
        return [{"keyword": "best crm", "serp_item_type": "featured_snippet", "engine": "google"}]


def test_collect_aeo_input_returns_mapped_aeo_input():
    result = collect_aeo_input(
        domain="example.com",
        keywords=[KeywordSpec(keyword="best crm", engine="google")],
        client=FakeDataForSEOClient(),
    )
    assert result.total_keywords_checked == 1
    assert result.snippet_hits[0].snippet_type == "featured_snippet"
