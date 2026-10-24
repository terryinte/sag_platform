from pathlib import Path

from data_collectors.providers.answers import BrowserCollectorStub, ScrapeResult
from data_collectors.providers.browser import collect_browser_answer, persist_artifacts


def test_stub_engines_do_not_call_the_runner():
    def explode(**_kwargs):
        raise AssertionError("stub engine must not launch")

    for engine in ("Google AI 概览", "Google AI Mode", "Copilot"):
        result = collect_browser_answer(engine, "best nas", runner=explode)
        assert result.error_code == "browser_stub"
        assert result.text == ""
        assert result.access == "scraped"


def test_launch_failure_is_browser_unavailable():
    def boom(**_kwargs):
        raise RuntimeError("launch failed")

    result = collect_browser_answer("ChatGPT 网页", "充电器怎么选", runner=boom)
    assert result.status == "skipped"
    assert result.error_code == "browser_unavailable"
    assert result.text == ""
    assert result.access == "scraped"


def test_screenshot_failure_still_returns_text(tmp_path: Path):
    def runner(**_kwargs):
        return {
            "text": "豆包回答正文",
            "html": "<p>豆包回答正文</p>",
            "png": None,
            "screenshot_error": "screenshot timeout",
            "implementation": "playwright-chromium",
        }

    result = collect_browser_answer("豆包", "问题", artifact_dir=tmp_path, runner=runner)
    assert result.status == "ok"
    assert result.error_code == ""
    assert result.text == "豆包回答正文"
    assert result.raw_output["screenshot_error"] == "screenshot timeout"
    assert Path(result.raw_output["html_path"]).read_text(encoding="utf-8").startswith("<p>")


def test_persist_artifacts_records_write_errors(tmp_path: Path):
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("file", encoding="utf-8")
    saved = persist_artifacts(blocked, "<p>x</p>", "x", None, "")
    assert saved["html_path"] == ""
    assert saved["screenshot_error"]


def test_stub_interface_skips_when_browser_fails(monkeypatch):
    def boom(**_kwargs):
        raise RuntimeError("launch failed")

    monkeypatch.setattr("data_collectors.providers.browser._default_runner", boom)
    result = BrowserCollectorStub().run("Kimi 网页", "你好")
    assert isinstance(result, ScrapeResult)
    assert result.status == "skipped"
    assert result.error_code == "browser_unavailable"
    assert result.text == ""
