# SAG Platform

SEO/AEO/GEO diagnostic platform prototype.

The repository is split into three Python packages:

- `services/analysis-engine`: scoring engine and recommendations
- `services/data-collectors`: upstream SEO/AEO/GEO data collection
- `services/api`: FastAPI service and browser usage page

## Requirements

- Python 3.11+

## Install for Development

Install all local packages in editable mode from the repository root:

```bash
python3 -m pip install -e services/analysis-engine -e services/data-collectors -e services/api
```

For test dependencies, include each package's `dev` extra:

```bash
python3 -m pip install -e "services/analysis-engine[dev]" -e "services/data-collectors[dev]" -e "services/api[dev]"
```

## Run Tests

```bash
(cd services/analysis-engine && pytest)
(cd services/data-collectors && pytest)
(cd services/api && pytest)
```

## Run the API

The API reads provider credentials from environment variables:

```bash
export DATAFORSEO_LOGIN="..."
export DATAFORSEO_PASSWORD="..."
export OPENROUTER_API_KEY="..."
export QIANFAN_ACCESS_KEY="..."
export QIANFAN_SECRET_KEY="..."
```

Start the service:

```bash
cd services/api
uvicorn api.main:app --reload
```

Then open `http://127.0.0.1:8000/` for the browser usage page or
`http://127.0.0.1:8000/docs` for the OpenAPI UI.
