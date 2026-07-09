from fastapi.testclient import TestClient

from api.main import app


def test_homepage_serves_usage_page():
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "SAG API Console" in response.text
    assert "/collect" in response.text
    assert "/analyze" in response.text
    assert "DATAFORSEO_LOGIN" in response.text
    assert "OPENROUTER_API_KEY" in response.text
    assert "QIANFAN_ACCESS_KEY" in response.text


def test_ui_alias_serves_same_usage_page():
    client = TestClient(app)
    response = client.get("/ui")

    assert response.status_code == 200
    assert "SAG API Console" in response.text
