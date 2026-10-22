from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import Response

from api.database import Database
from api.collection_settings import (
    estimate_budget,
    get_strategy,
    list_channels,
    probe_channel,
    save_strategy,
    update_channel,
)
from api.geo_platform import (
    add_key_content,
    add_outcome,
    add_plan_action,
    add_playbook_version,
    bootstrap_project,
    collection_catalog,
    create_baseline,
    create_playbook,
    delete_question,
    generate_questions_for_project,
    get_attempt_detail,
    get_playbook,
    list_attempts,
    list_baselines,
    list_key_contents,
    list_plan,
    list_playbooks,
    list_portfolio,
    list_revisions,
    project_sources,
    project_visibility,
    provider_env_from_settings,
    start_monitoring,
    suggest_plan,
    update_profile,
    update_question,
)
from api.mvp_models import (
    BaselineCreate,
    BootstrapRequest,
    BudgetEstimateRequest,
    ChannelUpdate,
    GenerateQuestionsRequest,
    GeoQuestionUpdate,
    KeyContentCreate,
    MonitorRequest,
    OutcomeCreate,
    PlanActionCreate,
    PlaybookCreate,
    PlaybookVersionCreate,
    ProjectProfileUpdate,
    StrategyUpdate,
)
from api.mvp_service import get_project
from api.settings import settings

_STATIC = Path(__file__).parent / "geo_static"


def geo_page_html() -> str:
    return (_STATIC / "index.html").read_text(encoding="utf-8")


