from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from api.database import Database
from api.models import AnalyzeRequest, AnalyzeResponse, CollectRequest, CollectResponse
from api.mvp_models import (
    ClientCreate,
    ClientUpdate,
    CommitmentCreate,
    CompetitorCreate,
    GeoBatchRunRequest,
    GeoQuestionCreate,
    GeoResponseCreate,
    GeoResponseReview,
    GeoRunCreate,
    KeywordRankingCreate,
    KeywordTargetCreate,
    ProjectCreate,
    ProjectUpdate,
    QuestionSetCreate,
    ReportCreate,
    SeoImportRequest,
    SeoMetricCreate,
)
from api.mvp_service import (
    create_client,
    create_commitment,
    create_competitor,
    create_geo_response,
    create_geo_run,
    create_keyword_ranking,
    create_keyword_target,
    create_project,
    create_question,
    create_question_set,
    create_report,
    create_seo_metric,
    get_project,
    import_seo_csv,
    list_clients,
    list_commitments,
    list_geo_responses,
    list_geo_runs,
    list_keyword_targets,
    list_projects,
    list_question_sets,
    list_questions,
    list_reports,
    list_seo_data,
    project_dashboard,
    project_assessment,
    render_report_html,
    review_geo_response,
    run_geo_batch,
    seed_demo,
    update_client,
    update_commitment,
    update_project,
)
from api.geo_routes import geo_page_html, register_geo_routes
from api.mvp_ui import render_mvp_page
from api.services import analyze_service, collect_service
from api.settings import settings
from api.ui import render_usage_page


