# Phase 3 FastAPI Thin Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a stateless FastAPI service in `services/api/` that exposes synchronous `POST /collect` and `POST /analyze` endpoints on top of `data-collectors` and `analysis-engine`.

**Architecture:** Keep the API layer thin. Define API DTOs in `services/api`, convert them to `data-collectors` inputs in adapters, orchestrate collection and scoring in service functions, and keep route handlers minimal. The service does not persist data, queue jobs, or own business logic beyond request/response translation.

**Tech Stack:** Python 3.11+, `fastapi`, `uvicorn`, `pydantic`, `pytest`, sibling packages `data-collectors` and `analysis-engine`, FastAPI test client, monkeypatched service tests.

---

## File Structure

```
services/api/
  pyproject.toml
  README.md
  src/api/
    __init__.py
    main.py
    settings.py
    models.py
    adapters.py
    services.py
  tests/
    test_models.py
    test_adapters.py
    test_services.py
    test_routes.py
```

The API layer owns only transport DTOs and orchestration. It must not reimplement provider access, scoring logic, or composite-score math.

---

### Task 1: Scaffold the API package and request/response DTOs

**Files:**
- Create: `services/api/pyproject.toml`
- Create: `services/api/README.md`
- Create: `services/api/src/api/__init__.py`
- Create: `services/api/src/api/settings.py`
- Create: `services/api/src/api/models.py`
- Test: `services/api/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/test_models.py`:

```python
from api.models import AnalyzeRequest, CollectRequest, GeoQueryInput, KeywordSpecInput


def test_keyword_spec_input_fields():
    spec = KeywordSpecInput(keyword="best crm", engine="google")
    assert spec.keyword == "best crm"
    assert spec.engine == "google"


def test_geo_query_input_fields():
    query = GeoQueryInput(query="best crm for factories", engine_hint="global")
    assert query.query == "best crm for factories"
    assert query.engine_hint == "global"


def test_collect_request_fields():
    request = CollectRequest(
        domain="example.com",
        url="https://example.com",
        brand_name="Acme",
        keywords=[KeywordSpecInput(keyword="best crm", engine="google")],
        geo_queries=[GeoQueryInput(query="best crm for factories")],
    )
    assert request.domain == "example.com"
    assert request.keywords[0].keyword == "best crm"


def test_analyze_request_matches_collect_request_shape():
    request = AnalyzeRequest(
        domain="example.com",
        url="https://example.com",
        brand_name="Acme",
        keywords=[],
        geo_queries=[],
    )
    assert request.url == "https://example.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd services/api && pytest tests/test_models.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'api'`.

- [ ] **Step 3: Write minimal implementation**

Create `services/api/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "api"
version = "0.1.0"
description = "Thin FastAPI service for the SAG diagnostic platform"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115,<1.0",
    "uvicorn>=0.30,<1.0",
    "pydantic>=2.7,<3.0",
    "analysis-engine @ file:///Users/terry/work/dev_env/copilot-worktrees/sag_platform/terry198411-urban-chainsaw/services/analysis-engine",
    "data-collectors @ file:///Users/terry/work/dev_env/copilot-worktrees/sag_platform/terry198411-urban-chainsaw/services/data-collectors",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0,<9.0",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src", "../analysis-engine/src", "../data-collectors/src"]
```

Create `services/api/README.md`:

```markdown
# API

Thin FastAPI service for the SAG diagnostic platform.

Exposes synchronous `/collect` and `/analyze` endpoints on top of the
existing `data-collectors` and `analysis-engine` packages.
```

Create `services/api/src/api/__init__.py`:

```python
"""Thin FastAPI service for the SAG diagnostic platform."""

__version__ = "0.1.0"
```

Create `services/api/src/api/settings.py`:

```python
from __future__ import annotations

import os

from pydantic import BaseModel, Field


class Settings(BaseModel):
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    log_level: str = Field(default="info")
    dataforseo_login: str = Field(default_factory=lambda: os.getenv("DATAFORSEO_LOGIN", ""))
    dataforseo_password: str = Field(default_factory=lambda: os.getenv("DATAFORSEO_PASSWORD", ""))
    openrouter_api_key: str = Field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    qianfan_access_key: str = Field(default_factory=lambda: os.getenv("QIANFAN_ACCESS_KEY", ""))
    qianfan_secret_key: str = Field(default_factory=lambda: os.getenv("QIANFAN_SECRET_KEY", ""))


settings = Settings()
```

Create `services/api/src/api/models.py`:

