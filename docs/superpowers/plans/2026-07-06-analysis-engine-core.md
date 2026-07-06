# Analysis Engine Core (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone, installable Python library + CLI (`analysis-engine`) that computes SEO/AEO/GEO composite scores and prioritized recommendations for a customer's brand/domain, using `geo-optimizer-skill` for the website AI-friendliness sub-score.

**Architecture:** A single Python package (`services/analysis-engine/`) with pure-function scoring modules per dimension (SEO, AEO, GEO, website audit), a composite-score aggregator that renormalizes weights when a dimension's data is missing, a recommendations generator, and a `click`-based CLI that wires it all together and prints a JSON report. This package has **no** dependency on FastAPI, Celery, or a database — those arrive in later phases. The scoring modules accept plain dataclasses as input; Phase 2 (data collection layer) will be responsible for populating those dataclasses from DataForSEO / LLM query results — this plan defines the data contracts they must satisfy but stubs them with fixture data in tests.

**Tech Stack:** Python 3.11+, `geo-optimizer-skill` (PyPI, MIT license) for the website audit sub-score, `click` for the CLI, `pytest` for testing. No network calls in tests — the `geo_optimizer.audit()` call is mocked everywhere except the (out-of-scope-for-CI) manual smoke test noted in Task 9.

## Global Constraints

- Python `>=3.11` (matches the sandboxed dev environment; `geo-optimizer-skill` requires `>=3.9` so this is compatible).
- `geo-optimizer-skill` version pin: `>=4.14.1,<5.0.0` (current PyPI release verified during design research; MIT licensed).
- `click` version pin: `>=8.1,<9.0`.
- `pytest` version pin (dev only): `>=8.0,<9.0`.
- Package lives at `services/analysis-engine/` — a self-contained installable project with its own `pyproject.toml`, matching the future multi-service layout (Phase 2 will add `services/data-collectors/`, Phase 3 `services/api/`, etc.).
- All tests run offline — no real HTTP calls to `geo-optimizer-skill`, DataForSEO, or LLM APIs. Every call that would hit the network is mocked/monkeypatched in tests.
- Every commit message includes the `Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>` trailer.
- Follow TDD: write the failing test first, watch it fail, then implement.

---

## File Structure

```
services/analysis-engine/
  pyproject.toml
  README.md
  src/analysis_engine/
    __init__.py
    models.py               # Shared dataclasses: inputs, ScoreBreakdown, CompositeReport, Recommendation
    scoring/
      __init__.py
      seo.py                 # score_seo(SeoInput) -> ScoreBreakdown
      aeo.py                 # score_aeo(AeoInput) -> ScoreBreakdown
      geo.py                 # score_geo(GeoInput) -> ScoreBreakdown
      website_audit.py        # score_website_audit(url) -> ScoreBreakdown (wraps geo_optimizer.audit)
      composite.py             # compute_composite_score(...) -> CompositeReport
    recommendations.py         # generate_recommendations(CompositeReport) -> list[Recommendation]
    cli.py                     # `analyze` click command: reads JSON input files, prints JSON report
  tests/
    test_models.py
    test_seo_scoring.py
    test_aeo_scoring.py
    test_geo_scoring.py
    test_website_audit.py
    test_composite.py
    test_recommendations.py
    test_cli.py
    test_integration.py
```

