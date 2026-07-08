# Phase 2 Data Collection MVP Design

## 1. Goal

Build a real-API data-collection MVP as a separate Python package that gathers SEO, AEO, and GEO inputs for the existing `analysis-engine` package.

This phase must stop at normalized data collection plus a thin CLI. It must not add FastAPI, a database, a queue, or any SaaS application concerns.

## 2. Confirmed Scope

- Delivery shape: reusable Python package plus thin CLI
- Package location: `services/data-collectors/`
- Upstream providers:
  - `DataForSEO` for SEO and AEO source data
  - `OpenRouter` for overseas GEO queries
  - `百度千帆` for domestic GEO queries
- Downstream contract:
  - Produce `SeoInput`, `AeoInput`, and `GeoInput`
  - Reuse `analysis_engine.models` from `services/analysis-engine`
- CLI modes:
  - `collect`: output normalized SEO/AEO/GEO JSON plus collection errors
  - `analyze`: collect data, call the existing `analysis-engine`, and print the final report

## 3. Architecture

Phase 2 adds a standalone package instead of folding collection into `analysis-engine`.

Reasoning:

- `analysis-engine` is already a pure scoring package with stable contracts.
- External API calling, retries, normalization, and provider-specific parsing are a different responsibility.
- Keeping them separate preserves testability, allows provider replacement, and leaves a clean dependency boundary for Phase 3 service work.

The package structure should be:

```text
services/data-collectors/
  pyproject.toml
  README.md
  src/data_collectors/
    __init__.py
    cli.py
    errors.py
    models.py
    providers/
      __init__.py
      dataforseo.py
      openrouter.py
      qianfan.py
    mappers/
      __init__.py
      seo.py
      aeo.py
      geo.py
    collectors/
      __init__.py
      seo.py
      aeo.py
      geo.py
      pipeline.py
  tests/
    test_dataforseo_provider.py
    test_openrouter_provider.py
    test_qianfan_provider.py
    test_seo_mapper.py
    test_aeo_mapper.py
    test_geo_mapper.py
    test_seo_collector.py
    test_aeo_collector.py
    test_geo_collector.py
    test_pipeline.py
    test_cli.py
```

## 4. Component Boundaries

### 4.1 `providers/`

Each provider module owns the HTTP contract for one upstream service.

- `dataforseo.py`
  - Sends requests for keyword rankings, featured snippets, and PAA data
  - Returns provider-native parsed dictionaries, not `analysis_engine` dataclasses
- `openrouter.py`
  - Sends branded GEO prompts to one overseas LLM endpoint
  - Returns a normalized raw GEO response shape shared with the domestic provider
- `qianfan.py`
  - Sends the same GEO prompts to 百度千帆
  - Returns the same raw GEO response shape as `openrouter.py`

Provider modules must not contain scoring logic or `analysis-engine` imports.

### 4.2 `mappers/`

Mapper modules convert raw provider responses into `analysis_engine.models` inputs.

- `seo.py` maps DataForSEO ranking/indexation output into `SeoInput`
- `aeo.py` maps DataForSEO snippet/PAA output into `AeoInput`
- `geo.py` maps OpenRouter and 百度千帆 raw GEO results into `GeoInput`

The mappers are the only place where raw provider fields become `KeywordRanking`, `FeaturedSnippetHit`, or `BrandMentionResult`.

### 4.3 `collectors/`

Collector modules orchestrate provider calls plus mapping.

- `collectors/seo.py` calls DataForSEO SEO endpoints and returns `SeoInput`
- `collectors/aeo.py` calls DataForSEO AEO endpoints and returns `AeoInput`
- `collectors/geo.py` calls OpenRouter and 百度千帆, merges results, and returns `GeoInput`
- `collectors/pipeline.py` runs all requested collection steps and produces one combined payload for CLI output

Collectors own degradation policy. Providers only report outcomes; collectors decide whether to continue or surface missing-data output.

### 4.4 `cli.py`

The CLI is intentionally thin. It parses arguments, reads input files, invokes pipeline functions, and prints JSON.

It supports:

- `collect`
  - Outputs normalized `seo`, `aeo`, `geo`, and `errors`
- `analyze`
  - Internally calls `collect`
  - Feeds normalized dataclasses into the existing `analysis-engine`
  - Reuses `score_website_audit(url)` from Phase 1
  - Prints the final composite report JSON

## 5. Data Flow

The end-to-end flow is:

1. User runs CLI with `domain`, `url`, `brand_name`, keyword file, GEO query file, and provider credentials in environment variables.
2. CLI loads keyword/query inputs and invokes the collection pipeline.
3. SEO collector calls DataForSEO ranking/indexation endpoints and maps the result to `SeoInput`.
4. AEO collector calls DataForSEO snippet/PAA endpoints and maps the result to `AeoInput`.
5. GEO collector sends the same query set to OpenRouter and 百度千帆, then maps the combined results to `GeoInput`.
6. `collect` mode returns normalized JSON plus any collection errors.
7. `analyze` mode passes the normalized inputs into the existing `analysis-engine` scoring functions and combines them with `score_website_audit(url)`.

