"""LLM-as-JSON mention judge with local evidence checks.

The model may propose mentions, recommendations and a single first position.
This module never trusts that proposal until the quote is found in the answer
body and at most one entity is marked as the unique first.
"""

from __future__ import annotations

import json
import re

PARSER_VERSION = "judge-1"

_POSITIVE = ("推荐", "最好", "首选", "值得买", "best", "recommend", "top pick", "首选")
_NEGATIVE = ("不推荐", "不建议", "较差", "差评", "avoid", "not recommended")
_REC_VALUES = {"positive", "negative", "mentioned", "uncertain"}
_STATE_VALUES = {"unique", "tied", "none", "unresolved"}
_SENTIMENT_VALUES = {"positive", "neutral", "mixed", "negative"}


def find_alias(text: str, alias: str) -> int:
    if not alias:
        return -1
    target = alias.casefold()
    folded = text.casefold()
    if len(folded) == len(text) and len(target) == len(alias):
        return folded.find(target)
    for index in range(len(text)):
        for size in range(max(1, len(alias) - 1), len(alias) + 4):
            window = text[index : index + size]
            if window and window.casefold() == target:
                return index
    return -1


def _quote_in_text(quote: str, text: str) -> bool:
    cleaned = (quote or "").strip()
    if not cleaned:
        return False
    return cleaned.casefold() in text.casefold()


def _sentence_around(text: str, index: int, alias: str) -> str:
    start_marks = [text.rfind("\n", 0, index), text.rfind("。", 0, index), text.rfind("！", 0, index)]
    start = max(start_marks)
    start = 0 if start < 0 else start + 1
    end_marks = [pos for mark in ("\n", "。", "！", ".", "?") if (pos := text.find(mark, index + len(alias))) >= 0]
    end = min(end_marks) + 1 if end_marks else len(text)
    snippet = text[start:end].strip()
    if alias.casefold() not in snippet.casefold():
        snippet = text[index : index + len(alias)]
    return snippet


def validate_judge_result(raw_text: str, result: dict) -> dict:
    """Force quote evidence and a single unique-first. Failures become unresolved."""
    entities_in = result.get("entities") if isinstance(result, dict) else None
    if not isinstance(entities_in, list):
        return {
            "parser_version": PARSER_VERSION,
            "sample_state": "unresolved",
            "entities": [],
            "counts_for_first_position": False,
            "reason": "invalid_schema",
        }

    normalized: list[dict] = []
    for item in entities_in:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("mention_quote") or "")
        rec_quote = str(item.get("recommendation_quote") or "")
        recommendation = item.get("recommendation") or "mentioned"
        if recommendation not in _REC_VALUES:
            recommendation = "uncertain"
        state = item.get("first_mention_state") or "none"
        if state not in _STATE_VALUES:
            state = "unresolved"
        sentiment = item.get("sentiment") if item.get("sentiment") in _SENTIMENT_VALUES else "neutral"
        quote_ok = _quote_in_text(quote, raw_text)
        rec_quote_ok = True
        if recommendation in {"positive", "negative"}:
            rec_quote_ok = _quote_in_text(rec_quote, raw_text)
        valid = quote_ok and rec_quote_ok
        if not valid:
            recommendation = "uncertain"
            state = "unresolved"
        normalized.append(
            {
                "name": str(item.get("name") or ""),
                "role": item.get("role") or "other",
                "recommendation": recommendation,
                "mention_quote": quote,
                "recommendation_quote": rec_quote,
                "first_mention_offset": item.get("first_mention_offset"),
                "first_mention_state": state,
                "sentiment": sentiment,
                "valid": valid,
                "counts_as_mention": bool(valid and recommendation in {"positive", "negative", "mentioned"}),
                "counts_as_first": False,
            }
        )

    unique_indexes = [
        index
        for index, entity in enumerate(normalized)
        if entity["first_mention_state"] == "unique" and entity["valid"]
    ]
    if len(unique_indexes) > 1:
        for index in unique_indexes:
            normalized[index]["first_mention_state"] = "unresolved"
            normalized[index]["counts_as_first"] = False
        counts_for_first = False
    elif len(unique_indexes) == 1:
        normalized[unique_indexes[0]]["counts_as_first"] = True
        counts_for_first = True
    else:
        counts_for_first = False

    if not entities_in:
        sample_state = "ok"
    elif any(entity["valid"] for entity in normalized):
        sample_state = "ok"
    else:
        sample_state = "unresolved"

    return {
        "parser_version": PARSER_VERSION,
        "sample_state": sample_state,
        "entities": normalized,
        "counts_for_first_position": counts_for_first,
        "reason": "",
    }


def heuristic_judge(raw_text: str, subjects: list[dict]) -> dict:
    """Local stand-in used when no judge model is configured. Same validation path."""
    entities: list[dict] = []
    for subject in subjects:
        aliases = [subject.get("name") or "", *list(subject.get("aliases") or [])]
        hit: tuple[int, str] | None = None
        for alias in aliases:
            if not alias or len(alias.strip()) < 2:
                continue
            index = find_alias(raw_text, alias.strip())
            if index >= 0 and (hit is None or index < hit[0]):
                hit = (index, alias.strip())
        if hit is None:
            continue
        index, alias = hit
        quote = _sentence_around(raw_text, index, alias)
        window = quote.casefold()
        if any(word.casefold() in window for word in _NEGATIVE):
            recommendation = "negative"
            sentiment = "negative"
        elif any(word.casefold() in window for word in _POSITIVE):
            recommendation = "positive"
            sentiment = "positive"
        else:
            recommendation = "mentioned"
            sentiment = "neutral"
        entities.append(
            {
                "name": subject.get("name") or alias,
                "role": subject.get("role") or "other",
                "recommendation": recommendation,
                "mention_quote": quote,
                "recommendation_quote": quote if recommendation in {"positive", "negative"} else "",
                "first_mention_offset": index,
                "first_mention_state": "none",
                "sentiment": sentiment,
            }
        )

    ranked = sorted(entities, key=lambda item: item["first_mention_offset"])
    positives = [item for item in ranked if item["recommendation"] == "positive"]
    if len(positives) == 1:
        positives[0]["first_mention_state"] = "unique"
    elif len(ranked) == 1:
        ranked[0]["first_mention_state"] = "unique"
    elif ranked:
        for item in ranked:
            item["first_mention_state"] = "tied"
    return validate_judge_result(raw_text, {"entities": entities})


def parse_json_object(text: str) -> dict | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def judge_answer(raw_text: str, subjects: list[dict], llm_json: dict | None = None) -> dict:
    """Prefer a model JSON object, then re-validate. Fall back to the local heuristic."""
    if llm_json is not None:
        checked = validate_judge_result(raw_text, llm_json)
        if checked["sample_state"] != "unresolved" or checked["entities"]:
            checked["reviewer"] = "llm"
            return checked
    checked = heuristic_judge(raw_text, subjects)
    checked["reviewer"] = "heuristic"
    return checked