**Design notes / assumptions (documented here since no further stakeholder input was requested for exact formulas):**
- **SEO score** = weighted blend of keyword-ranking score (70%) and page-indexation ratio (30%). Ranking score buckets: position 1-3 → 100, 4-10 → 80, 11-20 → 60, 21-50 → 40, 51-100 → 20, unranked → 0; weighted by `search_volume` when present.
- **AEO score** = `(featured_snippet_hits × 1.0 + PAA_hits × 0.5) / total_keywords_checked × 100`, capped at 100.
- **GEO score** = average across all brand-mention queries of: not mentioned → 0; mentioned position 1 → 100; position 2-3 → 80; mentioned but position unknown/>3 → 60; ×1.3 multiplier (capped at 100) if the brand's URL was cited as a source.
- **Website audit score** = passthrough of `geo_optimizer.audit(url).score` (already 0-100 per the library's own 8-category rubric).
- **Composite score** = weighted average with weights `seo=0.30, aeo=0.20, geo=0.35, website_audit=0.15`. When a dimension has no data, its weight is dropped and the remaining weights are renormalized to sum to 1.0. If all four dimensions are missing data, `overall_score` is `None`.
- **Recommendations**: any dimension scoring `< 80` gets a recommendation (priority `high` if `<40`, `medium` if `<70`, else `low`); any dimension with missing data gets a `high` priority "data missing" recommendation; `website_audit`'s own raw recommendation strings (from `geo_optimizer`) are also surfaced individually at the audit dimension's priority level. Final list sorted by priority (high → medium → low) then dimension name.

These weights/thresholds are intentionally simple, isolated in `composite.py` / `recommendations.py` constants so they're trivial to retune once real customer data is available — no other module needs to change if they're adjusted later.

---

### Task 1: Project scaffolding & shared data models

**Files:**
- Create: `services/analysis-engine/pyproject.toml`
- Create: `services/analysis-engine/README.md`
- Create: `services/analysis-engine/src/analysis_engine/__init__.py`
- Create: `services/analysis-engine/src/analysis_engine/models.py`
- Test: `services/analysis-engine/tests/test_models.py`

**Interfaces:**
- Produces: dataclasses `KeywordRanking`, `SeoInput`, `FeaturedSnippetHit`, `AeoInput`, `BrandMentionResult`, `GeoInput`, `ScoreBreakdown`, `Recommendation`, `CompositeReport` — all defined in `analysis_engine.models`, importable as `from analysis_engine.models import ...`. Every later task consumes these exact names/fields.

- [ ] **Step 1: Create the package scaffolding**

Create `services/analysis-engine/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "analysis-engine"
version = "0.1.0"
description = "SEO/AEO/GEO composite scoring engine for the SAG diagnostic platform"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "geo-optimizer-skill>=4.14.1,<5.0.0",
    "click>=8.1,<9.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0,<9.0",
]

[project.scripts]
analysis-engine = "analysis_engine.cli:analyze"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

Create `services/analysis-engine/README.md`:

```markdown
# Analysis Engine

SEO/AEO/GEO composite scoring engine for the SAG diagnostic platform.

Computes a 0-100 composite visibility score (plus per-dimension SEO/AEO/GEO/website-audit
scores and prioritized recommendations) for a customer's brand and domain.

## Install (editable, for development)

\`\`\`bash
cd services/analysis-engine
pip install -e ".[dev]"
\`\`\`

## Run the CLI

\`\`\`bash
analysis-engine --domain example.com --url https://example.com --brand-name Acme
\`\`\`

Optionally pass `--seo-data`, `--aeo-data`, `--geo-data` JSON files (see
`tests/test_cli.py` for the expected shape) to include SEO/AEO/GEO scores —
these come from the Phase 2 data-collection layer once it exists. Without
them, those dimensions are reported as missing data with a high-priority
recommendation.

## Run tests

\`\`\`bash
pytest
\`\`\`
```

Create `services/analysis-engine/src/analysis_engine/__init__.py`:

```python
"""Analysis Engine — SEO/AEO/GEO composite scoring for the SAG diagnostic platform."""

__version__ = "0.1.0"
```

- [ ] **Step 2: Write the failing test for the shared data models**

Create `services/analysis-engine/tests/test_models.py`:

```python
from analysis_engine.models import (
    AeoInput,
    BrandMentionResult,
    CompositeReport,
    FeaturedSnippetHit,
    GeoInput,
    KeywordRanking,
    Recommendation,
    ScoreBreakdown,
    SeoInput,
)


def test_seo_input_defaults_to_empty_rankings():
    seo_input = SeoInput(domain="example.com")
    assert seo_input.keyword_rankings == []
    assert seo_input.indexed_pages_count is None
    assert seo_input.total_pages_count is None


def test_keyword_ranking_holds_expected_fields():
    ranking = KeywordRanking(keyword="widgets", engine="google", position=3, search_volume=500)
    assert ranking.keyword == "widgets"
    assert ranking.engine == "google"
    assert ranking.position == 3
    assert ranking.search_volume == 500


def test_aeo_input_defaults():
    aeo_input = AeoInput(domain="example.com")
    assert aeo_input.snippet_hits == []
    assert aeo_input.total_keywords_checked == 0


def test_featured_snippet_hit_fields():
    hit = FeaturedSnippetHit(keyword="widgets", engine="google", snippet_type="paa")
    assert hit.snippet_type == "paa"


def test_geo_input_defaults():
    geo_input = GeoInput(brand_name="Acme", domain="acme.com")
    assert geo_input.mention_results == []


def test_brand_mention_result_defaults():
    mention = BrandMentionResult(query="best widget", engine="chatgpt", brand_mentioned=True)
    assert mention.mention_position is None
    assert mention.cited_as_source is False


def test_score_breakdown_fields():
    breakdown = ScoreBreakdown(dimension="seo", score=75.0, data_complete=True)
    assert breakdown.detail == {}


def test_recommendation_fields():
    rec = Recommendation(priority="high", dimension="seo", title="t", description="d")
    assert rec.priority == "high"


def test_composite_report_fields():
    report = CompositeReport(
        domain="example.com",
        overall_score=80.0,
        dimension_scores={},
        recommendations=[],
    )
    assert report.overall_score == 80.0
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd services/analysis-engine && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'analysis_engine.models'` (or similar import error), since `models.py` does not exist yet.

- [ ] **Step 4: Implement the data models**

Create `services/analysis-engine/src/analysis_engine/models.py`:

```python
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd services/analysis-engine && .venv/bin/pytest tests/test_models.py -v`
Expected: PASS (9 tests pass).

- [ ] **Step 6: Commit**

```bash
cd services/analysis-engine
git add pyproject.toml README.md src/analysis_engine/__init__.py src/analysis_engine/models.py tests/test_models.py
git commit -m "feat(analysis-engine): scaffold package and shared data models

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: SEO scoring

**Files:**
- Create: `services/analysis-engine/src/analysis_engine/scoring/__init__.py`
- Create: `services/analysis-engine/src/analysis_engine/scoring/seo.py`
- Test: `services/analysis-engine/tests/test_seo_scoring.py`

**Interfaces:**
- Consumes: `SeoInput`, `KeywordRanking`, `ScoreBreakdown` from `analysis_engine.models` (Task 1).
- Produces: `score_seo(seo_input: SeoInput) -> ScoreBreakdown` in `analysis_engine.scoring.seo` — consumed by Task 6 (composite) and Task 8 (CLI).

- [ ] **Step 1: Write the failing tests**

Create `services/analysis-engine/src/analysis_engine/scoring/__init__.py` (empty file):

```python
```

Create `services/analysis-engine/tests/test_seo_scoring.py`:

```python
from analysis_engine.models import KeywordRanking, SeoInput
from analysis_engine.scoring.seo import score_seo


def test_score_seo_returns_none_when_no_data():
    result = score_seo(SeoInput(domain="example.com"))
    assert result.score is None
    assert result.data_complete is False
    assert result.dimension == "seo"


def test_score_seo_top_ranking_with_no_indexation_data_scores_100():
    seo_input = SeoInput(
        domain="example.com",
        keyword_rankings=[
            KeywordRanking(keyword="widgets", engine="google", position=1, search_volume=1000),
        ],
    )
    result = score_seo(seo_input)
    # Only the ranking component (weight 0.7) has data, so it is renormalized to 100%.
    assert result.score == 100.0
    assert result.data_complete is False


def test_score_seo_combines_ranking_and_indexation():
    seo_input = SeoInput(
        domain="example.com",
        keyword_rankings=[
            KeywordRanking(keyword="widgets", engine="google", position=1, search_volume=1000),
        ],
        indexed_pages_count=80,
        total_pages_count=100,
    )
    result = score_seo(seo_input)
    # ranking_score=100 (weight 0.7) + indexation_score=80 (weight 0.3) = 94.0
    assert result.score == 94.0
    assert result.data_complete is True


def test_score_seo_weights_by_search_volume():
    seo_input = SeoInput(
        domain="example.com",
        keyword_rankings=[
            KeywordRanking(keyword="high-volume", engine="google", position=1, search_volume=9000),
            KeywordRanking(keyword="low-volume", engine="google", position=None, search_volume=1000),
        ],
    )
    result = score_seo(seo_input)
    # weighted ranking: (100*9000 + 0*1000) / 10000 = 90.0; renormalized to 100% weight -> 90.0
    assert result.score == 90.0


def test_score_seo_not_ranked_scores_zero():
    seo_input = SeoInput(
        domain="example.com",
        keyword_rankings=[KeywordRanking(keyword="widgets", engine="google", position=None)],
    )
    result = score_seo(seo_input)
    assert result.score == 0.0


def test_score_seo_position_bucket_boundaries():
    def _position_result(position):
        seo_input = SeoInput(
            domain="example.com",
            keyword_rankings=[KeywordRanking(keyword="k", engine="google", position=position)],
        )
        return score_seo(seo_input).score

    assert _position_result(3) == 100.0
    assert _position_result(4) == 80.0
    assert _position_result(10) == 80.0
    assert _position_result(11) == 60.0
    assert _position_result(20) == 60.0
    assert _position_result(21) == 40.0
    assert _position_result(50) == 40.0
    assert _position_result(51) == 20.0
    assert _position_result(100) == 20.0
    assert _position_result(101) == 0.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd services/analysis-engine && .venv/bin/pytest tests/test_seo_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'analysis_engine.scoring.seo'`.

- [ ] **Step 3: Implement SEO scoring**

Create `services/analysis-engine/src/analysis_engine/scoring/seo.py`:

```python
"""SEO dimension scoring: keyword-ranking distribution + indexation health."""

from __future__ import annotations

from analysis_engine.models import ScoreBreakdown, SeoInput

# (max_position_inclusive, score) buckets, checked in order.
_POSITION_BUCKETS: tuple[tuple[int, float], ...] = (
    (3, 100.0),
    (10, 80.0),
    (20, 60.0),
    (50, 40.0),
    (100, 20.0),
)

_RANKING_WEIGHT = 0.7
_INDEXATION_WEIGHT = 0.3


def _position_score(position: int | None) -> float:
    if position is None:
        return 0.0
    for max_position, score in _POSITION_BUCKETS:
        if position <= max_position:
            return score
    return 0.0


def _ranking_score(seo_input: SeoInput) -> float | None:
    if not seo_input.keyword_rankings:
        return None
    total_weight = 0.0
    weighted_sum = 0.0
    for ranking in seo_input.keyword_rankings:
        weight = ranking.search_volume if ranking.search_volume else 1
        weighted_sum += _position_score(ranking.position) * weight
        total_weight += weight
    if total_weight == 0:
        return None
    return weighted_sum / total_weight


def _indexation_score(seo_input: SeoInput) -> float | None:
    if not seo_input.indexed_pages_count or not seo_input.total_pages_count:
        return None
    ratio = seo_input.indexed_pages_count / seo_input.total_pages_count
    return min(ratio, 1.0) * 100.0


def score_seo(seo_input: SeoInput) -> ScoreBreakdown:
    ranking_score = _ranking_score(seo_input)
    indexation_score = _indexation_score(seo_input)

    components: list[tuple[float, float]] = []
    if ranking_score is not None:
        components.append((ranking_score, _RANKING_WEIGHT))
    if indexation_score is not None:
        components.append((indexation_score, _INDEXATION_WEIGHT))

    if not components:
        return ScoreBreakdown(
            dimension="seo",
            score=None,
            data_complete=False,
            detail={"reason": "no keyword ranking or indexation data available"},
        )

    total_weight = sum(weight for _, weight in components)
    final_score = sum(score * weight for score, weight in components) / total_weight

    return ScoreBreakdown(
        dimension="seo",
        score=round(final_score, 2),
        data_complete=ranking_score is not None and indexation_score is not None,
        detail={
            "ranking_score": ranking_score,
            "indexation_score": indexation_score,
            "keywords_evaluated": len(seo_input.keyword_rankings),
        },
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd services/analysis-engine && .venv/bin/pytest tests/test_seo_scoring.py -v`
Expected: PASS (6 tests pass).

- [ ] **Step 5: Commit**

```bash
cd services/analysis-engine
git add src/analysis_engine/scoring/__init__.py src/analysis_engine/scoring/seo.py tests/test_seo_scoring.py
git commit -m "feat(analysis-engine): add SEO dimension scoring

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: AEO scoring

**Files:**
- Create: `services/analysis-engine/src/analysis_engine/scoring/aeo.py`
- Test: `services/analysis-engine/tests/test_aeo_scoring.py`

**Interfaces:**
- Consumes: `AeoInput`, `FeaturedSnippetHit`, `ScoreBreakdown` from `analysis_engine.models` (Task 1).
- Produces: `score_aeo(aeo_input: AeoInput) -> ScoreBreakdown` in `analysis_engine.scoring.aeo` — consumed by Task 6 (composite) and Task 8 (CLI).

- [ ] **Step 1: Write the failing tests**

Create `services/analysis-engine/tests/test_aeo_scoring.py`:

```python
from analysis_engine.models import AeoInput, FeaturedSnippetHit
from analysis_engine.scoring.aeo import score_aeo


def test_score_aeo_returns_none_when_no_keywords_checked():
    result = score_aeo(AeoInput(domain="example.com", total_keywords_checked=0))
    assert result.score is None
    assert result.data_complete is False
    assert result.dimension == "aeo"


def test_score_aeo_full_featured_snippet_coverage():
    aeo_input = AeoInput(
        domain="example.com",
        total_keywords_checked=2,
        snippet_hits=[
            FeaturedSnippetHit(keyword="a", engine="google", snippet_type="featured_snippet"),
            FeaturedSnippetHit(keyword="b", engine="google", snippet_type="featured_snippet"),
        ],
    )
    result = score_aeo(aeo_input)
    assert result.score == 100.0
    assert result.data_complete is True


def test_score_aeo_paa_gives_partial_credit():
    aeo_input = AeoInput(
        domain="example.com",
        total_keywords_checked=2,
        snippet_hits=[
            FeaturedSnippetHit(keyword="a", engine="google", snippet_type="paa"),
        ],
    )
    result = score_aeo(aeo_input)
    # 0.5 point / 2 keywords * 100 = 25.0
    assert result.score == 25.0


def test_score_aeo_no_hits_scores_zero():
    aeo_input = AeoInput(domain="example.com", total_keywords_checked=3, snippet_hits=[])
    result = score_aeo(aeo_input)
    assert result.score == 0.0


def test_score_aeo_detail_counts_hit_types():
    aeo_input = AeoInput(
        domain="example.com",
        total_keywords_checked=3,
        snippet_hits=[
            FeaturedSnippetHit(keyword="a", engine="google", snippet_type="featured_snippet"),
            FeaturedSnippetHit(keyword="b", engine="google", snippet_type="paa"),
        ],
    )
    result = score_aeo(aeo_input)
    assert result.detail["featured_snippet_hits"] == 1
    assert result.detail["paa_hits"] == 1
    assert result.detail["total_keywords_checked"] == 3
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd services/analysis-engine && .venv/bin/pytest tests/test_aeo_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'analysis_engine.scoring.aeo'`.

- [ ] **Step 3: Implement AEO scoring**

Create `services/analysis-engine/src/analysis_engine/scoring/aeo.py`:

```python
"""AEO dimension scoring: featured snippet / People-Also-Ask hit rate."""

from __future__ import annotations

from analysis_engine.models import AeoInput, ScoreBreakdown

_SNIPPET_POINTS: dict[str, float] = {
    "featured_snippet": 1.0,
    "paa": 0.5,
    "none": 0.0,
}


def score_aeo(aeo_input: AeoInput) -> ScoreBreakdown:
    if aeo_input.total_keywords_checked <= 0:
        return ScoreBreakdown(
            dimension="aeo",
            score=None,
            data_complete=False,
            detail={"reason": "no keywords checked for featured snippets/PAA"},
        )

    total_points = sum(
        _SNIPPET_POINTS.get(hit.snippet_type, 0.0) for hit in aeo_input.snippet_hits
    )
    score = min(total_points / aeo_input.total_keywords_checked * 100.0, 100.0)

    return ScoreBreakdown(
        dimension="aeo",
        score=round(score, 2),
        data_complete=True,
        detail={
            "featured_snippet_hits": sum(
                1 for hit in aeo_input.snippet_hits if hit.snippet_type == "featured_snippet"
            ),
            "paa_hits": sum(1 for hit in aeo_input.snippet_hits if hit.snippet_type == "paa"),
            "total_keywords_checked": aeo_input.total_keywords_checked,
        },
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd services/analysis-engine && .venv/bin/pytest tests/test_aeo_scoring.py -v`
Expected: PASS (5 tests pass).

- [ ] **Step 5: Commit**

```bash
cd services/analysis-engine
git add src/analysis_engine/scoring/aeo.py tests/test_aeo_scoring.py
git commit -m "feat(analysis-engine): add AEO dimension scoring

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: GEO scoring

**Files:**
- Create: `services/analysis-engine/src/analysis_engine/scoring/geo.py`
- Test: `services/analysis-engine/tests/test_geo_scoring.py`

**Interfaces:**
- Consumes: `GeoInput`, `BrandMentionResult`, `ScoreBreakdown` from `analysis_engine.models` (Task 1).
- Produces: `score_geo(geo_input: GeoInput) -> ScoreBreakdown` in `analysis_engine.scoring.geo` — consumed by Task 6 (composite) and Task 8 (CLI).

- [ ] **Step 1: Write the failing tests**

Create `services/analysis-engine/tests/test_geo_scoring.py`:

```python
from analysis_engine.models import BrandMentionResult, GeoInput
from analysis_engine.scoring.geo import score_geo


def test_score_geo_returns_none_when_no_queries():
    result = score_geo(GeoInput(brand_name="Acme", domain="acme.com"))
    assert result.score is None
    assert result.data_complete is False
    assert result.dimension == "geo"


def test_score_geo_not_mentioned_scores_zero():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(query="best widget", engine="chatgpt", brand_mentioned=False),
        ],
    )
    result = score_geo(geo_input)
    assert result.score == 0.0
    assert result.data_complete is True


