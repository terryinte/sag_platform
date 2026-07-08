# Phase 2 Data Collection MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone `services/data-collectors/` Python package that collects real SEO/AEO/GEO inputs from DataForSEO, OpenRouter, and 百度千帆, then either emits normalized JSON or feeds the existing `analysis-engine`.

**Architecture:** Keep collection separate from scoring. `services/data-collectors/` owns provider HTTP calls, normalization, collector orchestration, and a thin CLI. It imports `analysis_engine.models` as the downstream contract and reuses the existing Phase 1 scoring pipeline for `analyze`.

**Tech Stack:** Python 3.11+, `httpx`, `click`, `pytest`, existing `analysis-engine` package, mocked HTTP/provider responses in tests.

---

## File Structure

```
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
    test_models.py
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

`models.py` here is only for collection-layer transport and error reporting. Scoring dataclasses stay in `analysis_engine.models`.

---

### Task 1: Scaffold the package and collection-layer models

**Files:**
- Create: `services/data-collectors/pyproject.toml`
- Create: `services/data-collectors/README.md`
- Create: `services/data-collectors/src/data_collectors/__init__.py`
- Create: `services/data-collectors/src/data_collectors/models.py`
- Create: `services/data-collectors/src/data_collectors/errors.py`
- Test: `services/data-collectors/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `services/data-collectors/tests/test_models.py`:

```python
from data_collectors.models import CollectionError, CollectionPayload, GeoQuerySpec, KeywordSpec


def test_keyword_spec_fields():
    spec = KeywordSpec(keyword="best crm", engine="google")
    assert spec.keyword == "best crm"
    assert spec.engine == "google"


def test_geo_query_spec_fields():
    query = GeoQuerySpec(query="best crm for factories", engine_hint="global")
    assert query.query == "best crm for factories"
    assert query.engine_hint == "global"


def test_collection_error_fields():
    error = CollectionError(
        provider="openrouter",
        operation="geo_query_batch",
        retryable=True,
        message="rate limited",
    )
    assert error.provider == "openrouter"
    assert error.retryable is True


def test_collection_payload_defaults():
    payload = CollectionPayload(domain="example.com")
    assert payload.seo is None
    assert payload.aeo is None
    assert payload.geo is None
    assert payload.errors == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd services/data-collectors && pytest tests/test_models.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'data_collectors'`.

- [ ] **Step 3: Write minimal implementation**

Create `services/data-collectors/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "data-collectors"
version = "0.1.0"
description = "Data collection layer for the SAG diagnostic platform"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "click>=8.1,<9.0",
    "httpx>=0.27,<1.0",
    "analysis-engine @ file:///Users/terry/work/dev_env/copilot-worktrees/sag_platform/terry198411-urban-chainsaw/services/analysis-engine",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0,<9.0",
]

[project.scripts]
data-collectors = "data_collectors.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

Create `services/data-collectors/README.md`:

```markdown
# Data Collectors

Real-API data collection layer for the SAG diagnostic platform.

This package collects SEO, AEO, and GEO inputs from upstream providers and
either emits normalized JSON or feeds the existing `analysis-engine`.
```

Create `services/data-collectors/src/data_collectors/__init__.py`:

```python
"""Data collection layer for the SAG diagnostic platform."""

__version__ = "0.1.0"
```

Create `services/data-collectors/src/data_collectors/models.py`:

```python
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
```

Create `services/data-collectors/src/data_collectors/errors.py`:

```python
from __future__ import annotations

from data_collectors.models import CollectionError


class ProviderError(Exception):
    def __init__(self, provider: str, operation: str, retryable: bool, message: str) -> None:
        super().__init__(message)
        self.provider = provider
        self.operation = operation
        self.retryable = retryable
        self.message = message

    def to_collection_error(self) -> CollectionError:
        return CollectionError(
            provider=self.provider,
            operation=self.operation,
            retryable=self.retryable,
            message=self.message,
        )
```

Create a temporary `services/data-collectors/src/data_collectors/cli.py`:

```python
import click


@click.group()
def main() -> None:
    pass
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd services/data-collectors && pytest tests/test_models.py -v
```

Expected: PASS with `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add services/data-collectors
git commit -m "feat(data-collectors): scaffold package and shared models"
```

---

### Task 2: Add provider HTTP clients and provider parsing tests

**Files:**
- Create: `services/data-collectors/src/data_collectors/providers/__init__.py`
- Create: `services/data-collectors/src/data_collectors/providers/dataforseo.py`
- Create: `services/data-collectors/src/data_collectors/providers/openrouter.py`
- Create: `services/data-collectors/src/data_collectors/providers/qianfan.py`
- Test: `services/data-collectors/tests/test_dataforseo_provider.py`
- Test: `services/data-collectors/tests/test_openrouter_provider.py`
- Test: `services/data-collectors/tests/test_qianfan_provider.py`

- [ ] **Step 1: Write the failing tests**

Create `services/data-collectors/tests/test_dataforseo_provider.py`:

```python
import json

import httpx
import pytest