Website technical audit is explicitly out of Phase 2 collection scope because the Phase 1 handoff already assigned that responsibility to `geo-optimizer-skill` through `score_website_audit(url)`.

## 6. Input and Output Contracts

### 6.1 CLI inputs

Required runtime arguments:

- `--domain`
- `--url`
- `--brand-name`
- `--keywords-file`
- `--geo-queries-file`

Required environment variables:

- `DATAFORSEO_LOGIN`
- `DATAFORSEO_PASSWORD`
- `OPENROUTER_API_KEY`
- `QIANFAN_ACCESS_KEY`
- `QIANFAN_SECRET_KEY`

MVP keeps model names and endpoint defaults as module constants. It does not add a separate config file system.

### 6.2 `collect` output

The JSON output should have this shape:

```json
{
  "domain": "example.com",
  "seo": {},
  "aeo": {},
  "geo": {},
  "errors": [
    {
      "provider": "openrouter",
      "operation": "geo_query_batch",
      "retryable": true,
      "message": "rate limited"
    }
  ]
}
```

`seo`, `aeo`, and `geo` contain normalized data matching the existing `analysis-engine` dataclass field names so they can be reloaded without translation.

### 6.3 `analyze` output

`analyze` prints the same final report shape already produced by `analysis-engine` CLI, with collection-time failures reflected as missing dimension data where applicable.

## 7. Error Handling

Phase 2 must preserve partial success. A single provider failure must not collapse the whole run unless the CLI cannot start at all.

Rules:

- If DataForSEO fails for SEO collection, return empty SEO data plus a collection error.
- If DataForSEO fails for AEO collection, return empty AEO data plus a collection error.
- If OpenRouter fails but 百度千帆 succeeds, GEO still returns the successful domestic results.
- If 百度千帆 fails but OpenRouter succeeds, GEO still returns the successful overseas results.
- If both GEO providers fail, GEO becomes missing data and both errors are returned.
- Missing credentials, missing required files, or malformed input files are startup errors and should cause a non-zero CLI exit.
- Provider exceptions must be converted into a stable error object with:
  - `provider`
  - `operation`
  - `retryable`
  - `message`

This aligns with the product design rule that one missing source should degrade one dimension rather than block the whole report.

## 8. Provider Strategy

### 8.1 DataForSEO

MVP responsibility:

- Fetch keyword ranking positions for a supplied keyword list
- Fetch data needed to derive featured snippet and PAA hits
- Fetch enough site-level information to populate `indexed_pages_count` and `total_pages_count` if supported by the chosen endpoint mix

If indexation data is not available from the final selected DataForSEO endpoint combination, the SEO mapper may leave those fields as `None` and rely on Phase 1 score renormalization.

### 8.2 OpenRouter

MVP responsibility:

- Run branded GEO prompts against one default overseas model
- Parse whether the brand was mentioned
- Infer mention position if the answer is enumerated or clearly ordered
- Infer whether the brand's domain was cited as a source

### 8.3 百度千帆

MVP responsibility:

- Run the same branded GEO prompts against one default domestic model
- Return the same raw GEO result shape as OpenRouter so the downstream mapper is provider-agnostic

## 9. Testing Strategy

The package should be verified at four layers.

### 9.1 Provider unit tests

Mock HTTP responses and verify:

- success parsing
- auth failure handling
- rate limit handling
- unexpected response shape handling

No provider unit test should call a real upstream service.

### 9.2 Mapper unit tests

Given raw provider payloads, verify correct conversion into:

- `SeoInput`
- `AeoInput`
- `GeoInput`

Cover boundary cases including:

- missing fields
- empty result sets
- unknown rank positions
- explicit citation detection

### 9.3 Collector integration tests

Mock providers and verify orchestration behavior:

- SEO failure does not block AEO/GEO
- one GEO provider failure still returns partial GEO data
- both GEO providers failing returns missing GEO data plus error entries

### 9.4 CLI end-to-end tests

Verify:

- `collect` prints valid JSON
- `analyze` prints a final composite report
- missing credentials fail fast
- provider partial failures still return usable output

## 10. Non-Goals

Phase 2 does not include:

- FastAPI or any HTTP service layer
- PostgreSQL or any persistence
- Celery, Redis, or scheduled jobs
- PDF generation
- authentication, tenant isolation, or billing
- extra search engines such as 360 or 搜狗
- browser automation or custom crawling

## 11. Handoff to Planning

The implementation plan should keep Phase 2 as one bounded package with explicit tests at each layer. It should not introduce API-service concerns early.

The plan should also preserve the existing `analysis-engine` package interface instead of changing scoring contracts to fit provider responses.