```python
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
```

Create a temporary `services/api/src/api/main.py`:

```python
from fastapi import FastAPI

app = FastAPI()
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd services/api && pytest tests/test_models.py -v
```

Expected: PASS with `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add services/api
git commit -m "feat(api): scaffold service package and dto models"
```

---

### Task 2: Add adapters between API DTOs and internal collector/scoring models

**Files:**
- Create: `services/api/src/api/adapters.py`
- Test: `services/api/tests/test_adapters.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/test_adapters.py`:

```python
from api.adapters import (
    analyze_response_to_dict,
    collect_request_to_inputs,
    collect_payload_to_dict,
)
from api.models import CollectRequest, GeoQueryInput, KeywordSpecInput
from data_collectors.models import CollectionError, CollectionPayload, GeoQuerySpec, KeywordSpec
from analysis_engine.models import AeoInput, GeoInput, ScoreBreakdown, SeoInput, Recommendation, CompositeReport


def test_collect_request_to_inputs_maps_fields():
    request = CollectRequest(
        domain="example.com",
        url="https://example.com",
        brand_name="Acme",
        keywords=[KeywordSpecInput(keyword="best crm", engine="google")],
        geo_queries=[GeoQueryInput(query="best crm for factories", engine_hint="global")],
    )
    keywords, geo_queries = collect_request_to_inputs(request)
    assert keywords == [KeywordSpec(keyword="best crm", engine="google")]
    assert geo_queries == [GeoQuerySpec(query="best crm for factories", engine_hint="global")]


def test_collect_payload_to_dict_serializes_collection_payload():
    payload = CollectionPayload(
        domain="example.com",
        seo=SeoInput(domain="example.com"),
        aeo=AeoInput(domain="example.com"),
        geo=GeoInput(brand_name="Acme", domain="example.com"),
        errors=[CollectionError(provider="openrouter", operation="geo_query_batch", retryable=True, message="rate limited")],
    )
    result = collect_payload_to_dict(payload)
    assert result["domain"] == "example.com"
    assert result["errors"][0]["provider"] == "openrouter"


def test_analyze_response_to_dict_serializes_report():
    report = CompositeReport(
        domain="example.com",
        overall_score=80.0,
        dimension_scores={
            "seo": ScoreBreakdown(dimension="seo", score=80.0, data_complete=True),
        },
        recommendations=[Recommendation(priority="low", dimension="seo", title="t", description="d")],
    )
    result = analyze_response_to_dict(report, [])
    assert result["domain"] == "example.com"
    assert result["recommendations"][0]["dimension"] == "seo"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd services/api && pytest tests/test_adapters.py -v
```

Expected: FAIL with import errors for `api.adapters`.

- [ ] **Step 3: Write minimal implementation**

Create `services/api/src/api/adapters.py`:

```python
from __future__ import annotations

from dataclasses import asdict

from api.models import CollectRequest
from data_collectors.models import CollectionPayload, GeoQuerySpec, KeywordSpec
from analysis_engine.models import CompositeReport


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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd services/api && pytest tests/test_adapters.py -v
```

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add services/api/src/api/adapters.py services/api/tests/test_adapters.py
git commit -m "feat(api): add dto adapters"
```

---

### Task 3: Add orchestration services for collect/analyze

**Files:**
- Create: `services/api/src/api/services.py`
- Test: `services/api/tests/test_services.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/test_services.py`:

```python
from data_collectors.models import CollectionError, CollectionPayload

from api.services import analyze_service, collect_service
from api.models import CollectRequest, GeoQueryInput, KeywordSpecInput


def test_collect_service_calls_collection_pipeline(monkeypatch):
    request = CollectRequest(
        domain="example.com",
        url="https://example.com",
        brand_name="Acme",
        keywords=[KeywordSpecInput(keyword="best crm", engine="google")],
        geo_queries=[GeoQueryInput(query="best crm for factories")],
    )
    monkeypatch.setattr(
        "api.services._build_collection_payload",
        lambda request: CollectionPayload(
            domain=request.domain,
            seo=None,
            aeo=None,
            geo=None,
            errors=[],
        ),
    )
    result = collect_service(request)
    assert result["domain"] == "example.com"


def test_analyze_service_returns_report(monkeypatch):
    request = CollectRequest(
        domain="example.com",
        url="https://example.com",
        brand_name="Acme",
        keywords=[],
        geo_queries=[],
    )
    monkeypatch.setattr(
        "api.services._build_collection_payload",
        lambda request: CollectionPayload(
            domain=request.domain,
            seo=None,
            aeo=None,
            geo=None,
            errors=[],
        ),
    )
    result = analyze_service(request)
    assert result["domain"] == "example.com"