from data_collectors.errors import ProviderError
from data_collectors.providers.dataforseo import DataForSEOClient


def test_dataforseo_post_returns_task_result():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"tasks": [{"result": [{"keyword": "best crm", "ranked_serp_element": {"position": 2}}]}]},
        )

    client = DataForSEOClient(
        login="login",
        password="password",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.post("/v3/serp/google/organic/live/advanced", [{"keyword": "best crm"}])
    assert result == [{"keyword": "best crm", "ranked_serp_element": {"position": 2}}]


def test_dataforseo_post_raises_provider_error_on_auth_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status_message": "auth failed"})

    client = DataForSEOClient(
        login="login",
        password="password",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderError) as exc:
        client.post("/v3/serp/google/organic/live/advanced", [{"keyword": "best crm"}])

    assert exc.value.provider == "dataforseo"
    assert exc.value.retryable is False
```

Create `services/data-collectors/tests/test_openrouter_provider.py`:

```python
import httpx
import pytest

from data_collectors.errors import ProviderError
from data_collectors.providers.openrouter import OpenRouterClient


def test_openrouter_query_returns_message_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "1. Acme CRM\nSource: https://acme.com"}}]},
        )

    client = OpenRouterClient(
        api_key="token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.query("best crm for factories")
    assert result["provider"] == "openrouter"
    assert "Acme CRM" in result["content"]


def test_openrouter_query_raises_retryable_error_on_429():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    client = OpenRouterClient(
        api_key="token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderError) as exc:
        client.query("best crm for factories")

    assert exc.value.provider == "openrouter"
    assert exc.value.retryable is True
```

Create `services/data-collectors/tests/test_qianfan_provider.py`:

```python
import httpx
import pytest

from data_collectors.errors import ProviderError
from data_collectors.providers.qianfan import QianfanClient


def test_qianfan_query_returns_message_text():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/2.0/token"):
            return httpx.Response(200, json={"access_token": "access-token"})
        return httpx.Response(200, json={"result": "1. Acme CRM\n来源: https://acme.com"})

    client = QianfanClient(
        access_key="ak",
        secret_key="sk",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.query("best crm for factories")
    assert result["provider"] == "qianfan"
    assert "Acme CRM" in result["content"]


def test_qianfan_query_raises_provider_error_on_bad_token_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error_description": "invalid client"})

    client = QianfanClient(
        access_key="ak",
        secret_key="sk",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderError) as exc:
        client.query("best crm for factories")

    assert exc.value.provider == "qianfan"
    assert exc.value.operation == "oauth_token"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd services/data-collectors && pytest tests/test_dataforseo_provider.py tests/test_openrouter_provider.py tests/test_qianfan_provider.py -v
```

Expected: FAIL with import errors for `data_collectors.providers.*`.

- [ ] **Step 3: Write minimal implementation**

Create `services/data-collectors/src/data_collectors/providers/__init__.py`:

```python
from data_collectors.providers.dataforseo import DataForSEOClient
from data_collectors.providers.openrouter import OpenRouterClient
from data_collectors.providers.qianfan import QianfanClient
```

Create `services/data-collectors/src/data_collectors/providers/dataforseo.py`:

```python
from __future__ import annotations

from base64 import b64encode

import httpx

from data_collectors.errors import ProviderError


class DataForSEOClient:
    def __init__(
        self,
        login: str,
        password: str,
        base_url: str = "https://api.dataforseo.com",
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client or httpx.Client(timeout=30.0)
        token = b64encode(f"{login}:{password}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}"}

    def post(self, path: str, payload: list[dict]) -> list[dict]:
        response = self.http_client.post(f"{self.base_url}{path}", json=payload, headers=self.headers)
        if response.status_code == 401:
            raise ProviderError("dataforseo", "post", False, "authentication failed")
        if response.status_code >= 400:
            raise ProviderError("dataforseo", "post", True, f"http {response.status_code}")
        data = response.json()
        tasks = data.get("tasks") or []
        if not tasks or "result" not in tasks[0]:
            raise ProviderError("dataforseo", "post", False, "unexpected response shape")
        return tasks[0]["result"]
```

Create `services/data-collectors/src/data_collectors/providers/openrouter.py`:

```python
from __future__ import annotations

import httpx

from data_collectors.errors import ProviderError


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-4.1-mini",
        base_url: str = "https://openrouter.ai/api/v1",
        http_client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client or httpx.Client(timeout=30.0)
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def query(self, prompt: str) -> dict:
        response = self.http_client.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            },
            headers=self.headers,
        )
        if response.status_code == 429:
            raise ProviderError("openrouter", "geo_query_batch", True, "rate limited")
        if response.status_code >= 400:
            raise ProviderError("openrouter", "geo_query_batch", False, f"http {response.status_code}")
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("openrouter", "geo_query_batch", False, "unexpected response shape")
        return {"provider": "openrouter", "content": choices[0]["message"]["content"]}
```

Create `services/data-collectors/src/data_collectors/providers/qianfan.py`:

```python
from __future__ import annotations

from urllib.parse import urlencode

import httpx

from data_collectors.errors import ProviderError


class QianfanClient:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        token_url: str = "https://aip.baidubce.com/oauth/2.0/token",
        chat_url: str = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions",
        http_client: httpx.Client | None = None,
    ) -> None:
        self.access_key = access_key
        self.secret_key = secret_key
        self.token_url = token_url
        self.chat_url = chat_url
        self.http_client = http_client or httpx.Client(timeout=30.0)

    def _fetch_token(self) -> str:
        response = self.http_client.post(
            self.token_url,
            params={
                "grant_type": "client_credentials",
                "client_id": self.access_key,
                "client_secret": self.secret_key,
            },
        )
        if response.status_code >= 400:
            raise ProviderError("qianfan", "oauth_token", False, "token fetch failed")
        token = response.json().get("access_token")
        if not token:
            raise ProviderError("qianfan", "oauth_token", False, "missing access token")
        return token

    def query(self, prompt: str) -> dict:
        token = self._fetch_token()
        response = self.http_client.post(
            f"{self.chat_url}?{urlencode({'access_token': token})}",
            json={"messages": [{"role": "user", "content": prompt}]},
        )
        if response.status_code >= 400:
            raise ProviderError("qianfan", "geo_query_batch", False, f"http {response.status_code}")
        result = response.json().get("result")
        if not result:
            raise ProviderError("qianfan", "geo_query_batch", False, "unexpected response shape")
        return {"provider": "qianfan", "content": result}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd services/data-collectors && pytest tests/test_dataforseo_provider.py tests/test_openrouter_provider.py tests/test_qianfan_provider.py -v
```

Expected: PASS with `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add services/data-collectors/src/data_collectors/providers services/data-collectors/tests/test_dataforseo_provider.py services/data-collectors/tests/test_openrouter_provider.py services/data-collectors/tests/test_qianfan_provider.py
git commit -m "feat(data-collectors): add provider clients"
```

---

### Task 3: Add mappers that convert provider responses into `analysis-engine` inputs

**Files:**
- Create: `services/data-collectors/src/data_collectors/mappers/__init__.py`
- Create: `services/data-collectors/src/data_collectors/mappers/seo.py`
- Create: `services/data-collectors/src/data_collectors/mappers/aeo.py`
- Create: `services/data-collectors/src/data_collectors/mappers/geo.py`
- Test: `services/data-collectors/tests/test_seo_mapper.py`
- Test: `services/data-collectors/tests/test_aeo_mapper.py`
- Test: `services/data-collectors/tests/test_geo_mapper.py`

- [ ] **Step 1: Write the failing tests**

Create `services/data-collectors/tests/test_seo_mapper.py`:

```python
from data_collectors.mappers.seo import map_seo_result


def test_map_seo_result_builds_seo_input():
    result = map_seo_result(
        domain="example.com",
        keyword_specs=[{"keyword": "best crm", "engine": "google"}],
        ranking_rows=[{"keyword": "best crm", "ranked_serp_element": {"position": 3}, "search_volume": 500}],
        indexed_pages_count=80,
        total_pages_count=100,
    )
    assert result.domain == "example.com"
    assert result.keyword_rankings[0].position == 3
    assert result.indexed_pages_count == 80
```

Create `services/data-collectors/tests/test_aeo_mapper.py`:

```python
from data_collectors.mappers.aeo import map_aeo_result


def test_map_aeo_result_builds_aeo_input():
    result = map_aeo_result(
        domain="example.com",
        snippet_rows=[
            {"keyword": "best crm", "serp_item_type": "featured_snippet"},
            {"keyword": "erp crm", "serp_item_type": "people_also_ask"},
        ],
        total_keywords_checked=2,
    )
    assert result.total_keywords_checked == 2
    assert result.snippet_hits[0].snippet_type == "featured_snippet"
    assert result.snippet_hits[1].snippet_type == "paa"
```

Create `services/data-collectors/tests/test_geo_mapper.py`:

```python
from data_collectors.mappers.geo import map_geo_result


def test_map_geo_result_builds_geo_input():
    result = map_geo_result(
        brand_name="Acme",
        domain="acme.com",
        query_results=[
            {
                "query": "best crm for factories",
                "provider": "openrouter",
                "content": "1. Acme CRM\nSource: https://acme.com\n2. Other Brand",
            }
        ],
    )
    assert result.brand_name == "Acme"
    assert result.mention_results[0].brand_mentioned is True
    assert result.mention_results[0].mention_position == 1
    assert result.mention_results[0].cited_as_source is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd services/data-collectors && pytest tests/test_seo_mapper.py tests/test_aeo_mapper.py tests/test_geo_mapper.py -v
```

Expected: FAIL with import errors for `data_collectors.mappers.*`.

- [ ] **Step 3: Write minimal implementation**

Create `services/data-collectors/src/data_collectors/mappers/__init__.py`:

```python
from data_collectors.mappers.aeo import map_aeo_result
from data_collectors.mappers.geo import map_geo_result
from data_collectors.mappers.seo import map_seo_result
```

Create `services/data-collectors/src/data_collectors/mappers/seo.py`:

```python
from __future__ import annotations

from analysis_engine.models import KeywordRanking, SeoInput


def map_seo_result(
    domain: str,
    keyword_specs: list[dict],
    ranking_rows: list[dict],
    indexed_pages_count: int | None,
    total_pages_count: int | None,
) -> SeoInput:
    ranking_by_keyword = {row["keyword"]: row for row in ranking_rows}
    rankings = []
    for spec in keyword_specs:
        row = ranking_by_keyword.get(spec["keyword"], {})
        serp = row.get("ranked_serp_element") or {}
        rankings.append(
            KeywordRanking(
                keyword=spec["keyword"],
                engine=spec["engine"],
                position=serp.get("position"),
                search_volume=row.get("search_volume"),
            )
        )
    return SeoInput(
        domain=domain,
        keyword_rankings=rankings,
        indexed_pages_count=indexed_pages_count,
        total_pages_count=total_pages_count,
    )
```

Create `services/data-collectors/src/data_collectors/mappers/aeo.py`:

```python
from __future__ import annotations

from analysis_engine.models import AeoInput, FeaturedSnippetHit


def map_aeo_result(domain: str, snippet_rows: list[dict], total_keywords_checked: int) -> AeoInput:
    snippet_type_map = {
        "featured_snippet": "featured_snippet",
        "people_also_ask": "paa",
    }
    hits = [
        FeaturedSnippetHit(
            keyword=row["keyword"],
            engine=row.get("engine", "google"),
            snippet_type=snippet_type_map.get(row.get("serp_item_type"), "none"),
        )
        for row in snippet_rows
    ]
    return AeoInput(domain=domain, snippet_hits=hits, total_keywords_checked=total_keywords_checked)
```

Create `services/data-collectors/src/data_collectors/mappers/geo.py`:

```python
from __future__ import annotations

from analysis_engine.models import BrandMentionResult, GeoInput


def _detect_position(content: str, brand_name: str) -> int | None:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    for index, line in enumerate(lines, start=1):
        if brand_name.lower() in line.lower():
            return index
    return None


def map_geo_result(brand_name: str, domain: str, query_results: list[dict]) -> GeoInput:
    mentions = []
    for row in query_results:
        content = row["content"]
        position = _detect_position(content, brand_name)
        mentions.append(
            BrandMentionResult(
                query=row["query"],
                engine=row["provider"],
                brand_mentioned=position is not None,
                mention_position=position,
                cited_as_source=domain.lower() in content.lower(),
            )
        )
    return GeoInput(brand_name=brand_name, domain=domain, mention_results=mentions)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd services/data-collectors && pytest tests/test_seo_mapper.py tests/test_aeo_mapper.py tests/test_geo_mapper.py -v
```

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add services/data-collectors/src/data_collectors/mappers services/data-collectors/tests/test_seo_mapper.py services/data-collectors/tests/test_aeo_mapper.py services/data-collectors/tests/test_geo_mapper.py
git commit -m "feat(data-collectors): add response mappers"
```

---

### Task 4: Add collectors and pipeline degradation behavior

**Files:**
- Create: `services/data-collectors/src/data_collectors/collectors/__init__.py`
- Create: `services/data-collectors/src/data_collectors/collectors/seo.py`
- Create: `services/data-collectors/src/data_collectors/collectors/aeo.py`
- Create: `services/data-collectors/src/data_collectors/collectors/geo.py`
- Create: `services/data-collectors/src/data_collectors/collectors/pipeline.py`
- Test: `services/data-collectors/tests/test_seo_collector.py`
- Test: `services/data-collectors/tests/test_aeo_collector.py`
- Test: `services/data-collectors/tests/test_geo_collector.py`
- Test: `services/data-collectors/tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Create `services/data-collectors/tests/test_seo_collector.py`:

```python
from data_collectors.collectors.seo import collect_seo_input
from data_collectors.models import KeywordSpec


class FakeDataForSEOClient:
    def post(self, path, payload):
        return [{"keyword": "best crm", "ranked_serp_element": {"position": 2}, "search_volume": 500}]


def test_collect_seo_input_returns_mapped_seo_input():
    result = collect_seo_input(
        domain="example.com",
        keywords=[KeywordSpec(keyword="best crm", engine="google")],
        client=FakeDataForSEOClient(),
    )
    assert result.domain == "example.com"
    assert result.keyword_rankings[0].position == 2
```

Create `services/data-collectors/tests/test_aeo_collector.py`:

```python
from data_collectors.collectors.aeo import collect_aeo_input
from data_collectors.models import KeywordSpec


class FakeDataForSEOClient:
    def post(self, path, payload):
        return [{"keyword": "best crm", "serp_item_type": "featured_snippet", "engine": "google"}]


def test_collect_aeo_input_returns_mapped_aeo_input():
    result = collect_aeo_input(
        domain="example.com",
        keywords=[KeywordSpec(keyword="best crm", engine="google")],
        client=FakeDataForSEOClient(),
    )
    assert result.total_keywords_checked == 1
    assert result.snippet_hits[0].snippet_type == "featured_snippet"
```

Create `services/data-collectors/tests/test_geo_collector.py`:

```python
from data_collectors.collectors.geo import collect_geo_input
from data_collectors.errors import ProviderError
from data_collectors.models import GeoQuerySpec


class FakeOpenRouterClient:
    def query(self, prompt):
        return {"provider": "openrouter", "content": "1. Acme CRM\nSource: https://acme.com"}


class FailingQianfanClient:
    def query(self, prompt):
        raise ProviderError("qianfan", "geo_query_batch", True, "rate limited")


def test_collect_geo_input_returns_partial_success_and_error():
    geo_input, errors = collect_geo_input(
        brand_name="Acme",
        domain="acme.com",
        queries=[GeoQuerySpec(query="best crm for factories")],
        openrouter_client=FakeOpenRouterClient(),
        qianfan_client=FailingQianfanClient(),
    )
    assert len(geo_input.mention_results) == 1
    assert errors[0].provider == "qianfan"
```

Create `services/data-collectors/tests/test_pipeline.py`:

```python
from analysis_engine.models import AeoInput, GeoInput, SeoInput

from data_collectors.collectors.pipeline import build_collection_payload
from data_collectors.models import CollectionError


def test_build_collection_payload_keeps_partial_failures():
    payload = build_collection_payload(
        domain="example.com",
        seo=SeoInput(domain="example.com"),
        aeo=AeoInput(domain="example.com"),
        geo=GeoInput(brand_name="Acme", domain="example.com"),
        errors=[CollectionError(provider="openrouter", operation="geo_query_batch", retryable=True, message="rate limited")],
    )
    assert payload.domain == "example.com"
    assert payload.geo is not None
    assert payload.errors[0].provider == "openrouter"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd services/data-collectors && pytest tests/test_seo_collector.py tests/test_aeo_collector.py tests/test_geo_collector.py tests/test_pipeline.py -v
```

Expected: FAIL with import errors for `data_collectors.collectors.*`.

- [ ] **Step 3: Write minimal implementation**

Create `services/data-collectors/src/data_collectors/collectors/__init__.py`:

```python
from data_collectors.collectors.aeo import collect_aeo_input
from data_collectors.collectors.geo import collect_geo_input
from data_collectors.collectors.pipeline import build_collection_payload
from data_collectors.collectors.seo import collect_seo_input
```

Create `services/data-collectors/src/data_collectors/collectors/seo.py`:

```python
from __future__ import annotations

from data_collectors.mappers.seo import map_seo_result
from data_collectors.models import KeywordSpec


def collect_seo_input(domain: str, keywords: list[KeywordSpec], client) -> object:
    rows = client.post(
        "/v3/serp/google/organic/live/advanced",
        [{"keyword": item.keyword} for item in keywords],
    )
    return map_seo_result(
        domain=domain,
        keyword_specs=[{"keyword": item.keyword, "engine": item.engine} for item in keywords],
        ranking_rows=rows,
        indexed_pages_count=None,
        total_pages_count=None,
    )
```

Create `services/data-collectors/src/data_collectors/collectors/aeo.py`:

```python
from __future__ import annotations

from data_collectors.mappers.aeo import map_aeo_result
from data_collectors.models import KeywordSpec


def collect_aeo_input(domain: str, keywords: list[KeywordSpec], client) -> object:
    rows = client.post(
        "/v3/serp/google/organic/live/advanced",
        [{"keyword": item.keyword} for item in keywords],
    )
    return map_aeo_result(
        domain=domain,
        snippet_rows=rows,
        total_keywords_checked=len(keywords),
    )
```

Create `services/data-collectors/src/data_collectors/collectors/geo.py`:

```python
from __future__ import annotations

from data_collectors.errors import ProviderError
from data_collectors.mappers.geo import map_geo_result
from data_collectors.models import GeoQuerySpec


def collect_geo_input(
    brand_name: str,
    domain: str,
    queries: list[GeoQuerySpec],
    openrouter_client,
    qianfan_client,
) -> tuple[object, list]:
    raw_results = []
    errors = []
    for item in queries:
        try:
            raw_results.append({"query": item.query, **openrouter_client.query(item.query)})
        except ProviderError as exc:
            errors.append(exc.to_collection_error())
        try:
            raw_results.append({"query": item.query, **qianfan_client.query(item.query)})
        except ProviderError as exc:
            errors.append(exc.to_collection_error())
    return map_geo_result(brand_name=brand_name, domain=domain, query_results=raw_results), errors
```

Create `services/data-collectors/src/data_collectors/collectors/pipeline.py`:

```python
from __future__ import annotations

from analysis_engine.models import AeoInput, GeoInput, SeoInput

from data_collectors.models import CollectionError, CollectionPayload


def build_collection_payload(
    domain: str,
    seo: SeoInput | None,
    aeo: AeoInput | None,
    geo: GeoInput | None,
    errors: list[CollectionError],
) -> CollectionPayload:
    return CollectionPayload(domain=domain, seo=seo, aeo=aeo, geo=geo, errors=errors)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd services/data-collectors && pytest tests/test_seo_collector.py tests/test_aeo_collector.py tests/test_geo_collector.py tests/test_pipeline.py -v
```

Expected: PASS with `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add services/data-collectors/src/data_collectors/collectors services/data-collectors/tests/test_seo_collector.py services/data-collectors/tests/test_aeo_collector.py services/data-collectors/tests/test_geo_collector.py services/data-collectors/tests/test_pipeline.py
git commit -m "feat(data-collectors): add collectors and pipeline"
```

---

### Task 5: Add CLI input loading, JSON serialization, and `analyze` mode

**Files:**
- Modify: `services/data-collectors/src/data_collectors/cli.py`
- Test: `services/data-collectors/tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Create `services/data-collectors/tests/test_cli.py`:

```python
import json

from click.testing import CliRunner

from data_collectors import cli as cli_module
from data_collectors.cli import main
from data_collectors.models import CollectionPayload
from analysis_engine.models import AeoInput, GeoInput, ScoreBreakdown, SeoInput


def test_collect_command_prints_normalized_json(monkeypatch, tmp_path):
    keywords_file = tmp_path / "keywords.json"
    geo_queries_file = tmp_path / "geo.json"
    keywords_file.write_text(json.dumps([{"keyword": "best crm", "engine": "google"}]))
    geo_queries_file.write_text(json.dumps([{"query": "best crm for factories"}]))

    monkeypatch.setattr(
        cli_module,
        "run_collection",
        lambda **kwargs: CollectionPayload(
            domain="example.com",
            seo=SeoInput(domain="example.com"),
            aeo=AeoInput(domain="example.com"),
            geo=GeoInput(brand_name="Acme", domain="example.com"),
            errors=[],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "collect",
            "--domain",
            "example.com",
            "--url",
            "https://example.com",
            "--brand-name",
            "Acme",
            "--keywords-file",
            str(keywords_file),
            "--geo-queries-file",
            str(geo_queries_file),
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["domain"] == "example.com"
    assert output["errors"] == []


def test_analyze_command_calls_analysis_engine(monkeypatch, tmp_path):
    keywords_file = tmp_path / "keywords.json"
    geo_queries_file = tmp_path / "geo.json"
    keywords_file.write_text(json.dumps([{"keyword": "best crm", "engine": "google"}]))
    geo_queries_file.write_text(json.dumps([{"query": "best crm for factories"}]))

    monkeypatch.setattr(
        cli_module,
        "run_collection",
        lambda **kwargs: CollectionPayload(
            domain="example.com",
            seo=SeoInput(domain="example.com"),
            aeo=AeoInput(domain="example.com"),
            geo=GeoInput(brand_name="Acme", domain="example.com"),
            errors=[],
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "score_website_audit",
        lambda url: ScoreBreakdown(dimension="website_audit", score=75.0, data_complete=True, detail={}),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "analyze",
            "--domain",
            "example.com",
            "--url",
            "https://example.com",
            "--brand-name",
            "Acme",
            "--keywords-file",
            str(keywords_file),
            "--geo-queries-file",
            str(geo_queries_file),
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["domain"] == "example.com"
    assert "dimensions" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd services/data-collectors && pytest tests/test_cli.py -v
```

Expected: FAIL because `collect` and `analyze` commands do not exist.

- [ ] **Step 3: Write minimal implementation**

Replace `services/data-collectors/src/data_collectors/cli.py` with:

```python
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from analysis_engine.cli import _report_to_dict
from analysis_engine.recommendations import generate_recommendations
from analysis_engine.scoring.aeo import score_aeo
from analysis_engine.scoring.composite import compute_composite_score
from analysis_engine.scoring.geo import score_geo
from analysis_engine.scoring.seo import score_seo
from analysis_engine.scoring.website_audit import score_website_audit

from data_collectors.collectors.pipeline import build_collection_payload
from data_collectors.models import CollectionPayload, GeoQuerySpec, KeywordSpec


def _load_json_list(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def run_collection(
    domain: str,
    url: str,
    brand_name: str,
    keywords_file: Path,
    geo_queries_file: Path,
) -> CollectionPayload:
    keywords = [KeywordSpec(**item) for item in _load_json_list(keywords_file)]
    geo_queries = [GeoQuerySpec(**item) for item in _load_json_list(geo_queries_file)]
    return build_collection_payload(
        domain=domain,
        seo=None,
        aeo=None,
        geo=None,
        errors=[],
    )


def _payload_to_dict(payload: CollectionPayload) -> dict:
    return {
        "domain": payload.domain,
        "seo": asdict(payload.seo) if payload.seo is not None else None,
        "aeo": asdict(payload.aeo) if payload.aeo is not None else None,
        "geo": asdict(payload.geo) if payload.geo is not None else None,
        "errors": [asdict(item) for item in payload.errors],
    }


@click.group()
def main() -> None:
    pass


@main.command()
@click.option("--domain", required=True)
@click.option("--url", required=True)
@click.option("--brand-name", required=True)
@click.option("--keywords-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), required=True)
@click.option("--geo-queries-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), required=True)
def collect(domain: str, url: str, brand_name: str, keywords_file: Path, geo_queries_file: Path) -> None:
    payload = run_collection(
        domain=domain,
        url=url,
        brand_name=brand_name,
        keywords_file=keywords_file,
        geo_queries_file=geo_queries_file,
    )
    click.echo(json.dumps(_payload_to_dict(payload)))


@main.command()
@click.option("--domain", required=True)
@click.option("--url", required=True)
@click.option("--brand-name", required=True)
@click.option("--keywords-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), required=True)
@click.option("--geo-queries-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), required=True)
def analyze(domain: str, url: str, brand_name: str, keywords_file: Path, geo_queries_file: Path) -> None:
    payload = run_collection(
        domain=domain,
        url=url,
        brand_name=brand_name,
        keywords_file=keywords_file,
        geo_queries_file=geo_queries_file,
    )
    seo = score_seo(payload.seo) if payload.seo is not None else score_seo(SeoInput(domain=domain))
    aeo = score_aeo(payload.aeo) if payload.aeo is not None else score_aeo(AeoInput(domain=domain))
    geo = score_geo(payload.geo) if payload.geo is not None else score_geo(GeoInput(brand_name=brand_name, domain=domain))
    website_audit = score_website_audit(url)
    report = compute_composite_score(domain, seo, aeo, geo, website_audit)
    report.recommendations = generate_recommendations(report)
    click.echo(json.dumps(_report_to_dict(report)))
```

Then add the missing imports at the top of `cli.py`:

```python
from analysis_engine.models import AeoInput, GeoInput, SeoInput
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd services/data-collectors && pytest tests/test_cli.py -v
```

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add services/data-collectors/src/data_collectors/cli.py services/data-collectors/tests/test_cli.py
git commit -m "feat(data-collectors): add collect and analyze CLI modes"
```

---

### Task 6: Wire real collectors into CLI, add startup validation, and run full suite

**Files:**
- Modify: `services/data-collectors/src/data_collectors/cli.py`
- Modify: `services/data-collectors/src/data_collectors/collectors/pipeline.py`
- Modify: `services/data-collectors/src/data_collectors/collectors/seo.py`
- Modify: `services/data-collectors/src/data_collectors/collectors/aeo.py`
- Modify: `services/data-collectors/src/data_collectors/collectors/geo.py`
- Modify: `services/data-collectors/tests/test_pipeline.py`
- Modify: `services/data-collectors/tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `services/data-collectors/tests/test_pipeline.py`:

```python
import pytest

from data_collectors.errors import ProviderError
from data_collectors.models import GeoQuerySpec, KeywordSpec
from data_collectors.collectors.pipeline import run_collection_pipeline


class WorkingDataForSEOClient:
    def post(self, path, payload):
        return [{"keyword": payload[0]["keyword"], "ranked_serp_element": {"position": 1}, "search_volume": 1000}]


class FailingOpenRouterClient:
    def query(self, prompt):
        raise ProviderError("openrouter", "geo_query_batch", True, "rate limited")


class WorkingQianfanClient:
    def query(self, prompt):
        return {"provider": "qianfan", "content": "1. Acme CRM\nSource: https://acme.com"}


def test_run_collection_pipeline_keeps_partial_geo_results():
    payload = run_collection_pipeline(
        domain="example.com",
        brand_name="Acme",
        keywords=[KeywordSpec(keyword="best crm", engine="google")],
        geo_queries=[GeoQuerySpec(query="best crm for factories")],
        dataforseo_client=WorkingDataForSEOClient(),
        openrouter_client=FailingOpenRouterClient(),
        qianfan_client=WorkingQianfanClient(),
    )
    assert payload.seo is not None
    assert payload.geo is not None
    assert payload.errors[0].provider == "openrouter"
```

Append to `services/data-collectors/tests/test_cli.py`:

```python
def test_collect_command_fails_fast_without_credentials(monkeypatch, tmp_path):
    keywords_file = tmp_path / "keywords.json"
    geo_queries_file = tmp_path / "geo.json"
    keywords_file.write_text(json.dumps([{"keyword": "best crm", "engine": "google"}]))
    geo_queries_file.write_text(json.dumps([{"query": "best crm for factories"}]))

    monkeypatch.delenv("DATAFORSEO_LOGIN", raising=False)
    monkeypatch.delenv("DATAFORSEO_PASSWORD", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("QIANFAN_ACCESS_KEY", raising=False)
    monkeypatch.delenv("QIANFAN_SECRET_KEY", raising=False)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "collect",
            "--domain",
            "example.com",
            "--url",
            "https://example.com",
            "--brand-name",
            "Acme",
            "--keywords-file",
            str(keywords_file),
            "--geo-queries-file",
            str(geo_queries_file),
        ],
    )

    assert result.exit_code != 0
    assert "Missing required environment variables" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd services/data-collectors && pytest tests/test_pipeline.py tests/test_cli.py -v
```

Expected: FAIL because `run_collection_pipeline` and credential validation do not exist.

- [ ] **Step 3: Write minimal implementation**

Update `services/data-collectors/src/data_collectors/collectors/pipeline.py` to:

```python
from __future__ import annotations

from data_collectors.collectors.aeo import collect_aeo_input
from data_collectors.collectors.geo import collect_geo_input
from data_collectors.collectors.seo import collect_seo_input
from data_collectors.errors import ProviderError
from data_collectors.models import CollectionPayload


def build_collection_payload(domain: str, seo, aeo, geo, errors) -> CollectionPayload:
    return CollectionPayload(domain=domain, seo=seo, aeo=aeo, geo=geo, errors=errors)


def run_collection_pipeline(
    domain: str,
    brand_name: str,
    keywords,
    geo_queries,
    dataforseo_client,
    openrouter_client,
    qianfan_client,
) -> CollectionPayload:
    errors = []

    try:
        seo = collect_seo_input(domain=domain, keywords=keywords, client=dataforseo_client)
    except ProviderError as exc:
        seo = None
        errors.append(exc.to_collection_error())

    try:
        aeo = collect_aeo_input(domain=domain, keywords=keywords, client=dataforseo_client)
    except ProviderError as exc:
        aeo = None
        errors.append(exc.to_collection_error())

    geo, geo_errors = collect_geo_input(
        brand_name=brand_name,
        domain=domain,
        queries=geo_queries,
        openrouter_client=openrouter_client,
        qianfan_client=qianfan_client,
    )
    errors.extend(geo_errors)

    return build_collection_payload(domain=domain, seo=seo, aeo=aeo, geo=geo, errors=errors)
```

Update `services/data-collectors/src/data_collectors/collectors/geo.py` so empty raw results produce a valid empty `GeoInput`:

```python
    if not raw_results:
        return map_geo_result(brand_name=brand_name, domain=domain, query_results=[]), errors
```

Update `services/data-collectors/src/data_collectors/mappers/geo.py` so an empty result set returns an empty `GeoInput`:

```python
    if not query_results:
        return GeoInput(brand_name=brand_name, domain=domain, mention_results=[])
```

Update `services/data-collectors/src/data_collectors/cli.py`:

```python
import os

from data_collectors.collectors.pipeline import run_collection_pipeline
from data_collectors.providers.dataforseo import DataForSEOClient
from data_collectors.providers.openrouter import OpenRouterClient
from data_collectors.providers.qianfan import QianfanClient
```

Add this helper to `cli.py`:

```python
def _require_env(names: list[str]) -> dict[str, str]:
    values = {name: os.getenv(name, "") for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise click.ClickException(f"Missing required environment variables: {', '.join(missing)}")
    return values
```

Replace `run_collection()` in `cli.py` with:

```python
def run_collection(
    domain: str,
    url: str,
    brand_name: str,
    keywords_file: Path,
    geo_queries_file: Path,
) -> CollectionPayload:
    env = _require_env(
        [
            "DATAFORSEO_LOGIN",
            "DATAFORSEO_PASSWORD",
            "OPENROUTER_API_KEY",
            "QIANFAN_ACCESS_KEY",
            "QIANFAN_SECRET_KEY",
        ]
    )
    keywords = [KeywordSpec(**item) for item in _load_json_list(keywords_file)]
    geo_queries = [GeoQuerySpec(**item) for item in _load_json_list(geo_queries_file)]
    return run_collection_pipeline(
        domain=domain,
        brand_name=brand_name,
        keywords=keywords,
        geo_queries=geo_queries,
        dataforseo_client=DataForSEOClient(
            login=env["DATAFORSEO_LOGIN"],
            password=env["DATAFORSEO_PASSWORD"],
        ),
        openrouter_client=OpenRouterClient(api_key=env["OPENROUTER_API_KEY"]),
        qianfan_client=QianfanClient(
            access_key=env["QIANFAN_ACCESS_KEY"],
            secret_key=env["QIANFAN_SECRET_KEY"],
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd services/data-collectors && pytest
```

Expected: PASS with all `services/data-collectors/tests/` tests passing.

- [ ] **Step 5: Commit**

```bash
git add services/data-collectors
git commit -m "feat(data-collectors): wire collection pipeline into CLI"
```

---

## Self-Review

Spec coverage:

- Separate `services/data-collectors/` package: covered by Tasks 1-6
- Provider split for DataForSEO/OpenRouter/百度千帆: covered by Task 2
- Mapping into `SeoInput`/`AeoInput`/`GeoInput`: covered by Task 3
- Partial-failure degradation: covered by Task 4 and Task 6
- `collect` and `analyze` CLI modes: covered by Task 5 and Task 6
- Startup env validation: covered by Task 6
- No FastAPI/DB/queue scope creep: no task introduces those concerns

Placeholder scan:

- No `TODO`, `TBD`, or “implement later” placeholders remain.

Type consistency:

- `CollectionPayload`, `CollectionError`, `KeywordSpec`, and `GeoQuerySpec` are defined before later tasks consume them.
- Provider names and CLI command names remain consistent across tasks.
