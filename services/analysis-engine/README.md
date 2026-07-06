# Analysis Engine

SEO/AEO/GEO composite scoring engine for the SAG diagnostic platform.

Computes a 0-100 composite visibility score (plus per-dimension SEO/AEO/GEO/website-audit
scores and prioritized recommendations) for a customer's brand and domain.

## Install (editable, for development)

```bash
cd services/analysis-engine
pip install -e ".[dev]"
```

## Run the CLI

```bash
analysis-engine --domain example.com --url https://example.com --brand-name Acme
```

Optionally pass `--seo-data`, `--aeo-data`, `--geo-data` JSON files (see
`tests/test_cli.py` for the expected shape) to include SEO/AEO/GEO scores —
these come from the Phase 2 data-collection layer once it exists. Without
them, those dimensions are reported as missing data with a high-priority
recommendation.

## Run tests

```bash
pytest
```
