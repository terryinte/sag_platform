from types import SimpleNamespace

from analysis_engine.scoring import website_audit as website_audit_module
from analysis_engine.scoring.website_audit import score_website_audit


def test_score_website_audit_maps_successful_result(monkeypatch):
    fake_result = SimpleNamespace(
        score=82,
        band="good",
        error=None,
        score_breakdown={"robots": 10, "schema": 20},
        recommendations=["Add llms.txt"],
    )
    monkeypatch.setattr(website_audit_module, "run_geo_audit", lambda url: fake_result)

    result = score_website_audit("https://example.com")

    assert result.dimension == "website_audit"
    assert result.score == 82.0
    assert result.data_complete is True
    assert result.detail["band"] == "good"
    assert result.detail["score_breakdown"] == {"robots": 10, "schema": 20}
    assert result.detail["recommendations"] == ["Add llms.txt"]


def test_score_website_audit_handles_connection_error(monkeypatch):
    fake_result = SimpleNamespace(
        score=0,
        band="critical",
        error="connection timed out",
        score_breakdown={},
        recommendations=[],
    )
    monkeypatch.setattr(website_audit_module, "run_geo_audit", lambda url: fake_result)

    result = score_website_audit("https://unreachable.example")

    assert result.score is None
    assert result.data_complete is False
    assert result.detail["reason"] == "connection timed out"
