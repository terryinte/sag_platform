"""Turn provider payloads into answer text, search queries and citations.

Only structured provider citations are marked ``provider_citation``. Inline
links in the prose are not promoted to citations.
"""

from __future__ import annotations

from urllib.parse import urlparse


def domain_of(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _citation(url: str, title: str, position: int, payload_path: str) -> dict:
    return {
        "url": url,
        "domain": domain_of(url),
        "title": title or "",
        "position": position,
        "source_kind": "provider_citation",
        "payload_path": payload_path,
    }


def extract_openai_response(payload: dict) -> tuple[str, list[dict], list[str]]:
    texts: list[str] = []
    citations: list[dict] = []
    queries: list[str] = []
    for block_index, block in enumerate(payload.get("output") or []):
        if not isinstance(block, dict):
            continue
        action = block.get("action") or {}
        if isinstance(action, dict) and action.get("query"):
            queries.append(str(action["query"]))
        for content_index, content in enumerate(block.get("content") or []):
            if not isinstance(content, dict):
                continue
            if content.get("text"):
                texts.append(str(content["text"]))
            for ann_index, annotation in enumerate(content.get("annotations") or []):
                if not isinstance(annotation, dict):
                    continue
                if annotation.get("type") not in {None, "url_citation"}:
                    continue
                url = annotation.get("url") or annotation.get("uri")
                if not url:
                    continue
                citations.append(
                    _citation(
                        str(url),
                        str(annotation.get("title") or ""),
                        len(citations) + 1,
                        f"output[{block_index}].content[{content_index}].annotations[{ann_index}]",
                    )
                )
    return "\n".join(texts).strip(), citations, queries


def extract_perplexity_response(payload: dict) -> tuple[str, list[dict], list[str]]:
    text = ""
    if payload.get("output_text"):
        text = str(payload["output_text"])
    elif payload.get("text"):
        text = str(payload["text"])
    else:
        choices = payload.get("choices") or []
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
            text = str(message.get("content") or "")
    citations: list[dict] = []
    search_results = payload.get("search_results") or payload.get("citations") or []
    if isinstance(search_results, list):
        for index, item in enumerate(search_results):
            if isinstance(item, str):
                citations.append(_citation(item, "", index + 1, f"citations[{index}]"))
            elif isinstance(item, dict) and item.get("url"):
                citations.append(
                    _citation(
                        str(item["url"]),
                        str(item.get("title") or ""),
                        index + 1,
                        f"search_results[{index}].url",
                    )
                )
    queries = [str(item) for item in payload.get("web_queries") or [] if item]
    return text.strip(), citations, queries


def extract_gemini_response(payload: dict) -> tuple[str, list[dict], list[str]]:
    texts: list[str] = []
    citations: list[dict] = []
    queries: list[str] = []
    for candidate_index, candidate in enumerate(payload.get("candidates") or []):
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            if isinstance(part, dict) and part.get("text"):
                texts.append(str(part["text"]))
        grounding = candidate.get("groundingMetadata") or candidate.get("grounding_metadata") or {}
        for query in grounding.get("webSearchQueries") or grounding.get("web_search_queries") or []:
            queries.append(str(query))
        chunks = grounding.get("groundingChunks") or grounding.get("grounding_chunks") or []
        for index, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                continue
            web = chunk.get("web") or {}
            url = web.get("uri") or web.get("url")
            if not url:
                continue
            citations.append(
                _citation(
                    str(url),
                    str(web.get("title") or ""),
                    index + 1,
                    f"candidates[{candidate_index}].groundingMetadata.groundingChunks[{index}].web.uri",
                )
            )
    return "\n".join(texts).strip(), citations, queries


def extract_claude_response(payload: dict) -> tuple[str, list[dict], list[str]]:
    texts: list[str] = []
    citations: list[dict] = []
    queries: list[str] = []
    for block_index, block in enumerate(payload.get("content") or []):
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            texts.append(str(block["text"]))
        if block.get("type") == "server_tool_use" and isinstance(block.get("input"), dict):
            query = block["input"].get("query")
            if query:
                queries.append(str(query))
        for cit_index, citation in enumerate(block.get("citations") or []):
            if isinstance(citation, dict) and citation.get("url"):
                citations.append(
                    _citation(
                        str(citation["url"]),
                        str(citation.get("title") or ""),
                        len(citations) + 1,
                        f"content[{block_index}].citations[{cit_index}]",
                    )
                )
        if block.get("type") in {"web_search_tool_result", "web_search_result"}:
            items = block.get("content") if isinstance(block.get("content"), list) else [block]
            for item_index, item in enumerate(items):
                if isinstance(item, dict) and item.get("url"):
                    citations.append(
                        _citation(
                            str(item["url"]),
                            str(item.get("title") or ""),
                            len(citations) + 1,
                            f"content[{block_index}].content[{item_index}].url",
                        )
                    )
    return "\n".join(texts).strip(), citations, queries


def extract_chat_completions(payload: dict) -> tuple[str, list[dict], list[str]]:
    text, citations, queries = extract_perplexity_response(payload)
    if text or citations:
        return text, citations, queries
    return "", [], []
