from api.models import AnalyzeRequest, CollectRequest, GeoQueryInput, KeywordSpecInput


def test_keyword_spec_input_fields():
    spec = KeywordSpecInput(keyword="best crm", engine="google")
    assert spec.keyword == "best crm"
    assert spec.engine == "google"


def test_geo_query_input_fields():
    query = GeoQueryInput(query="best crm for factories", engine_hint="global")
    assert query.query == "best crm for factories"
    assert query.engine_hint == "global"


def test_collect_request_fields():
    request = CollectRequest(
        domain="example.com",
        url="https://example.com",
        brand_name="Acme",
        keywords=[KeywordSpecInput(keyword="best crm", engine="google")],
        geo_queries=[GeoQueryInput(query="best crm for factories")],
    )
    assert request.domain == "example.com"
    assert request.keywords[0].keyword == "best crm"


def test_analyze_request_matches_collect_request_shape():
    request = AnalyzeRequest(
        domain="example.com",
        url="https://example.com",
        brand_name="Acme",
        keywords=[],
        geo_queries=[],
    )
    assert request.url == "https://example.com"
