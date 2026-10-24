"""Playwright browser collectors for the web answer channels.

Tests pass ``runner`` and never launch a browser. If Playwright is missing or
the browser fails to start, the result is skipped with ``browser_unavailable``.
Google AI 概览, Google AI Mode, and Copilot stay stubs.

Camoufox is optional. Set ``GEO_BROWSER_ENGINE=camoufox``. If that package
cannot be imported or fails to launch, collection falls back to headless
Chromium. Proxy comes from the ``proxy`` argument or ``GEO_BROWSER_PROXY``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from data_collectors.providers.answers import ScrapeResult

STUB_ENGINES = ("Google AI 概览", "Google AI Mode", "Copilot")
REAL_ENGINES = {
    "ChatGPT 网页": "https://chatgpt.com/",
    "Perplexity 网页": "https://www.perplexity.ai/",
    "Gemini 网页": "https://gemini.google.com/app",
    "豆包": "https://www.doubao.com/chat/",
    "元宝": "https://yuanbao.tencent.com/",
    "Kimi 网页": "https://kimi.moonshot.cn/",
}
_MAX_HTML = 1_500_000
_MAX_TEXT = 100_000


class BrowserUnavailable(RuntimeError):
    """Playwright is missing or the browser process could not start."""


def is_stub_engine(engine: str) -> bool:
    return engine in STUB_ENGINES


def browser_runtime_status() -> tuple[bool, str]:
    """Check that Playwright can be imported. Does not open a site."""
    choice = (os.environ.get("GEO_BROWSER_ENGINE") or "chromium").strip().lower()
    note = ""
    if choice == "camoufox":
        try:
            import camoufox  # noqa: F401
        except Exception:
            note = "Camoufox 未安装，将回退到 Playwright Chromium。"
    try:
        import playwright  # noqa: F401
    except Exception as exc:
        return False, f"browser_unavailable: 未能导入 Playwright（{exc}）。可执行 playwright install chromium。"
    proxy = (os.environ.get("GEO_BROWSER_PROXY") or "").strip()
    extra = " 已读取 GEO_BROWSER_PROXY。" if proxy else ""
    return True, (note + "Playwright 可导入，测试连接不会打开目标网站。" + extra).strip()


def persist_artifacts(directory: Path | None, html: str, text: str, png: bytes | None, screenshot_error: str = "") -> dict:
    """Write HTML/text and an optional screenshot. Failures are recorded, not raised."""
    saved = {"html_path": "", "text_path": "", "screenshot_path": "", "screenshot_error": screenshot_error}
    if directory is None:
        return saved
    try:
        directory.mkdir(parents=True, exist_ok=True)
        html_path = directory / "page.html"
        html_path.write_text((html or "")[:_MAX_HTML], encoding="utf-8")
        saved["html_path"] = str(html_path)
        text_path = directory / "page.txt"
        text_path.write_text((text or "")[:_MAX_TEXT], encoding="utf-8")
        saved["text_path"] = str(text_path)
        if png:
            shot = directory / "page.png"
            shot.write_bytes(png)
            saved["screenshot_path"] = str(shot)
    except Exception as exc:
        saved["screenshot_error"] = (f"{screenshot_error} {type(exc).__name__}: {exc}").strip()[:300]
    return saved


def _stub_result(engine: str, prompt: str, *, country: str, language: str, web_search: bool) -> ScrapeResult:
    return ScrapeResult(
        provider_id="browser",
        engine=engine,
        access="scraped",
        status="skipped",
        error_code="browser_stub",
        text="",
        raw_output={
            "implementation": "playwright+camoufox",
            "status": "stub",
            "message": "P1 浏览器采集只保留接口，尚未执行页面自动化。",
            "country": country,
            "language": language,
            "web_search": web_search,
            "prompt_excerpt": prompt[:120],
        },
    )


def _unavailable(engine: str, message: str) -> ScrapeResult:
    return ScrapeResult(
        provider_id="browser",
        engine=engine,
        access="scraped",
        status="skipped",
        error_code="browser_unavailable",
        text="",
        raw_output={"implementation": "playwright", "message": message[:300], "sampled": True},
    )


def _apply_cookie_note(context, note: str) -> bool:
    raw = (note or "").strip()
    if not raw.startswith("["):
        return False
    try:
        cookies = json.loads(raw)
    except json.JSONDecodeError:
        return False
    if not isinstance(cookies, list):
        return False
    cleaned = []
    for item in cookies[:30]:
        if not isinstance(item, dict) or not item.get("name") or item.get("value") is None:
            continue
        cookie = {"name": str(item["name"])[:200], "value": str(item["value"])[:4000]}
        if item.get("url"):
            cookie["url"] = str(item["url"])[:500]
        elif item.get("domain"):
            cookie["domain"] = str(item["domain"])[:200]
            cookie["path"] = str(item.get("path") or "/")[:200]
        else:
            continue
        cleaned.append(cookie)
    if not cleaned:
        return False
    context.add_cookies(cleaned)
    return True


def _try_submit(page, prompt: str) -> None:
    for selector in ("textarea", "[contenteditable='true']", "input[type='search']", "input[type='text']"):
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            locator.click(timeout=2000)
            locator.fill((prompt or "")[:500], timeout=2000)
            page.keyboard.press("Enter")
            return
        except Exception:
            continue


def _read_page(page, prompt: str, timeout_ms: int) -> tuple[str, str, bytes | None, str]:
    _try_submit(page, prompt)
    try:
        page.wait_for_timeout(min(4000, timeout_ms))
    except Exception:
        pass
    html = ""
    text = ""
    png = None
    screenshot_error = ""
    try:
        html = page.content() or ""
    except Exception as exc:
        screenshot_error = f"html:{type(exc).__name__}"
    try:
        text = page.inner_text("body") or ""
    except Exception as exc:
        screenshot_error = (screenshot_error + f" text:{type(exc).__name__}").strip()
    try:
        png = page.screenshot(full_page=False)
    except Exception as exc:
        screenshot_error = (screenshot_error + f" screenshot:{type(exc).__name__}:{exc}").strip()[:300]
    return html, text, png, screenshot_error


def _launch_kwargs(proxy_url: str) -> dict:
    kwargs = {"headless": True}
    if proxy_url:
        kwargs["proxy"] = {"server": proxy_url}
    return kwargs


def _run_chromium(*, url: str, prompt: str, timeout_ms: int, proxy_url: str, session_note: str) -> dict:
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    browser = None
    try:
        browser = playwright.chromium.launch(**_launch_kwargs(proxy_url))
        context = browser.new_context()
        applied = False
        try:
            applied = _apply_cookie_note(context, session_note)
        except Exception:
            applied = False
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        html, text, png, screenshot_error = _read_page(page, prompt, timeout_ms)
        return {
            "text": text,
            "html": html,
            "png": png,
            "screenshot_error": screenshot_error,
            "session_note_applied": applied,
            "implementation": "playwright-chromium",
            "fallback": "",
        }
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        try:
            playwright.stop()
        except Exception:
            pass


def _run_camoufox(*, url: str, prompt: str, timeout_ms: int, proxy_url: str, session_note: str) -> dict:
    from camoufox.sync_api import Camoufox

    kwargs = {"headless": True}
    if proxy_url:
        kwargs["proxy"] = {"server": proxy_url}
    with Camoufox(**kwargs) as browser:
        page = browser.new_page()
        applied = False
        try:
            applied = _apply_cookie_note(browser, session_note) if hasattr(browser, "add_cookies") else False
        except Exception:
            applied = False
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        html, text, png, screenshot_error = _read_page(page, prompt, timeout_ms)
        return {
            "text": text,
            "html": html,
            "png": png,
            "screenshot_error": screenshot_error,
            "session_note_applied": applied,
            "implementation": "camoufox",
            "fallback": "",
        }


def _default_runner(*, engine: str, prompt: str, timeout: int, proxy: str, session_note: str, artifact_dir: Path | None, country: str = "", language: str = "") -> dict:
    url = REAL_ENGINES[engine]
    proxy_url = (proxy or os.environ.get("GEO_BROWSER_PROXY") or "").strip()
    timeout_ms = max(5, min(int(timeout or 45), 180)) * 1000
    choice = (os.environ.get("GEO_BROWSER_ENGINE") or "chromium").strip().lower()
    produced = None
    fallback = ""
    if choice == "camoufox":
        try:
            produced = _run_camoufox(url=url, prompt=prompt, timeout_ms=timeout_ms, proxy_url=proxy_url, session_note=session_note)
        except Exception as exc:
            fallback = f"camoufox_fallback_chromium:{type(exc).__name__}"
            produced = None
    if produced is None:
        try:
            produced = _run_chromium(url=url, prompt=prompt, timeout_ms=timeout_ms, proxy_url=proxy_url, session_note=session_note)
        except ImportError as exc:
            raise BrowserUnavailable(f"playwright_import_failed: {exc}") from exc
        except Exception as exc:
            message = str(exc)[:240]
            if proxy_url:
                message = message.replace(proxy_url, "****")
            raise BrowserUnavailable(message or type(exc).__name__) from exc
    if fallback:
        produced["fallback"] = fallback
    return produced


def collect_browser_answer(
    engine: str,
    prompt: str,
    *,
    country: str = "",
    language: str = "",
    web_search: bool = True,
    timeout: int = 45,
    proxy: str = "",
    session_note: str = "",
    artifact_dir: Path | None = None,
    runner=None,
) -> ScrapeResult:
    """Collect one page. Never raises. Stub engines do not launch a browser."""
    if engine in STUB_ENGINES or engine not in REAL_ENGINES:
        code = "browser_stub" if engine in STUB_ENGINES or engine not in REAL_ENGINES else "unsupported_engine"
        if engine in STUB_ENGINES:
            return _stub_result(engine, prompt, country=country, language=language, web_search=web_search)
        return ScrapeResult(
            provider_id="browser",
            engine=engine,
            access="scraped",
            status="skipped",
            error_code=code,
            text="",
            raw_output={"message": "没有这个网页引擎的采集骨架。"},
        )
    invoke = runner or _default_runner
    try:
        produced = invoke(
            engine=engine,
            prompt=prompt,
            timeout=timeout,
            proxy=proxy,
            session_note=session_note,
            artifact_dir=artifact_dir,
            country=country,
            language=language,
        )
    except Exception as exc:
        message = str(exc)[:240]
        if proxy:
            message = message.replace(proxy, "****")
        return _unavailable(engine, message or type(exc).__name__)
    if isinstance(produced, ScrapeResult):
        return produced
    text = str((produced or {}).get("text") or "")[:_MAX_TEXT]
    html = str((produced or {}).get("html") or "")
    saved = persist_artifacts(
        artifact_dir,
        html,
        text,
        produced.get("png") if isinstance(produced, dict) else None,
        str((produced or {}).get("screenshot_error") or ""),
    )
    raw = {
        "implementation": (produced or {}).get("implementation") or "playwright",
        "fallback": (produced or {}).get("fallback") or "",
        "session_note_applied": bool((produced or {}).get("session_note_applied")),
        "sampled": True,
        "html_path": saved["html_path"],
        "text_path": saved["text_path"],
        "screenshot_path": saved["screenshot_path"],
        "screenshot_error": saved["screenshot_error"],
        "country": country,
        "language": language,
    }
    return ScrapeResult(
        provider_id="browser",
        engine=engine,
        access="scraped",
        status="ok",
        error_code="",
        text=text,
        raw_output=raw,
    )