def test_score_geo_first_position_mention_scores_100():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(
                query="best widget", engine="chatgpt", brand_mentioned=True, mention_position=1
            ),
        ],
    )
    result = score_geo(geo_input)
    assert result.score == 100.0


def test_score_geo_second_or_third_position_scores_80():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(
                query="best widget", engine="chatgpt", brand_mentioned=True, mention_position=3
            ),
        ],
    )
    result = score_geo(geo_input)
    assert result.score == 80.0


def test_score_geo_mentioned_without_position_scores_60():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(query="best widget", engine="chatgpt", brand_mentioned=True),
        ],
    )
    result = score_geo(geo_input)
    assert result.score == 60.0


def test_score_geo_citation_bonus_caps_at_100():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(
                query="best widget",
                engine="chatgpt",
                brand_mentioned=True,
                mention_position=1,
                cited_as_source=True,
            ),
        ],
    )
    result = score_geo(geo_input)
    assert result.score == 100.0  # 100 * 1.3 capped at 100


def test_score_geo_citation_bonus_applies_to_lower_base_score():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(
                query="best widget",
                engine="chatgpt",
                brand_mentioned=True,
                mention_position=3,
                cited_as_source=True,
            ),
        ],
    )
    result = score_geo(geo_input)
    assert result.score == 100.0  # 80 * 1.3 = 104 -> capped at 100