def build_llm_complete(env: dict):
    """Return a JSON-oriented completion callable, or None when no key is set."""
    import httpx

    openai_key = env.get("OPENAI_API_KEY") or ""
    openrouter_key = env.get("OPENROUTER_API_KEY") or ""
    if not openai_key and not openrouter_key:
        return None
    http = httpx.Client(timeout=30.0)

    def complete(prompt: str) -> str:
        if openai_key:
            response = http.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {openai_key}"},
                json={
                    "model": "gpt-4.1-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
            )
        else:
            response = http.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {openrouter_key}"},
                json={
                    "model": "openai/gpt-4.1-mini",
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    return complete


def register_geo_routes(application: FastAPI, database: Database) -> None:
    @application.get("/geo-static/{name}")
    def geo_static(name: str) -> Response:
        if name not in {"app.js", "style.css"}:
            raise LookupError("asset")
        media = "text/css" if name.endswith(".css") else "application/javascript"
        return Response((_STATIC / name).read_text(encoding="utf-8"), media_type=media)

    @application.get("/api/geo/portfolio")
    def geo_portfolio() -> dict:
        return list_portfolio(database)

    @application.get("/api/geo/collection-catalog")
    def geo_catalog() -> list[dict]:
        return collection_catalog()

    @application.get("/api/geo/channels")
    def geo_channels() -> list[dict]:
        return list_channels(database, provider_env_from_settings(settings))

    @application.put("/api/geo/channels/{channel_id}")
    def geo_channel_update(channel_id: str, payload: ChannelUpdate) -> dict:
        return update_channel(database, channel_id, payload, provider_env_from_settings(settings))

    @application.post("/api/geo/channels/{channel_id}/test")
    def geo_channel_test(channel_id: str) -> dict:
        return probe_channel(database, channel_id, provider_env_from_settings(settings))

    @application.get("/api/projects/{project_id}/collection-strategy")
    def geo_strategy(project_id: int) -> dict:
        get_project(database, project_id)
        return get_strategy(database, project_id)

    @application.put("/api/projects/{project_id}/collection-strategy")
    def geo_strategy_save(project_id: int, payload: StrategyUpdate) -> dict:
        get_project(database, project_id)
        return save_strategy(database, project_id, payload)

    @application.post("/api/projects/{project_id}/geo/budget-estimate")
    def geo_budget(project_id: int, payload: BudgetEstimateRequest) -> dict:
        get_project(database, project_id)
        return estimate_budget(database, project_id, payload)

    @application.post("/api/geo/bootstrap", status_code=201)
    def geo_bootstrap(payload: BootstrapRequest) -> dict:
        return bootstrap_project(database, payload)

    @application.put("/api/projects/{project_id}/profile")
    def geo_profile(project_id: int, payload: ProjectProfileUpdate) -> dict:
        return update_profile(database, project_id, payload)

    @application.get("/api/projects/{project_id}/key-contents")
    def geo_key_contents(project_id: int) -> list[dict]:
        return list_key_contents(database, project_id)

    @application.post("/api/projects/{project_id}/key-contents", status_code=201)
    def geo_key_contents_create(project_id: int, payload: KeyContentCreate) -> dict:
        return add_key_content(database, project_id, payload)

    @application.post("/api/projects/{project_id}/geo/questions/generate", status_code=201)
    def geo_questions_generate(project_id: int, payload: GenerateQuestionsRequest) -> dict:
        env = provider_env_from_settings(settings)
        complete = build_llm_complete(env) if payload.llm else None
        return generate_questions_for_project(database, project_id, payload.name, complete)

    @application.put("/api/geo/questions/{question_id}")
    def geo_question_update(question_id: int, payload: GeoQuestionUpdate) -> dict:
        return update_question(database, question_id, payload)

    @application.delete("/api/geo/questions/{question_id}")
    def geo_question_delete(question_id: int) -> dict:
        return delete_question(database, question_id)

    @application.get("/api/projects/{project_id}/geo/baselines")
    def geo_baselines(project_id: int) -> list[dict]:
        return list_baselines(database, project_id)

    @application.post("/api/projects/{project_id}/geo/baselines", status_code=201)
    def geo_baselines_create(project_id: int, payload: BaselineCreate) -> dict:
        return create_baseline(database, project_id, payload)

    @application.post("/api/projects/{project_id}/geo/monitor")
    def geo_monitor(project_id: int, payload: MonitorRequest) -> dict:
        env = provider_env_from_settings(settings)
        return start_monitoring(
            database,
            project_id,
            payload.baseline_id,
            env=env,
            llm_complete=build_llm_complete(env),
        )

    @application.get("/api/projects/{project_id}/geo/visibility")
    def geo_visibility(project_id: int) -> dict:
        return project_visibility(database, project_id)

    @application.get("/api/projects/{project_id}/geo/sources")
    def geo_sources(project_id: int) -> dict:
        return project_sources(database, project_id)

    @application.get("/api/projects/{project_id}/geo/attempts")
    def geo_attempts(project_id: int, run_id: int | None = None) -> list[dict]:
        return list_attempts(database, project_id, run_id)

    @application.get("/api/geo/attempts/{attempt_id}")
    def geo_attempt_detail(attempt_id: int) -> dict:
        return get_attempt_detail(database, attempt_id)

    @application.get("/api/geo/responses/{response_id}/revisions")
    def geo_revisions(response_id: int) -> list[dict]:
        return list_revisions(database, response_id)

    @application.get("/api/playbooks")
    def playbooks_index() -> list[dict]:
        return list_playbooks(database)

    @application.post("/api/playbooks", status_code=201)
    def playbooks_create(payload: PlaybookCreate) -> dict:
        return create_playbook(database, payload)

    @application.get("/api/playbooks/{playbook_id}")
    def playbooks_show(playbook_id: int) -> dict:
        return get_playbook(database, playbook_id)

    @application.post("/api/playbooks/{playbook_id}/versions", status_code=201)
    def playbooks_version(playbook_id: int, payload: PlaybookVersionCreate) -> dict:
        return add_playbook_version(database, playbook_id, payload)

    @application.get("/api/projects/{project_id}/plan")
    def plan_index(project_id: int) -> list[dict]:
        return list_plan(database, project_id)

    @application.post("/api/projects/{project_id}/plan-actions", status_code=201)
    def plan_create(project_id: int, payload: PlanActionCreate) -> dict:
        return add_plan_action(database, project_id, payload)

    @application.post("/api/projects/{project_id}/plan/suggest", status_code=201)
    def plan_suggest(project_id: int) -> list[dict]:
        return suggest_plan(database, project_id)

    @application.post("/api/plan-actions/{plan_action_id}/outcomes", status_code=201)
    def outcomes_create(plan_action_id: int, payload: OutcomeCreate) -> dict:
        return add_outcome(database, plan_action_id, payload)
