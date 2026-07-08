from fastapi.testclient import TestClient

from api.main import app


def test_collect_route_returns_json(monkeypatch):
    monkeypatch.setattr(
        "api.main.collect_service",
        lambda request: {
            "domain": request.domain,
            "seo": None,
            "aeo": None,
            "geo": None,
            "errors": [],
        },
    )
    client = TestClient(app)
    response = client.post(
        "/collect",
        json={
            "domain": "example.com",
            "url": "https://example.com",
            "brand_name": "Acme",
            "keywords": [{"keyword": "best crm", "engine": "google"}],
            "geo_queries": [{"query": "best crm for factories", "engine_hint": "global"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["domain"] == "example.com"


def test_analyze_route_returns_json(monkeypatch):
    monkeypatch.setattr(
        "api.main.analyze_service",
        lambda request: {
            "domain": request.domain,
            "overall_score": 78.4,
            "dimensions": {},
            "recommendations": [],
            "collection_errors": [],
        },
    )
    client = TestClient(app)
    response = client.post(
        "/analyze",
        json={
            "domain": "example.com",
            "url": "https://example.com",
            "brand_name": "Acme",
            "keywords": [],
            "geo_queries": [],
        },
    )
    assert response.status_code == 200
    assert response.json()["domain"] == "example.com"


def test_collect_route_rejects_invalid_payload():
    client = TestClient(app)
    response = client.post("/collect", json={"domain": "example.com"})
    assert response.status_code == 422


def test_collect_route_returns_clear_500_on_runtime_error(monkeypatch):
    monkeypatch.setattr(
        "api.main.collect_service",
        lambda request: (_ for _ in ()).throw(RuntimeError("Missing required environment variables")),
    )
    client = TestClient(app)
    response = client.post(
        "/collect",
        json={
            "domain": "example.com",
            "url": "https://example.com",
            "brand_name": "Acme",
            "keywords": [{"keyword": "best crm", "engine": "google"}],
            "geo_queries": [{"query": "best crm for factories", "engine_hint": "global"}],
        },
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "Missing required environment variables"
