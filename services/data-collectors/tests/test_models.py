from data_collectors.models import CollectionError, CollectionPayload, GeoQuerySpec, KeywordSpec


def test_keyword_spec_fields():
    spec = KeywordSpec(keyword="best crm", engine="google")
    assert spec.keyword == "best crm"
    assert spec.engine == "google"


def test_geo_query_spec_fields():
    query = GeoQuerySpec(query="best crm for factories", engine_hint="global")
    assert query.query == "best crm for factories"
    assert query.engine_hint == "global"


def test_collection_error_fields():
    error = CollectionError(
        provider="openrouter",
        operation="geo_query_batch",
        retryable=True,
        message="rate limited",
    )
    assert error.provider == "openrouter"
    assert error.retryable is True


def test_collection_payload_defaults():
    payload = CollectionPayload(domain="example.com")
    assert payload.seo is None
    assert payload.aeo is None
    assert payload.geo is None
    assert payload.errors == []