def test_score_geo_averages_across_multiple_queries():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(
                query="q1", engine="chatgpt", brand_mentioned=True, mention_position=1
            ),
            BrandMentionResult(query="q2", engine="claude", brand_mentioned=False),
        ],
    )
    result = score_geo(geo_input)
    assert result.score == 50.0


def test_score_geo_detail_counts():
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(
                query="q1",
                engine="chatgpt",
                brand_mentioned=True,
                mention_position=1,
                cited_as_source=True,
            ),
            BrandMentionResult(query="q2", engine="claude", brand_mentioned=False),
        ],
    )
    result = score_geo(geo_input)
    assert result.detail["queries_checked"] == 2
    assert result.detail["mentioned_count"] == 1
    assert result.detail["cited_as_source_count"] == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd services/analysis-engine && .venv/bin/pytest tests/test_geo_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'analysis_engine.scoring.geo'`.

- [ ] **Step 3: Implement GEO scoring**

Create `services/analysis-engine/src/analysis_engine/scoring/geo.py`:

```python
"""GEO dimension scoring: brand mention rate/position across LLM answer engines."""

from __future__ import annotations

from analysis_engine.models import BrandMentionResult, GeoInput, ScoreBreakdown

_CITATION_MULTIPLIER = 1.3
_MAX_SCORE = 100.0


def _mention_score(mention: BrandMentionResult) -> float:
    if not mention.brand_mentioned:
        return 0.0

    if mention.mention_position is not None and mention.mention_position <= 1:
        base = 100.0
    elif mention.mention_position is not None and mention.mention_position <= 3:
        base = 80.0
    else:
        base = 60.0

    if mention.cited_as_source:
        base = min(base * _CITATION_MULTIPLIER, _MAX_SCORE)

    return base


