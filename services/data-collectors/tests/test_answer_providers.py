import httpx

from data_collectors.providers.answers import (
    BrowserCollectorStub,
    OpenAIWebSearchProvider,
    build_answer_providers,
    resolve_provider,
)
from data_collectors.providers.extractors import extract_gemini_response, extract_openai_response


def test_missing_api_key_skips_without_calling_network():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("network should not be called")

    provider = OpenAIWebSearchProvider("", httpx.Client(transport=httpx.MockTransport(handler)))
    result = provider.run("ChatGPT", "best charger")

    assert result.status == "skipped"
    assert result.access == "mock"
    assert result.error_code == "missing_api_key"
    assert "OPENAI_API_KEY" in result.text


def test_openai_web_search_extracts_citation_from_payload():
    payload = {
        "model": "gpt-4.1-mini",
        "output": [
            {"type": "web_search_call", "action": {"query": "best 100W charger"}},
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "UGREEN Nexode is a solid pick.",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://www.ugreen.com/nexode",
                                "title": "Nexode",
                            }
                        ],
                    }
                ],
            },
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        body = request.read().decode()
        assert "web_search" in body
        assert "sk-test" not in body or "Bearer" in request.headers.get("authorization", "")
        return httpx.Response(200, json=payload)

    provider = OpenAIWebSearchProvider("sk-test", httpx.Client(transport=httpx.MockTransport(handler)))
    result = provider.run("ChatGPT", "best charger")

    assert result.status == "ok"
    assert result.access == "api"
    assert result.citations[0]["source_kind"] == "provider_citation"
    assert result.citations[0]["domain"] == "ugreen.com"
    assert result.web_queries == ["best 100W charger"]
    text, citations, queries = extract_openai_response(payload)
    assert "UGREEN" in text
    assert citations[0]["url"].endswith("/nexode")
    assert queries == ["best 100W charger"]


def test_gemini_grounding_chunks_stay_provider_citations():
    text, citations, queries = extract_gemini_response(
        {
            "candidates": [
                {
                    "content": {"parts": [{"text": "See the roundup."}]},
                    "groundingMetadata": {
                        "webSearchQueries": ["best charger"],
                        "groundingChunks": [
                            {"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc", "title": "Roundup"}}
                        ],
                    },
                }
            ]
        }
    )

    assert "roundup" in text.lower()
    assert citations[0]["domain"] == "vertexaisearch.cloud.google.com"
    assert citations[0]["source_kind"] == "provider_citation"
    assert queries == ["best charger"]


def test_browser_stub_does_not_raise():
    result = BrowserCollectorStub().run("Google AI 概览", "best nas", country="US", language="en-US")

    assert result.status == "skipped"
    assert result.error_code == "browser_stub"
    assert result.access == "scraped"
    assert result.raw_output["implementation"] == "playwright+camoufox"
    assert result.text == ""


def test_registry_resolves_official_engine_and_unknown():
    providers = build_answer_providers({})
    chatgpt = resolve_provider(providers, "ChatGPT")
    browser = resolve_provider(providers, "Copilot")

    assert chatgpt.id == "openai"
    assert browser.id == "browser"
    assert resolve_provider(providers, "不存在的引擎") is None