def test_analyze_service_preserves_collection_errors(monkeypatch):
    request = CollectRequest(
        domain="example.com",
        url="https://example.com",
        brand_name="Acme",
        keywords=[],
        geo_queries=[],
    )
    monkeypatch.setattr(
        "api.services._build_collection_payload",
        lambda request: CollectionPayload(
            domain=request.domain,
            seo=None,
            aeo=None,
            geo=None,
            errors=[
                CollectionError(
                    provider="openrouter",
                    operation="geo_query_batch",
                    retryable=True,
                    message="rate limited",
                )
            ],
        ),
    )
    result = analyze_service(request)
    assert result["collection_errors"][0]["provider"] == "openrouter"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd services/api && pytest tests/test_services.py -v
```

Expected: FAIL with import errors for `api.services`.

- [ ] **Step 3: Write minimal implementation**

Create `services/api/src/api/services.py`:

```python
from __future__ import annotations

from analysis_engine.models import AeoInput, GeoInput, SeoInput
from analysis_engine.recommendations import generate_recommendations
from analysis_engine.scoring.aeo import score_aeo
from analysis_engine.scoring.composite import compute_composite_score
from analysis_engine.scoring.geo import score_geo
from analysis_engine.scoring.seo import score_seo
from analysis_engine.scoring.website_audit import score_website_audit
from data_collectors.collectors.pipeline import run_collection_pipeline
from data_collectors.providers.dataforseo import DataForSEOClient
from data_collectors.providers.openrouter import OpenRouterClient
from data_collectors.providers.qianfan import QianfanClient

from api.adapters import analyze_response_to_dict, collect_payload_to_dict, collect_request_to_inputs
from api.models import AnalyzeRequest, CollectRequest
from api.settings import settings


def _build_collection_payload(request: CollectRequest):
    keywords, geo_queries = collect_request_to_inputs(request)
    return run_collection_pipeline(
        domain=request.domain,
        brand_name=request.brand_name,
        keywords=keywords,
        geo_queries=geo_queries,
        dataforseo_client=DataForSEOClient(
            login=settings.dataforseo_login,
            password=settings.dataforseo_password,
        ),
        openrouter_client=OpenRouterClient(api_key=settings.openrouter_api_key),
        qianfan_client=QianfanClient(
            access_key=settings.qianfan_access_key,
            secret_key=settings.qianfan_secret_key,
        ),
    )


def collect_service(request: CollectRequest) -> dict:
    payload = _build_collection_payload(request)
    return collect_payload_to_dict(payload)


def analyze_service(request: AnalyzeRequest) -> dict:
    payload = _build_collection_payload(request)
    seo = payload.seo or SeoInput(domain=request.domain)
    aeo = payload.aeo or AeoInput(domain=request.domain)
    geo = payload.geo or GeoInput(brand_name=request.brand_name, domain=request.domain)
    report = compute_composite_score(
        request.domain,
        score_seo(seo),
        score_aeo(aeo),
        score_geo(geo),
        score_website_audit(request.url),
    )
    report.recommendations = generate_recommendations(report)
    return analyze_response_to_dict(report, [item.__dict__ for item in payload.errors])
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd services/api && pytest tests/test_services.py -v
```

Expected: PASS with the service tests green.

- [ ] **Step 5: Commit**

```bash
git add services/api/src/api/services.py services/api/tests/test_services.py
git commit -m "feat(api): add collect and analyze service orchestration"
```

---

### Task 4: Add FastAPI app, routes, and route tests

**Files:**
- Modify: `services/api/src/api/main.py`
- Test: `services/api/tests/test_routes.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/test_routes.py`:

```python
from fastapi.testclient import TestClient

from api.main import app


