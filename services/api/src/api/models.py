from __future__ import annotations

from pydantic import BaseModel, Field


class KeywordSpecInput(BaseModel):
    keyword: str
    engine: str


class GeoQueryInput(BaseModel):
    query: str
    engine_hint: str = "global"


class CollectRequest(BaseModel):
    domain: str
    url: str
    brand_name: str = Field(alias="brand_name")
    keywords: list[KeywordSpecInput]
    geo_queries: list[GeoQueryInput]


class AnalyzeRequest(CollectRequest):
    pass


class CollectResponse(BaseModel):
    domain: str
    seo: dict | None
    aeo: dict | None
    geo: dict | None
    errors: list[dict]


class AnalyzeResponse(BaseModel):
    domain: str
    overall_score: float | None
    dimensions: dict
    recommendations: list[dict]
    collection_errors: list[dict]
