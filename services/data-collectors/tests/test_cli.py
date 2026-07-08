import json

from click.testing import CliRunner

from data_collectors import cli as cli_module
from data_collectors.cli import main
from data_collectors.models import CollectionPayload
from analysis_engine.models import AeoInput, GeoInput, ScoreBreakdown, SeoInput


def test_collect_command_prints_normalized_json(monkeypatch, tmp_path):
    keywords_file = tmp_path / "keywords.json"
    geo_queries_file = tmp_path / "geo.json"
    keywords_file.write_text(json.dumps([{"keyword": "best crm", "engine": "google"}]))
    geo_queries_file.write_text(json.dumps([{"query": "best crm for factories"}]))

    monkeypatch.setattr(
        cli_module,
        "run_collection",
        lambda **kwargs: CollectionPayload(
            domain="example.com",
            seo=SeoInput(domain="example.com"),
            aeo=AeoInput(domain="example.com"),
            geo=GeoInput(brand_name="Acme", domain="example.com"),
            errors=[],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "collect",
            "--domain",
            "example.com",
            "--url",
            "https://example.com",
            "--brand-name",
            "Acme",
            "--keywords-file",
            str(keywords_file),
            "--geo-queries-file",
            str(geo_queries_file),
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["domain"] == "example.com"
    assert output["errors"] == []


def test_analyze_command_calls_analysis_engine(monkeypatch, tmp_path):
    keywords_file = tmp_path / "keywords.json"
    geo_queries_file = tmp_path / "geo.json"
    keywords_file.write_text(json.dumps([{"keyword": "best crm", "engine": "google"}]))
    geo_queries_file.write_text(json.dumps([{"query": "best crm for factories"}]))

    monkeypatch.setattr(
        cli_module,
        "run_collection",
        lambda **kwargs: CollectionPayload(
            domain="example.com",
            seo=SeoInput(domain="example.com"),
            aeo=AeoInput(domain="example.com"),
            geo=GeoInput(brand_name="Acme", domain="example.com"),
            errors=[],
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "score_website_audit",
        lambda url: ScoreBreakdown(dimension="website_audit", score=75.0, data_complete=True, detail={}),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "analyze",
            "--domain",
            "example.com",
            "--url",
            "https://example.com",
            "--brand-name",
            "Acme",
            "--keywords-file",
            str(keywords_file),
            "--geo-queries-file",
            str(geo_queries_file),
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["domain"] == "example.com"
    assert "dimensions" in output


def test_collect_command_fails_fast_without_credentials(monkeypatch, tmp_path):
    keywords_file = tmp_path / "keywords.json"
    geo_queries_file = tmp_path / "geo.json"
    keywords_file.write_text(json.dumps([{"keyword": "best crm", "engine": "google"}]))
    geo_queries_file.write_text(json.dumps([{"query": "best crm for factories"}]))

    monkeypatch.delenv("DATAFORSEO_LOGIN", raising=False)
    monkeypatch.delenv("DATAFORSEO_PASSWORD", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("QIANFAN_ACCESS_KEY", raising=False)
    monkeypatch.delenv("QIANFAN_SECRET_KEY", raising=False)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "collect",
            "--domain",
            "example.com",
            "--url",
            "https://example.com",
            "--brand-name",
            "Acme",
            "--keywords-file",
            str(keywords_file),
            "--geo-queries-file",
            str(geo_queries_file),
        ],
    )

    assert result.exit_code != 0
    assert "Missing required environment variables" in result.output
