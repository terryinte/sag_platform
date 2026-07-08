# Phase 3 FastAPI Thin Service Design

## 1. Goal

Build a stateless FastAPI service that exposes two synchronous HTTP endpoints, `/collect` and `/analyze`, on top of the existing `data-collectors` and `analysis-engine` packages.

This phase must stay thin. It must not add persistence, async job processing, authentication, tenant isolation, billing, or any other SaaS concerns.

## 2. Confirmed Scope

- Delivery shape: standalone FastAPI service
- Service location: `services/api/`
- External endpoints:
  - `POST /collect`
  - `POST /analyze`
- Internal dependencies:
  - `data-collectors` for provider access, normalization, and collection orchestration
  - `analysis-engine` for SEO/AEO/GEO scoring, composite aggregation, and recommendations
- Runtime behavior:
  - synchronous request/response only
  - no database writes
  - no queue or background worker
  - no auth layer

## 3. Architecture

The service is a thin adapter around the two existing Python packages.

Reasoning:

- `data-collectors` already knows how to talk to upstream providers and return normalized `SeoInput`, `AeoInput`, and `GeoInput`.
- `analysis-engine` already computes scores and recommendations.
- The API layer should translate external request DTOs into the internal inputs those packages already expect, then return stable JSON responses.

The package structure should be:

```text
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

## 4. Component Boundaries

### 4.1 `models.py`

Defines API DTOs only.

Proposed request/response models:

- `CollectRequest`
  - `domain`
  - `url`
  - `brand_name`
  - `keywords`: list of `KeywordSpecInput`
  - `geo_queries`: list of `GeoQueryInput`
- `AnalyzeRequest`
  - same fields as `CollectRequest`
- `KeywordSpecInput`
  - `keyword`
  - `engine`
- `GeoQueryInput`
  - `query`
  - `engine_hint`
- `CollectResponse`
  - `domain`
  - `seo`
  - `aeo`
  - `geo`
  - `errors`
- `AnalyzeResponse`
  - `domain`
  - `overall_score`
  - `dimensions`
  - `recommendations`
  - `collection_errors`

The API DTOs must not be the same dataclasses as the `data-collectors` internal transport models. The API layer may convert between them.

### 4.2 `adapters.py`

Contains conversion helpers between API DTOs and internal package objects.

- API request DTOs to `data_collectors.models.KeywordSpec` and `GeoQuerySpec`
- `data_collectors.models.CollectionPayload` to response JSON shape
- `analysis_engine.models.*` to response JSON shape where needed

### 4.3 `services.py`

Contains orchestration logic for the endpoints.

- `collect_service(request)`:
  - converts API DTOs to collector inputs
  - runs the `data-collectors` pipeline
  - returns `CollectResponse`
- `analyze_service(request)`:
  - runs collection first
  - passes normalized inputs into `analysis-engine`
  - returns `AnalyzeResponse`

### 4.4 `main.py`

Defines the FastAPI app and routes.

The route layer should stay minimal:

- parse request body
- call service function
- return response model

## 5. Data Flow

The end-to-end flow is:

1. Client sends a `POST /collect` or `POST /analyze` request with domain, URL, brand name, keyword list, and GEO queries.
2. FastAPI validates the API DTOs.
3. `services.py` adapts the DTOs into `data-collectors` inputs.
4. `data-collectors` calls upstream providers and returns normalized SEO/AEO/GEO data plus collection errors.
5. For `/analyze`, the normalized data is passed into `analysis-engine` scoring functions and `score_website_audit(url)`.
6. The route returns a synchronous JSON response.

## 6. Endpoint Contracts

### 6.1 `POST /collect`

Purpose: collect and normalize SEO/AEO/GEO inputs only.

Request example:

```json
{
  "domain": "example.com",
  "url": "https://example.com",
  "brand_name": "Acme",
  "keywords": [
    {"keyword": "best crm", "engine": "google"}
  ],
  "geo_queries": [
    {"query": "best crm for factories", "engine_hint": "global"}
  ]
}
```

Response example:

```json
{
  "domain": "example.com",
  "seo": {},
  "aeo": {},
  "geo": {},
  "errors": []
}
```

### 6.2 `POST /analyze`

Purpose: collect inputs and return the final composite report.

Request body is the same as `/collect`.

Response example:

```json
{
  "domain": "example.com",
  "overall_score": 78.4,
  "dimensions": {
    "seo": {"score": 80.0, "data_complete": true, "detail": {}},
    "aeo": {"score": 60.0, "data_complete": true, "detail": {}},
    "geo": {"score": 90.0, "data_complete": true, "detail": {}},
    "website_audit": {"score": 70.0, "data_complete": true, "detail": {}}
  },
  "recommendations": [],
  "collection_errors": []
}
```

## 7. Error Handling

The service must preserve partial success.

Rules:

- Validation errors should be returned as standard FastAPI 422 responses.
- Provider or collection failures should not crash the service if some data can still be returned.
- If a single source fails, the response should include partial data plus collection errors.
- If collection cannot start because required credentials are missing, return a clear 500-class error from service startup or dependency setup, not a traceback.
- The service should not hide upstream failure details, but it should normalize them into a stable error payload.

The service itself must not implement retries beyond what the existing provider clients or collectors already do.

## 8. Configuration Boundary

Phase 3 keeps configuration minimal.

Required environment variables:

- `DATAFORSEO_LOGIN`
- `DATAFORSEO_PASSWORD`
- `OPENROUTER_API_KEY`
- `QIANFAN_ACCESS_KEY`
- `QIANFAN_SECRET_KEY`

Optional service settings:

- host
- port
- log level

These belong in `settings.py` and should use environment-based loading only.

## 9. Testing Strategy

Testing should cover four layers.

### 9.1 DTO tests

Verify request and response models accept the expected shape and reject invalid payloads.

### 9.2 Adapter tests

Verify conversion between API DTOs and internal collector/scoring objects.

### 9.3 Service tests

Mock `data-collectors` and `analysis-engine` to verify orchestration and partial-failure behavior.

### 9.4 Route tests

Use FastAPI test clients to verify:

- `POST /collect` returns normalized JSON
- `POST /analyze` returns composite report JSON
- invalid payloads get 422
- missing credentials produce a clear startup/runtime error path

## 10. Non-Goals

Phase 3 does not include:

- PostgreSQL or any database
- Celery, Redis, or background workers
- auth, sessions, organizations, or RBAC
- billing or subscriptions
- PDF generation
- scheduled jobs
- frontend UI
- queue-backed report generation

## 11. Handoff Notes

This service should be implemented as a thin wrapper, not a new source of business logic.

The implementation plan should keep endpoint logic minimal, centralize conversion in adapters, and preserve the existing contracts from `data-collectors` and `analysis-engine`.
