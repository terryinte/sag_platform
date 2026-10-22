from fastapi.testclient import TestClient

from api.main import app


def test_homepage_serves_usage_page():
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "SAG 测评台" in response.text
    assert "GEO检测" in response.text
    assert "/api/demo/seed" in response.text
    assert "评分与建议" in response.text
    assert "添加测试关键词" in response.text


def test_ui_alias_serves_same_usage_page():
    client = TestClient(app)
    response = client.get("/ui")

    assert response.status_code == 200
    assert "SAG 测评台" in response.text


def test_console_keeps_provider_debug_page():
    client = TestClient(app)
    response = client.get("/console")

    assert response.status_code == 200
    assert "SAG API Console" in response.text