def create_app(database_path: str | Path | None = None) -> FastAPI:
    application = FastAPI(title="SAG SEO/GEO 独立测评平台", version="0.1.0")
    database = Database(database_path or settings.database_path)
    database.initialize()
    application.state.database = database
    register_geo_routes(application, database)

    @application.exception_handler(RuntimeError)
    async def runtime_error_handler(_: Request, exc: RuntimeError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @application.exception_handler(LookupError)
    async def lookup_error_handler(_: Request, exc: LookupError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @application.exception_handler(sqlite3.IntegrityError)
    async def integrity_error_handler(_: Request, exc: sqlite3.IntegrityError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @application.get("/", response_class=HTMLResponse)
    def mvp_page() -> str:
        return geo_page_html()

    @application.get("/ui", response_class=HTMLResponse)
    def mvp_ui_alias() -> str:
        return geo_page_html()

    @application.get("/workbench", response_class=HTMLResponse)
    def legacy_workbench() -> str:
        return render_mvp_page()

    @application.get("/console", response_class=HTMLResponse)
    def usage_console() -> str:
        return render_usage_page()

    @application.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "database": str(database.path)}

    @application.post("/collect", response_model=CollectResponse)
    def collect(request: CollectRequest) -> dict:
        return collect_service(request)

    @application.post("/analyze", response_model=AnalyzeResponse)
    def analyze(request: AnalyzeRequest) -> dict:
        return analyze_service(request)

    @application.get("/api/clients")
    def clients_index() -> list[dict]:
        return list_clients(database)

    @application.post("/api/clients", status_code=201)
    def clients_create(payload: ClientCreate) -> dict:
        return create_client(database, payload)

    @application.put("/api/clients/{client_id}")
    def clients_update(client_id: int, payload: ClientUpdate) -> dict:
        return update_client(database, client_id, payload)

    @application.get("/api/projects")
    def projects_index(client_id: int | None = None) -> list[dict]:
        return list_projects(database, client_id)

    @application.post("/api/projects", status_code=201)
    def projects_create(payload: ProjectCreate) -> dict:
        return create_project(database, payload)

    @application.put("/api/projects/{project_id}")
    def projects_update(project_id: int, payload: ProjectUpdate) -> dict:
        return update_project(database, project_id, payload)

    @application.get("/api/projects/{project_id}")
    def projects_show(project_id: int) -> dict:
        return get_project(database, project_id)

    @application.get("/api/projects/{project_id}/dashboard")
    def dashboard(project_id: int) -> dict:
        return project_dashboard(database, project_id)

    @application.get("/api/projects/{project_id}/assessment")
    def assessment(project_id: int) -> dict:
        return project_assessment(database, project_id)

    @application.post("/api/projects/{project_id}/competitors", status_code=201)
    def competitors_create(project_id: int, payload: CompetitorCreate) -> dict:
        return create_competitor(database, project_id, payload)

    @application.get("/api/projects/{project_id}/commitments")
    def commitments_index(project_id: int) -> list[dict]:
        return list_commitments(database, project_id)

    @application.post("/api/projects/{project_id}/commitments", status_code=201)
    def commitments_create(project_id: int, payload: CommitmentCreate) -> dict:
        return create_commitment(database, project_id, payload)

    @application.put("/api/commitments/{commitment_id}")
    def commitments_update(commitment_id: int, payload: CommitmentCreate) -> dict:
        return update_commitment(database, commitment_id, payload)

    @application.get("/api/projects/{project_id}/keyword-targets")
    def keyword_targets_index(project_id: int) -> list[dict]:
        return list_keyword_targets(database, project_id)

    @application.post("/api/projects/{project_id}/keyword-targets", status_code=201)
    def keyword_targets_create(project_id: int, payload: KeywordTargetCreate) -> dict:
        return create_keyword_target(database, project_id, payload)

    @application.get("/api/projects/{project_id}/seo")
    def seo_index(project_id: int) -> dict:
        return list_seo_data(database, project_id)

    @application.post("/api/projects/{project_id}/seo/metrics", status_code=201)
    def seo_metrics_create(project_id: int, payload: SeoMetricCreate) -> dict:
        return create_seo_metric(database, project_id, payload)

    @application.post("/api/projects/{project_id}/seo/rankings", status_code=201)
    def seo_rankings_create(project_id: int, payload: KeywordRankingCreate) -> dict:
        return create_keyword_ranking(database, project_id, payload)

    @application.post("/api/projects/{project_id}/seo/import")
    def seo_import(project_id: int, payload: SeoImportRequest) -> dict:
        return import_seo_csv(database, project_id, payload)

    @application.get("/api/projects/{project_id}/geo/question-sets")
    def question_sets_index(project_id: int) -> list[dict]:
        return list_question_sets(database, project_id)

    @application.post("/api/projects/{project_id}/geo/question-sets", status_code=201)
    def question_sets_create(project_id: int, payload: QuestionSetCreate) -> dict:
        return create_question_set(database, project_id, payload)

    @application.get("/api/geo/question-sets/{question_set_id}/questions")
    def questions_index(question_set_id: int) -> list[dict]:
        return list_questions(database, question_set_id)

    @application.post("/api/geo/question-sets/{question_set_id}/questions", status_code=201)
    def questions_create(question_set_id: int, payload: GeoQuestionCreate) -> dict:
        return create_question(database, question_set_id, payload)

    @application.get("/api/projects/{project_id}/geo/runs")
    def geo_runs_index(project_id: int) -> list[dict]:
        return list_geo_runs(database, project_id)

    @application.post("/api/projects/{project_id}/geo/runs", status_code=201)
    def geo_runs_create(project_id: int, payload: GeoRunCreate) -> dict:
        return create_geo_run(database, project_id, payload)

    @application.post("/api/projects/{project_id}/geo/runs/batch")
    def geo_runs_batch(project_id: int, payload: GeoBatchRunRequest) -> dict:
        return run_geo_batch(database, settings, project_id, payload)

    @application.get("/api/geo/runs/{geo_run_id}/responses")
    def geo_responses_index(geo_run_id: int) -> list[dict]:
        return list_geo_responses(database, geo_run_id)

    @application.post("/api/geo/runs/{geo_run_id}/responses", status_code=201)
    def geo_responses_create(geo_run_id: int, payload: GeoResponseCreate) -> dict:
        return create_geo_response(database, geo_run_id, payload)

    @application.put("/api/geo/responses/{response_id}/review")
    def geo_responses_review(response_id: int, payload: GeoResponseReview) -> dict:
        return review_geo_response(database, response_id, payload)

    @application.get("/api/projects/{project_id}/reports")
    def reports_index(project_id: int) -> list[dict]:
        return list_reports(database, project_id)

    @application.post("/api/projects/{project_id}/reports", status_code=201)
    def reports_create(project_id: int, payload: ReportCreate) -> dict:
        return create_report(database, project_id, payload)

    @application.get("/reports/{project_id}/preview", response_class=HTMLResponse)
    def reports_preview(project_id: int) -> str:
        return render_report_html(database, project_id)

    @application.get("/reports/{project_id}/{report_id}", response_class=HTMLResponse)
    def reports_show(project_id: int, report_id: int) -> str:
        return render_report_html(database, project_id, report_id)

    @application.post("/api/demo/seed")
    def demo_seed() -> dict:
        return seed_demo(database)

    return application


app = create_app()
