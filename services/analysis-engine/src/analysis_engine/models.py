"""Shared dataclasses for the analysis engine's scoring pipeline.

These are the data contracts every scoring module (SEO/AEO/GEO/website-audit)
and the composite aggregator depend on. Phase 2 (data collection layer) is
responsible for populating SeoInput/AeoInput/GeoInput from real data sources
(DataForSEO, LLM query APIs); this package only consumes them.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KeywordRanking:
    keyword: str
    engine: str  # "google" | "bing" | "baidu"
    position: int | None
    search_volume: int | None = None


@dataclass
class SeoInput:
    domain: str
    keyword_rankings: list[KeywordRanking] = field(default_factory=list)
    indexed_pages_count: int | None = None
    total_pages_count: int | None = None


@dataclass
class FeaturedSnippetHit:
    keyword: str
    engine: str
    snippet_type: str  # "featured_snippet" | "paa" | "none"


@dataclass
class AeoInput:
    domain: str
    snippet_hits: list[FeaturedSnippetHit] = field(default_factory=list)
    total_keywords_checked: int = 0


@dataclass
class BrandMentionResult:
    query: str
    engine: str  # "chatgpt" | "claude" | "gemini" | "ernie" | "qwen" | "deepseek" | ...
    brand_mentioned: bool
    mention_position: int | None = None
    cited_as_source: bool = False


@dataclass
class GeoInput:
    brand_name: str
    domain: str
    mention_results: list[BrandMentionResult] = field(default_factory=list)


@dataclass
class ScoreBreakdown:
    """A single dimension's (seo/aeo/geo/website_audit) score with detail."""

    dimension: str
    score: float | None  # None means the dimension's data was unavailable
    data_complete: bool
    detail: dict = field(default_factory=dict)


@dataclass
class Recommendation:
    priority: str  # "high" | "medium" | "low"
    dimension: str
    title: str
    description: str


@dataclass
class CompositeReport:
    domain: str
    overall_score: float | None
    dimension_scores: dict[str, ScoreBreakdown]
    recommendations: list[Recommendation]
