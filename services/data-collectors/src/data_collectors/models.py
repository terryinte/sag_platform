from __future__ import annotations

from dataclasses import dataclass, field

from analysis_engine.models import AeoInput, GeoInput, SeoInput


@dataclass
class KeywordSpec:
    keyword: str
    engine: str


@dataclass
class GeoQuerySpec:
    query: str
    engine_hint: str = "global"


@dataclass
class CollectionError:
    provider: str
    operation: str
    retryable: bool
    message: str


@dataclass
class CollectionPayload:
    domain: str
    seo: SeoInput | None = None
    aeo: AeoInput | None = None
    geo: GeoInput | None = None
    errors: list[CollectionError] = field(default_factory=list)
