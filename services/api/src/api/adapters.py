from __future__ import annotations

from dataclasses import asdict

from api.models import CollectRequest
from analysis_engine.models import CompositeReport
from data_collectors.models import CollectionPayload, GeoQuerySpec, KeywordSpec


def collect_request_to_inputs(request: CollectRequest) -> tuple[list[KeywordSpec], list[GeoQuerySpec]]:
    keywords = [KeywordSpec(keyword=item.keyword, engine=item.engine) for item in request.keywords]
    geo_queries = [
        GeoQuerySpec(query=item.query, engine_hint=item.engine_hint)
        for item in request.geo_queries
    ]
    return keywords, geo_queries


def collect_payload_to_dict(payload: CollectionPayload) -> dict:
    return {
        "domain": payload.domain,
        "seo": asdict(payload.seo) if payload.seo is not None else None,
        "aeo": asdict(payload.aeo) if payload.aeo is not None else None,
        "geo": asdict(payload.geo) if payload.geo is not None else None,
        "errors": [asdict(item) for item in payload.errors],
    }


def analyze_response_to_dict(report: CompositeReport, collection_errors: list[dict]) -> dict:
    return {
        "domain": report.domain,
        "overall_score": report.overall_score,
        "dimensions": {
            name: {
                "score": breakdown.score,
                "data_complete": breakdown.data_complete,
                "detail": breakdown.detail,
            }
            for name, breakdown in report.dimension_scores.items()
        },
        "recommendations": [
            {
                "priority": item.priority,
                "dimension": item.dimension,
                "title": item.title,
                "description": item.description,
            }
            for item in report.recommendations
        ],
        "collection_errors": collection_errors,
    }
