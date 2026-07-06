import json

from click.testing import CliRunner

from analysis_engine import cli as cli_module
from analysis_engine.cli import analyze
from analysis_engine.models import ScoreBreakdown


def _patch_website_audit(monkeypatch, score=75.0):
    monkeypatch.setattr(
        cli_module,
        "score_website_audit",
        lambda url: ScoreBreakdown(
            dimension="website_audit", score=score, data_complete=True, detail={}
        ),
    )


def test_analyze_cli_runs_end_to_end_with_no_data_files(monkeypatch):
    _patch_website_audit(monkeypatch)

    runner = CliRunner()
    result = runner.invoke(
        analyze,
        ["--domain", "example.com", "--url", "https://example.com", "--brand-name", "Acme"],
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["domain"] == "example.com"
    assert output["dimensions"]["website_audit"]["score"] == 75.0
    assert output["dimensions"]["seo"]["score"] is None
    assert any(
        r["dimension"] == "seo" and r["priority"] == "high" for r in output["recommendations"]
    )


def test_analyze_cli_reads_seo_data_file(monkeypatch, tmp_path):
    _patch_website_audit(monkeypatch)
    seo_file = tmp_path / "seo.json"
    seo_file.write_text(
        json.dumps(
            {
                "keyword_rankings": [
                    {"keyword": "widgets", "engine": "google", "position": 1, "search_volume": 500}
                ]
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        analyze,
        [
            "--domain",
            "example.com",
            "--url",
            "https://example.com",
            "--brand-name",
            "Acme",
            "--seo-data",
            str(seo_file),
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["dimensions"]["seo"]["score"] == 100.0


def test_analyze_cli_reads_aeo_and_geo_data_files(monkeypatch, tmp_path):
    _patch_website_audit(monkeypatch)
    aeo_file = tmp_path / "aeo.json"
    aeo_file.write_text(
        json.dumps(
            {
                "total_keywords_checked": 1,
                "snippet_hits": [
                    {"keyword": "widgets", "engine": "google", "snippet_type": "featured_snippet"}
                ],
            }
        )
    )
    geo_file = tmp_path / "geo.json"
    geo_file.write_text(
        json.dumps(
            {
                "mention_results": [
                    {
                        "query": "best widget maker",
                        "engine": "chatgpt",
                        "brand_mentioned": True,
                        "mention_position": 1,
                    }
                ]
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        analyze,
        [
            "--domain",
            "example.com",
            "--url",
            "https://example.com",
            "--brand-name",
            "Acme",
            "--aeo-data",
            str(aeo_file),
            "--geo-data",
            str(geo_file),
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["dimensions"]["aeo"]["score"] == 100.0
    assert output["dimensions"]["geo"]["score"] == 100.0