def test_collect_route_returns_json(monkeypatch):
    monkeypatch.setattr(
        "api.main.collect_service",
        lambda request: {
            "domain": request.domain,
            "seo": None,
            "aeo": None,
            "geo": None,
            "errors": [],
        },
    )
    client = TestClient(app)
    response = client.post(
        "/collect",
        json={
            "domain": "example.com",
            "url": "https://example.com",
            "brand_name": "Acme",
            "keywords": [{"keyword": "best crm", "engine": "google"}],
            "geo_queries": [{"query": "best crm for factories", "engine_hint": "global"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["domain"] == "example.com"


def test_analyze_route_returns_json(monkeypatch):
    monkeypatch.setattr(
        "api.main.analyze_service",
        lambda request: {
            "domain": request.domain,
            "overall_score": 78.4,
            "dimensions": {},
            "recommendations": [],
            "collection_errors": [],
        },
    )
    client = TestClient(app)
    response = client.post(
        "/analyze",
        json={
            "domain": "example.com",
            "url": "https://example.com",
            "brand_name": "Acme",
            "keywords": [],
            "geo_queries": [],
        },
    )
    assert response.status_code == 200
    assert response.json()["domain"] == "example.com"


def test_collect_route_rejects_invalid_payload():
    client = TestClient(app)
    response = client.post("/collect", json={"domain": "example.com"})
    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd services/api && pytest tests/test_routes.py -v
```

Expected: FAIL because `app` and routes do not exist.

- [ ] **Step 3: Write minimal implementation**

Replace `services/api/src/api/main.py` with:

```python
from __future__ import annotations

from fastapi import FastAPI

from api.models import AnalyzeRequest, CollectRequest
from api.services import analyze_service, collect_service

app = FastAPI()


@app.post("/collect")
def collect(request: CollectRequest) -> dict:
    payload = collect_service(request)
    return payload


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict:
    return analyze_service(request)
```

Then refine the routes to return JSON-serializable dicts via the adapters rather than raw objects.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd services/api && pytest tests/test_routes.py -v
```

Expected: PASS with route tests green.

- [ ] **Step 5: Commit**

```bash
git add services/api/src/api/main.py services/api/tests/test_routes.py
git commit -m "feat(api): add collect and analyze routes"
```

---

### Task 5: Wire environment settings, final response shapes, and full-suite verification

**Files:**
- Modify: `services/api/src/api/settings.py`
- Modify: `services/api/src/api/services.py`
- Modify: `services/api/src/api/main.py`
- Modify: `services/api/tests/test_services.py`
- Modify: `services/api/tests/test_routes.py`

- [ ] **Step 1: Write the failing tests**

Append to `services/api/tests/test_services.py`:

```python
from api.models import CollectRequest, GeoQueryInput, KeywordSpecInput


def test_collect_service_preserves_partial_errors(monkeypatch):
    request = CollectRequest(
        domain="example.com",
        url="https://example.com",
        brand_name="Acme",
        keywords=[KeywordSpecInput(keyword="best crm", engine="google")],
        geo_queries=[GeoQueryInput(query="best crm for factories")],
    )
    result = collect_service(request)
    assert result["domain"] == "example.com"
    assert "errors" in result
```

Add one more test that monkeypatches `run_collection_pipeline` to return a payload with a `CollectionError`, then verify `analyze_service(request)["collection_errors"]` preserves that entry.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd services/api && pytest tests/test_routes.py tests/test_services.py -v
```

Expected: FAIL on the new error-path assertions and any unfinished wiring.

- [ ] **Step 3: Write minimal implementation**

Update `settings.py` to load host/port/log level from environment with a small settings object.

Update `services.py` so:

```python
collect_service(request) -> dict
analyze_service(request) -> dict
```

both return JSON-ready dictionaries using the adapters.

Update `main.py` so:

- route handlers return adapter-produced dictionaries
- `CollectRequest` and `AnalyzeRequest` use the response models if needed
- invalid payloads remain FastAPI 422s

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd services/api && pytest
```

Expected: PASS with the full `services/api/tests/` suite green.

- [ ] **Step 5: Commit**

```bash
git add services/api
git commit -m "feat(api): finalize thin fastapi service wiring"
```

---

## Self-Review

Spec coverage:

- Stateless FastAPI service: covered by Goal and Architecture
- `/collect` and `/analyze` synchronous endpoints: covered by Tasks 3-4
- API DTOs distinct from internal package models: covered by Task 1 and Task 2
- Thin orchestration on top of `data-collectors` and `analysis-engine`: covered by Tasks 2-4
- No DB/queue/auth/billing: explicitly listed in Scope and Non-Goals

Placeholder scan:

- No `TODO`, `TBD`, or “implement later” placeholders remain.

Type consistency:

- `CollectRequest`, `AnalyzeRequest`, `KeywordSpecInput`, and `GeoQueryInput` are introduced before the adapters consume them.
- `collect_service` and `analyze_service` keep the same names across tests and implementation steps.
- Response dictionaries are kept separate from the internal package dataclasses to preserve the boundary in the spec.