def score_geo(geo_input: GeoInput) -> ScoreBreakdown:
    if not geo_input.mention_results:
        return ScoreBreakdown(
            dimension="geo",
            score=None,
            data_complete=False,
            detail={"reason": "no LLM brand mention queries were run"},
        )

    scores = [_mention_score(mention) for mention in geo_input.mention_results]
    final_score = sum(scores) / len(scores)

    return ScoreBreakdown(
        dimension="geo",
        score=round(final_score, 2),
        data_complete=True,
        detail={
            "queries_checked": len(geo_input.mention_results),
            "mentioned_count": sum(1 for m in geo_input.mention_results if m.brand_mentioned),
            "cited_as_source_count": sum(
                1 for m in geo_input.mention_results if m.cited_as_source
            ),
        },
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd services/analysis-engine && .venv/bin/pytest tests/test_geo_scoring.py -v`
Expected: PASS (9 tests pass).

- [ ] **Step 5: Commit**

```bash
cd services/analysis-engine
git add src/analysis_engine/scoring/geo.py tests/test_geo_scoring.py
git commit -m "feat(analysis-engine): add GEO dimension scoring

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: Website AI-friendliness audit wrapper (geo-optimizer-skill integration)

**Files:**
- Modify: `services/analysis-engine/pyproject.toml` (already declares the `geo-optimizer-skill` dependency from Task 1 — no change needed here, just installing it)
- Create: `services/analysis-engine/src/analysis_engine/scoring/website_audit.py`
- Test: `services/analysis-engine/tests/test_website_audit.py`

**Interfaces:**
- Consumes: `ScoreBreakdown` from `analysis_engine.models` (Task 1); `geo_optimizer.audit` (function `audit(url: str) -> AuditResult` where `AuditResult` has `.score: int`, `.band: str`, `.recommendations: list[str]`, `.score_breakdown: dict[str, int]`, `.error: str | None`) from the third-party `geo-optimizer-skill` package.
- Produces: `score_website_audit(url: str) -> ScoreBreakdown` in `analysis_engine.scoring.website_audit` — consumed by Task 6 (composite) and Task 8 (CLI). Module-level name `run_geo_audit` (bound to `geo_optimizer.audit`) is monkeypatched in tests — do not rename it.

- [ ] **Step 1: Write the failing tests**

Create `services/analysis-engine/tests/test_website_audit.py`:

```python
from types import SimpleNamespace

from analysis_engine.scoring import website_audit as website_audit_module
from analysis_engine.scoring.website_audit import score_website_audit


def test_score_website_audit_maps_successful_result(monkeypatch):
    fake_result = SimpleNamespace(
        score=82,
        band="good",
        error=None,
        score_breakdown={"robots": 10, "schema": 20},
        recommendations=["Add llms.txt"],
    )
    monkeypatch.setattr(website_audit_module, "run_geo_audit", lambda url: fake_result)

    result = score_website_audit("https://example.com")

    assert result.dimension == "website_audit"
    assert result.score == 82.0
    assert result.data_complete is True
    assert result.detail["band"] == "good"
    assert result.detail["score_breakdown"] == {"robots": 10, "schema": 20}
    assert result.detail["recommendations"] == ["Add llms.txt"]


def test_score_website_audit_handles_connection_error(monkeypatch):
    fake_result = SimpleNamespace(
        score=0,
        band="critical",
        error="connection timed out",
        score_breakdown={},
        recommendations=[],
    )
    monkeypatch.setattr(website_audit_module, "run_geo_audit", lambda url: fake_result)

    result = score_website_audit("https://unreachable.example")

    assert result.score is None
    assert result.data_complete is False
    assert result.detail["reason"] == "connection timed out"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd services/analysis-engine && .venv/bin/pytest tests/test_website_audit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'analysis_engine.scoring.website_audit'`.

- [ ] **Step 3: Implement the website audit wrapper**

Create `services/analysis-engine/src/analysis_engine/scoring/website_audit.py`:

```python
"""Website AI-friendliness scoring — wraps geo-optimizer-skill's `audit()`."""

from __future__ import annotations

from geo_optimizer import audit as run_geo_audit

from analysis_engine.models import ScoreBreakdown


def score_website_audit(url: str) -> ScoreBreakdown:
    """Run geo-optimizer-skill's audit and map it onto our ScoreBreakdown shape."""
    audit_result = run_geo_audit(url)

    if audit_result.error:
        return ScoreBreakdown(
            dimension="website_audit",
            score=None,
            data_complete=False,
            detail={"reason": audit_result.error},
        )

    return ScoreBreakdown(
        dimension="website_audit",
        score=float(audit_result.score),
        data_complete=True,
        detail={
            "band": audit_result.band,
            "score_breakdown": dict(audit_result.score_breakdown),
            "recommendations": list(audit_result.recommendations),
        },
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd services/analysis-engine && .venv/bin/pip install -e ".[dev]" && .venv/bin/pytest tests/test_website_audit.py -v`
Expected: PASS (2 tests pass). The `pip install -e ".[dev]"` step pulls in `geo-optimizer-skill` from PyPI so the import in `website_audit.py` resolves — the tests themselves never call the real network-hitting `audit()` function since `run_geo_audit` is monkeypatched.

- [ ] **Step 5: Commit**

```bash
cd services/analysis-engine
git add src/analysis_engine/scoring/website_audit.py tests/test_website_audit.py
git commit -m "feat(analysis-engine): wrap geo-optimizer-skill audit for website AI-friendliness score

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 6: Composite score aggregation

**Files:**
- Create: `services/analysis-engine/src/analysis_engine/scoring/composite.py`
- Test: `services/analysis-engine/tests/test_composite.py`

**Interfaces:**
- Consumes: `ScoreBreakdown`, `CompositeReport` from `analysis_engine.models` (Task 1).
- Produces: `compute_composite_score(domain: str, seo: ScoreBreakdown, aeo: ScoreBreakdown, geo: ScoreBreakdown, website_audit: ScoreBreakdown) -> CompositeReport` and the constant `DIMENSION_WEIGHTS: dict[str, float]` in `analysis_engine.scoring.composite` — consumed by Task 7 (recommendations) and Task 8 (CLI). `CompositeReport.dimension_scores` keys are exactly `"seo"`, `"aeo"`, `"geo"`, `"website_audit"`.

- [ ] **Step 1: Write the failing tests**

Create `services/analysis-engine/tests/test_composite.py`:

```python
from analysis_engine.models import ScoreBreakdown
from analysis_engine.scoring.composite import compute_composite_score


def _breakdown(dimension: str, score: float | None) -> ScoreBreakdown:
    return ScoreBreakdown(dimension=dimension, score=score, data_complete=score is not None)


def test_compute_composite_score_all_dimensions_present():
    report = compute_composite_score(
        domain="example.com",
        seo=_breakdown("seo", 80.0),
        aeo=_breakdown("aeo", 60.0),
        geo=_breakdown("geo", 90.0),
        website_audit=_breakdown("website_audit", 70.0),
    )
    # 80*0.30 + 60*0.20 + 90*0.35 + 70*0.15 = 24 + 12 + 31.5 + 10.5 = 78.0
    assert report.overall_score == 78.0
    assert report.domain == "example.com"
    assert set(report.dimension_scores.keys()) == {"seo", "aeo", "geo", "website_audit"}
    assert report.recommendations == []


def test_compute_composite_score_renormalizes_when_dimension_missing():
    report = compute_composite_score(
        domain="example.com",
        seo=_breakdown("seo", 80.0),
        aeo=_breakdown("aeo", None),
        geo=_breakdown("geo", 90.0),
        website_audit=_breakdown("website_audit", 70.0),
    )
    # weights renormalized over seo(0.30)+geo(0.35)+website_audit(0.15)=0.80
    # (80*0.30 + 90*0.35 + 70*0.15) / 0.80 = (24+31.5+10.5)/0.80 = 82.5
    assert report.overall_score == 82.5


def test_compute_composite_score_all_missing_returns_none():
    report = compute_composite_score(
        domain="example.com",
        seo=_breakdown("seo", None),
        aeo=_breakdown("aeo", None),
        geo=_breakdown("geo", None),
        website_audit=_breakdown("website_audit", None),
    )
    assert report.overall_score is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd services/analysis-engine && .venv/bin/pytest tests/test_composite.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'analysis_engine.scoring.composite'`.

- [ ] **Step 3: Implement composite scoring**

Create `services/analysis-engine/src/analysis_engine/scoring/composite.py`:

```python
"""Combines the SEO/AEO/GEO/website-audit dimension scores into one overall score."""

from __future__ import annotations

from analysis_engine.models import CompositeReport, ScoreBreakdown

# Relative importance of each dimension in the overall score. These are a
# starting assumption for the MVP (see docs/superpowers/plans — Design notes)
# and are isolated here so they're trivial to retune later without touching
# any other module.
DIMENSION_WEIGHTS: dict[str, float] = {
    "seo": 0.30,
    "aeo": 0.20,
    "geo": 0.35,
    "website_audit": 0.15,
}


def compute_composite_score(
    domain: str,
    seo: ScoreBreakdown,
    aeo: ScoreBreakdown,
    geo: ScoreBreakdown,
    website_audit: ScoreBreakdown,
) -> CompositeReport:
    dimension_scores = {
        "seo": seo,
        "aeo": aeo,
        "geo": geo,
        "website_audit": website_audit,
    }

    available = [
        (breakdown.score, DIMENSION_WEIGHTS[name])
        for name, breakdown in dimension_scores.items()
        if breakdown.score is not None
    ]

    overall_score: float | None
    if not available:
        overall_score = None
    else:
        total_weight = sum(weight for _, weight in available)
        overall_score = round(
            sum(score * weight for score, weight in available) / total_weight, 2
        )

    return CompositeReport(
        domain=domain,
        overall_score=overall_score,
        dimension_scores=dimension_scores,
        recommendations=[],
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd services/analysis-engine && .venv/bin/pytest tests/test_composite.py -v`
Expected: PASS (3 tests pass).

- [ ] **Step 5: Commit**

```bash
cd services/analysis-engine
git add src/analysis_engine/scoring/composite.py tests/test_composite.py
git commit -m "feat(analysis-engine): add composite score aggregation with weight renormalization

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 7: Recommendations engine

**Files:**
- Create: `services/analysis-engine/src/analysis_engine/recommendations.py`
- Test: `services/analysis-engine/tests/test_recommendations.py`

**Interfaces:**
- Consumes: `CompositeReport`, `ScoreBreakdown`, `Recommendation` from `analysis_engine.models` (Task 1). Expects `CompositeReport.dimension_scores` to have exactly the keys `"seo"`, `"aeo"`, `"geo"`, `"website_audit"` (as produced by Task 6). For the `website_audit` dimension, reads `breakdown.detail.get("recommendations", [])` (a `list[str]`, as produced by Task 5).
- Produces: `generate_recommendations(report: CompositeReport) -> list[Recommendation]` in `analysis_engine.recommendations` — consumed by Task 8 (CLI).

- [ ] **Step 1: Write the failing tests**

Create `services/analysis-engine/tests/test_recommendations.py`:

```python
from analysis_engine.models import CompositeReport, ScoreBreakdown
from analysis_engine.recommendations import generate_recommendations


def _report(seo=90.0, aeo=90.0, geo=90.0, website_audit=90.0, website_audit_detail=None):
    return CompositeReport(
        domain="example.com",
        overall_score=90.0,
        dimension_scores={
            "seo": ScoreBreakdown(dimension="seo", score=seo, data_complete=seo is not None),
            "aeo": ScoreBreakdown(dimension="aeo", score=aeo, data_complete=aeo is not None),
            "geo": ScoreBreakdown(dimension="geo", score=geo, data_complete=geo is not None),
            "website_audit": ScoreBreakdown(
                dimension="website_audit",
                score=website_audit,
                data_complete=website_audit is not None,
                detail=website_audit_detail or {},
            ),
        },
        recommendations=[],
    )


def test_generate_recommendations_flags_missing_data_as_high_priority():
    report = _report(seo=None)
    recs = generate_recommendations(report)
    assert any(r.dimension == "seo" and r.priority == "high" for r in recs)


def test_generate_recommendations_skips_high_scoring_dimensions():
    report = _report(seo=95.0, aeo=90.0, geo=90.0, website_audit=90.0)
    recs = generate_recommendations(report)
    assert recs == []


def test_generate_recommendations_medium_priority_between_40_and_70():
    report = _report(seo=50.0)
    recs = generate_recommendations(report)
    seo_recs = [r for r in recs if r.dimension == "seo"]
    assert len(seo_recs) == 1
    assert seo_recs[0].priority == "medium"


def test_generate_recommendations_high_priority_below_40():
    report = _report(seo=20.0)
    recs = generate_recommendations(report)
    seo_recs = [r for r in recs if r.dimension == "seo"]
    assert len(seo_recs) == 1
    assert seo_recs[0].priority == "high"


def test_generate_recommendations_includes_website_audit_raw_recommendations():
    report = _report(
        website_audit=30.0,
        website_audit_detail={"recommendations": ["Add an llms.txt file"]},
    )
    recs = generate_recommendations(report)
    audit_recs = [r for r in recs if r.title == "Add an llms.txt file"]
    assert len(audit_recs) == 1
    assert audit_recs[0].priority == "high"
    assert audit_recs[0].dimension == "website_audit"


def test_generate_recommendations_sorted_by_priority_then_dimension():
    report = _report(seo=50.0, aeo=20.0, geo=90.0, website_audit=90.0)
    recs = generate_recommendations(report)
    assert [r.dimension for r in recs] == ["aeo", "seo"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd services/analysis-engine && .venv/bin/pytest tests/test_recommendations.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'analysis_engine.recommendations'`.

- [ ] **Step 3: Implement the recommendations engine**

Create `services/analysis-engine/src/analysis_engine/recommendations.py`:

```python
"""Turns a CompositeReport's dimension scores into a prioritized action list."""

from __future__ import annotations

from analysis_engine.models import CompositeReport, Recommendation, ScoreBreakdown

_PRIORITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}

_DIMENSION_LABELS: dict[str, str] = {
    "seo": "SEO",
    "aeo": "AEO",
    "geo": "GEO",
    "website_audit": "Website AI-friendliness",
}

_HIGH_PRIORITY_THRESHOLD = 40.0
_MEDIUM_PRIORITY_THRESHOLD = 70.0
_RECOMMENDATION_THRESHOLD = 80.0


def _priority_for_score(score: float) -> str:
    if score < _HIGH_PRIORITY_THRESHOLD:
        return "high"
    if score < _MEDIUM_PRIORITY_THRESHOLD:
        return "medium"
    return "low"


def _dimension_recommendation(name: str, breakdown: ScoreBreakdown) -> Recommendation | None:
    label = _DIMENSION_LABELS[name]

    if breakdown.score is None:
        return Recommendation(
            priority="high",
            dimension=name,
            title=f"{label} data missing",
            description=(
                f"No {label} data was collected for this domain. Connect the "
                "relevant data source before this score can be computed."
            ),
        )

    if breakdown.score >= _RECOMMENDATION_THRESHOLD:
        return None

    return Recommendation(
        priority=_priority_for_score(breakdown.score),
        dimension=name,
        title=f"Improve {label} score ({breakdown.score:.0f}/100)",
        description=(
            f"{label} score is below target; review the {label} data breakdown "
            "for specific gaps."
        ),
    )


def generate_recommendations(report: CompositeReport) -> list[Recommendation]:
    recommendations: list[Recommendation] = []

    for name, breakdown in report.dimension_scores.items():
        rec = _dimension_recommendation(name, breakdown)
        if rec is not None:
            recommendations.append(rec)

    website_audit = report.dimension_scores.get("website_audit")
    if website_audit is not None and website_audit.score is not None:
        audit_priority = _priority_for_score(website_audit.score)
        for raw_recommendation in website_audit.detail.get("recommendations", []):
            recommendations.append(
                Recommendation(
                    priority=audit_priority,
                    dimension="website_audit",
                    title=raw_recommendation,
                    description=raw_recommendation,
                )
            )

    recommendations.sort(key=lambda r: (_PRIORITY_ORDER[r.priority], r.dimension))
    return recommendations
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd services/analysis-engine && .venv/bin/pytest tests/test_recommendations.py -v`
Expected: PASS (6 tests pass).

- [ ] **Step 5: Commit**

```bash
cd services/analysis-engine
git add src/analysis_engine/recommendations.py tests/test_recommendations.py
git commit -m "feat(analysis-engine): add prioritized recommendations engine

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 8: CLI

**Files:**
- Create: `services/analysis-engine/src/analysis_engine/cli.py`
- Test: `services/analysis-engine/tests/test_cli.py`

**Interfaces:**
- Consumes: `score_seo` (Task 2), `score_aeo` (Task 3), `score_geo` (Task 4), `score_website_audit` (Task 5, imported into `cli.py`'s module namespace as `score_website_audit` so it can be monkeypatched as `analysis_engine.cli.score_website_audit`), `compute_composite_score` (Task 6), `generate_recommendations` (Task 7), and the models from Task 1.
- Produces: `click.Command` named `analyze` in `analysis_engine.cli`, registered as the `analysis-engine` console script (Task 1's `pyproject.toml`). Prints a JSON object to stdout with keys `domain`, `overall_score`, `dimensions` (map of dimension name -> `{score, data_complete, detail}`), `recommendations` (list of `{priority, dimension, title, description}`).

- [ ] **Step 1: Write the failing tests**

Create `services/analysis-engine/tests/test_cli.py`:

```python
import json

from click.testing import CliRunner

from analysis_engine import cli as cli_module
from analysis_engine.cli import analyze
from analysis_engine.models import ScoreBreakdown


def _patch_website_audit(monkeypatch, score=75.0):
    monkeypatch.setattr(
        cli_module,
        "score_website_audit",
        lambda url: ScoreBreakdown(
            dimension="website_audit", score=score, data_complete=True, detail={}
        ),
    )


def test_analyze_cli_runs_end_to_end_with_no_data_files(monkeypatch):
    _patch_website_audit(monkeypatch)

    runner = CliRunner()
    result = runner.invoke(
        analyze,
        ["--domain", "example.com", "--url", "https://example.com", "--brand-name", "Acme"],
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["domain"] == "example.com"
    assert output["dimensions"]["website_audit"]["score"] == 75.0
    assert output["dimensions"]["seo"]["score"] is None
    # seo/aeo/geo all missing data -> high priority recommendations expected
    assert any(
        r["dimension"] == "seo" and r["priority"] == "high" for r in output["recommendations"]
    )


def test_analyze_cli_reads_seo_data_file(monkeypatch, tmp_path):
    _patch_website_audit(monkeypatch)
    seo_file = tmp_path / "seo.json"
    seo_file.write_text(
        json.dumps(
            {
                "keyword_rankings": [
                    {"keyword": "widgets", "engine": "google", "position": 1, "search_volume": 500}
                ]
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        analyze,
        [
            "--domain", "example.com",
            "--url", "https://example.com",
            "--brand-name", "Acme",
            "--seo-data", str(seo_file),
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["dimensions"]["seo"]["score"] == 100.0


def test_analyze_cli_reads_aeo_and_geo_data_files(monkeypatch, tmp_path):
    _patch_website_audit(monkeypatch)
    aeo_file = tmp_path / "aeo.json"
    aeo_file.write_text(
        json.dumps(
            {
                "total_keywords_checked": 1,
                "snippet_hits": [
                    {"keyword": "widgets", "engine": "google", "snippet_type": "featured_snippet"}
                ],
            }
        )
    )
    geo_file = tmp_path / "geo.json"
    geo_file.write_text(
        json.dumps(
            {
                "mention_results": [
                    {
                        "query": "best widget maker",
                        "engine": "chatgpt",
                        "brand_mentioned": True,
                        "mention_position": 1,
                    }
                ]
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        analyze,
        [
            "--domain", "example.com",
            "--url", "https://example.com",
            "--brand-name", "Acme",
            "--aeo-data", str(aeo_file),
            "--geo-data", str(geo_file),
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["dimensions"]["aeo"]["score"] == 100.0
    assert output["dimensions"]["geo"]["score"] == 100.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd services/analysis-engine && .venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'analysis_engine.cli'`.

- [ ] **Step 3: Implement the CLI**

Create `services/analysis-engine/src/analysis_engine/cli.py`:

```python
"""CLI entry point: run the full SEO/AEO/GEO analysis pipeline and print a JSON report."""

from __future__ import annotations

import json
from pathlib import Path

import click

from analysis_engine.models import (
    AeoInput,
    BrandMentionResult,
    CompositeReport,
    FeaturedSnippetHit,
    GeoInput,
    KeywordRanking,
    SeoInput,
)
from analysis_engine.recommendations import generate_recommendations
from analysis_engine.scoring.aeo import score_aeo
from analysis_engine.scoring.composite import compute_composite_score
from analysis_engine.scoring.geo import score_geo
from analysis_engine.scoring.seo import score_seo
from analysis_engine.scoring.website_audit import score_website_audit


def _load_seo_input(path: Path | None, domain: str) -> SeoInput:
    if path is None:
        return SeoInput(domain=domain)
    data = json.loads(path.read_text())
    return SeoInput(
        domain=domain,
        keyword_rankings=[KeywordRanking(**kr) for kr in data.get("keyword_rankings", [])],
        indexed_pages_count=data.get("indexed_pages_count"),
        total_pages_count=data.get("total_pages_count"),
    )


def _load_aeo_input(path: Path | None, domain: str) -> AeoInput:
    if path is None:
        return AeoInput(domain=domain, total_keywords_checked=0)
    data = json.loads(path.read_text())
    return AeoInput(
        domain=domain,
        snippet_hits=[FeaturedSnippetHit(**hit) for hit in data.get("snippet_hits", [])],
        total_keywords_checked=data.get("total_keywords_checked", 0),
    )


def _load_geo_input(path: Path | None, brand_name: str, domain: str) -> GeoInput:
    if path is None:
        return GeoInput(brand_name=brand_name, domain=domain)
    data = json.loads(path.read_text())
    return GeoInput(
        brand_name=brand_name,
        domain=domain,
        mention_results=[BrandMentionResult(**m) for m in data.get("mention_results", [])],
    )


def _report_to_dict(report: CompositeReport) -> dict:
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
                "priority": rec.priority,
                "dimension": rec.dimension,
                "title": rec.title,
                "description": rec.description,
            }
            for rec in report.recommendations
        ],
    }


@click.command()
@click.option("--domain", required=True, help="Customer domain, e.g. example.com")
@click.option("--url", required=True, help="Full URL to run the website audit against")
@click.option("--brand-name", required=True, help="Brand name to check for in LLM answers")
@click.option(
    "--seo-data",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="JSON file with SEO keyword ranking data",
)
@click.option(
    "--aeo-data",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="JSON file with AEO featured snippet/PAA data",
)
@click.option(
    "--geo-data",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="JSON file with GEO brand mention data",
)
def analyze(
    domain: str,
    url: str,
    brand_name: str,
    seo_data: Path | None,
    aeo_data: Path | None,
    geo_data: Path | None,
) -> None:
    """Run the full SEO/AEO/GEO analysis pipeline and print a JSON report."""
    seo_input = _load_seo_input(seo_data, domain)
    aeo_input = _load_aeo_input(aeo_data, domain)
    geo_input = _load_geo_input(geo_data, brand_name, domain)

    seo_score = score_seo(seo_input)
    aeo_score = score_aeo(aeo_input)
    geo_score = score_geo(geo_input)
    website_audit_score = score_website_audit(url)

    report = compute_composite_score(domain, seo_score, aeo_score, geo_score, website_audit_score)
    report.recommendations = generate_recommendations(report)

    click.echo(json.dumps(_report_to_dict(report), indent=2))


if __name__ == "__main__":
    analyze()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd services/analysis-engine && .venv/bin/pytest tests/test_cli.py -v`
Expected: PASS (3 tests pass).

- [ ] **Step 5: Commit**

```bash
cd services/analysis-engine
git add src/analysis_engine/cli.py tests/test_cli.py
git commit -m "feat(analysis-engine): add analyze CLI wiring the full scoring pipeline

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 9: End-to-end integration test and full test suite run

**Files:**
- Test: `services/analysis-engine/tests/test_integration.py`

**Interfaces:**
- Consumes: everything from Tasks 1-8. No new production code — this task only adds a test that exercises the full pipeline through the public Python API (as opposed to Task 8's CLI-level test) and verifies the whole suite is green.

- [ ] **Step 1: Write the integration test**

Create `services/analysis-engine/tests/test_integration.py`:

```python
"""End-to-end test: feed realistic fixture data through every scoring module
and the composite/recommendations pipeline via the public Python API."""

from unittest.mock import patch

from analysis_engine.models import (
    AeoInput,
    BrandMentionResult,
    FeaturedSnippetHit,
    GeoInput,
    KeywordRanking,
    SeoInput,
)
from analysis_engine.recommendations import generate_recommendations
from analysis_engine.scoring.aeo import score_aeo
from analysis_engine.scoring.composite import compute_composite_score
from analysis_engine.scoring.geo import score_geo
from analysis_engine.scoring.seo import score_seo
from analysis_engine.scoring.website_audit import score_website_audit


def test_full_pipeline_produces_a_complete_report():
    seo_input = SeoInput(
        domain="acme.com",
        keyword_rankings=[
            KeywordRanking(keyword="widgets", engine="google", position=2, search_volume=800),
            KeywordRanking(keyword="gadgets", engine="baidu", position=15, search_volume=200),
        ],
        indexed_pages_count=45,
        total_pages_count=50,
    )
    aeo_input = AeoInput(
        domain="acme.com",
        total_keywords_checked=4,
        snippet_hits=[
            FeaturedSnippetHit(keyword="widgets", engine="google", snippet_type="featured_snippet"),
            FeaturedSnippetHit(keyword="gadgets", engine="google", snippet_type="paa"),
        ],
    )
    geo_input = GeoInput(
        brand_name="Acme",
        domain="acme.com",
        mention_results=[
            BrandMentionResult(
                query="best widget maker",
                engine="chatgpt",
                brand_mentioned=True,
                mention_position=1,
                cited_as_source=True,
            ),
            BrandMentionResult(query="top gadget brands", engine="claude", brand_mentioned=False),
        ],
    )

    with patch("analysis_engine.scoring.website_audit.run_geo_audit") as mock_audit:
        mock_audit.return_value.score = 68
        mock_audit.return_value.band = "fair"
        mock_audit.return_value.error = None
        mock_audit.return_value.score_breakdown = {"robots": 5, "llms_txt": 0}
        mock_audit.return_value.recommendations = ["Add an llms.txt file"]

        seo_score = score_seo(seo_input)
        aeo_score = score_aeo(aeo_input)
        geo_score = score_geo(geo_input)
        website_audit_score = score_website_audit("https://acme.com")

    report = compute_composite_score(
        "acme.com", seo_score, aeo_score, geo_score, website_audit_score
    )
    report.recommendations = generate_recommendations(report)

    assert report.domain == "acme.com"
    assert report.overall_score is not None
    assert 0.0 <= report.overall_score <= 100.0
    assert set(report.dimension_scores.keys()) == {"seo", "aeo", "geo", "website_audit"}
    for breakdown in report.dimension_scores.values():
        assert breakdown.data_complete is True
        assert breakdown.score is not None

    # website_audit scored 68 (< 80) so its raw recommendation should surface.
    assert any(r.title == "Add an llms.txt file" for r in report.recommendations)
```

- [ ] **Step 2: Run the full test suite**

Run: `cd services/analysis-engine && .venv/bin/pytest -v`
Expected: PASS — all tests across `test_models.py`, `test_seo_scoring.py`, `test_aeo_scoring.py`, `test_geo_scoring.py`, `test_website_audit.py`, `test_composite.py`, `test_recommendations.py`, `test_cli.py`, and `test_integration.py` pass (44 tests total).

- [ ] **Step 3: Manual smoke test of the CLI (optional, not part of automated suite)**

Run: `cd services/analysis-engine && .venv/bin/analysis-engine --domain example.com --url https://example.com --brand-name Acme`
Expected: prints a JSON report to stdout; this call *does* hit the real `geo-optimizer-skill` audit over the network against `https://example.com`, so only run it when network access is available and you want to sanity-check the real integration (not required for the automated test suite to pass).

- [ ] **Step 4: Commit**

```bash
cd services/analysis-engine
git add tests/test_integration.py
git commit -m "test(analysis-engine): add end-to-end integration test for the scoring pipeline

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

## Notes for Phase 2 handoff

- `SeoInput`, `AeoInput`, `GeoInput` (in `analysis_engine.models`) are the contracts Phase 2's data-collection layer must populate from DataForSEO (SEO/AEO) and LLM query APIs (GEO / OpenRouter, 硅基流动, 百度千帆, etc.).
- `score_website_audit(url)` already calls the real `geo-optimizer-skill` library — Phase 2 does not need to touch website-audit data collection, only wire up SEO/AEO/GEO data.
- Composite weights (`DIMENSION_WEIGHTS` in `composite.py`) and recommendation thresholds (`recommendations.py`) are simple module-level constants — safe to retune later without other code changes.
- No FastAPI/DB/queue code exists yet; Phase 3 will build a thin service around this package (`services/analysis-engine` becomes an installable dependency of `services/api`).
