from __future__ import annotations

import csv
import html
import io
import json
import re
from collections import defaultdict
from datetime import date

from data_collectors.errors import ProviderError
from data_collectors.providers.openrouter import OpenRouterClient
from data_collectors.providers.qianfan import QianfanClient
from analysis_engine.models import BrandMentionResult, GeoInput, KeywordRanking, SeoInput
from analysis_engine.scoring.geo import score_geo
from analysis_engine.scoring.seo import score_seo

from api.database import Database
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
from api.settings import Settings


def _require(record: dict | None, name: str) -> dict:
    if record is None:
        raise LookupError(f"{name} not found")
    return record


def _insert(db: Database, table: str, values: dict) -> dict:
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    record_id = db.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        tuple(values.values()),
    )
    return _require(db.fetch_one(f"SELECT * FROM {table} WHERE id = ?", (record_id,)), table)


def create_client(db: Database, payload: ClientCreate) -> dict:
    return _insert(db, "clients", payload.model_dump())


def list_clients(db: Database) -> list[dict]:
    return db.fetch_all(
        """
        SELECT c.*, COUNT(p.id) AS project_count
        FROM clients c
        LEFT JOIN projects p ON p.client_id = c.id
        GROUP BY c.id
        ORDER BY c.id DESC
        """
    )


def update_client(db: Database, client_id: int, payload: ClientUpdate) -> dict:
    _require(db.fetch_one("SELECT id FROM clients WHERE id = ?", (client_id,)), "client")
    values = payload.model_dump()
    assignments = ", ".join(f"{key} = ?" for key in values)
    db.execute(f"UPDATE clients SET {assignments} WHERE id = ?", (*values.values(), client_id))
    return _require(db.fetch_one("SELECT * FROM clients WHERE id = ?", (client_id,)), "client")


def create_project(db: Database, payload: ProjectCreate) -> dict:
    _require(db.fetch_one("SELECT id FROM clients WHERE id = ?", (payload.client_id,)), "client")
    return _insert(db, "projects", payload.model_dump())


def update_project(db: Database, project_id: int, payload: ProjectUpdate) -> dict:
    get_project(db, project_id)
    _require(db.fetch_one("SELECT id FROM clients WHERE id = ?", (payload.client_id,)), "client")
    values = payload.model_dump()
    assignments = ", ".join(f"{key} = ?" for key in values)
    db.execute(f"UPDATE projects SET {assignments} WHERE id = ?", (*values.values(), project_id))
    return get_project(db, project_id)


def list_projects(db: Database, client_id: int | None = None) -> list[dict]:
    where = "WHERE p.client_id = ?" if client_id is not None else ""
    params = (client_id,) if client_id is not None else ()
    return db.fetch_all(
        f"""
        SELECT p.*, c.name AS client_name, c.brand_name, c.domain,
               COUNT(DISTINCT cm.id) AS commitment_count,
               COUNT(DISTINCT gr.id) AS geo_run_count
        FROM projects p
        JOIN clients c ON c.id = p.client_id
        LEFT JOIN commitments cm ON cm.project_id = p.id
        LEFT JOIN geo_runs gr ON gr.project_id = p.id
        {where}
        GROUP BY p.id
        ORDER BY p.id DESC
        """,
        params,
    )


def get_project(db: Database, project_id: int) -> dict:
    project = _require(
        db.fetch_one(
            """
            SELECT p.*, c.name AS client_name, c.brand_name, c.domain, c.industry,
                   c.contact_name, c.contact_email
            FROM projects p
            JOIN clients c ON c.id = p.client_id
            WHERE p.id = ?
            """,
            (project_id,),
        ),
        "project",
    )
    project["competitors"] = db.fetch_all(
        "SELECT * FROM competitors WHERE project_id = ? ORDER BY id", (project_id,)
    )
    return project


def create_competitor(db: Database, project_id: int, payload: CompetitorCreate) -> dict:
    get_project(db, project_id)
    return _insert(db, "competitors", {"project_id": project_id, **payload.model_dump()})


def create_commitment(db: Database, project_id: int, payload: CommitmentCreate) -> dict:
    get_project(db, project_id)
    return _insert(db, "commitments", {"project_id": project_id, **payload.model_dump()})


def list_commitments(db: Database, project_id: int) -> list[dict]:
    get_project(db, project_id)
    return db.fetch_all(
        "SELECT * FROM commitments WHERE project_id = ? ORDER BY category, id", (project_id,)
    )


def update_commitment(db: Database, commitment_id: int, payload: CommitmentCreate) -> dict:
    existing = _require(
        db.fetch_one("SELECT * FROM commitments WHERE id = ?", (commitment_id,)),
        "commitment",
    )
    values = payload.model_dump()
    assignments = ", ".join(f"{key} = ?" for key in values)
    db.execute(
        f"UPDATE commitments SET {assignments} WHERE id = ?",
        (*values.values(), commitment_id),
    )
    return _require(
        db.fetch_one("SELECT * FROM commitments WHERE id = ?", (existing["id"],)),
        "commitment",
    )


def create_keyword_target(db: Database, project_id: int, payload: KeywordTargetCreate) -> dict:
    get_project(db, project_id)
    return _insert(db, "keyword_targets", {"project_id": project_id, **payload.model_dump()})


def list_keyword_targets(db: Database, project_id: int) -> list[dict]:
    return db.fetch_all(
        "SELECT * FROM keyword_targets WHERE project_id = ? ORDER BY id", (project_id,)
    )


def create_seo_metric(db: Database, project_id: int, payload: SeoMetricCreate) -> dict:
    get_project(db, project_id)
    return _insert(db, "seo_metrics", {"project_id": project_id, **payload.model_dump()})


def create_keyword_ranking(
    db: Database, project_id: int, payload: KeywordRankingCreate
) -> dict:
    get_project(db, project_id)
    return _insert(db, "keyword_rankings", {"project_id": project_id, **payload.model_dump()})


def list_seo_data(db: Database, project_id: int) -> dict:
    get_project(db, project_id)
    return {
        "metrics": db.fetch_all(
            "SELECT * FROM seo_metrics WHERE project_id = ? ORDER BY captured_at DESC, id DESC",
            (project_id,),
        ),
        "rankings": db.fetch_all(
            """
            SELECT * FROM keyword_rankings
            WHERE project_id = ?
            ORDER BY captured_at DESC, keyword, engine
            """,
            (project_id,),
        ),
    }


def _normalized_row(row: dict) -> dict:
    aliases = {
        "关键词": "keyword",
        "关键字": "keyword",
        "排名": "position",
        "rank": "position",
        "搜索量": "search_volume",
        "volume": "search_volume",
        "搜索引擎": "engine",
        "地域": "region_name",
        "地区": "region_name",
        "语言": "language",
        "类型": "category",
        "目标页面": "target_url",
        "url": "target_url",
        "日期": "captured_at",
        "数据源": "source",
        "指标编码": "metric_key",
        "指标": "metric_name",
        "数值": "value",
        "单位": "unit",
    }
    normalized = {}
    for key, value in row.items():
        clean_key = (key or "").strip().lower()
        normalized[aliases.get(clean_key, clean_key)] = (value or "").strip()
    return normalized


def _optional_int(value: str) -> int | None:
    if not value:
        return None
    match = re.search(r"-?\d+", value.replace(",", ""))
    return int(match.group()) if match else None


def _optional_float(value: str) -> float | None:
    if not value:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
    return float(match.group()) if match else None


def import_seo_csv(db: Database, project_id: int, payload: SeoImportRequest) -> dict:
    get_project(db, project_id)
    content = payload.content.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(content))
    rankings: list[tuple] = []
    metrics: list[tuple] = []
    rejected: list[dict] = []
    for line_number, raw in enumerate(reader, start=2):
        row = _normalized_row(raw)
        captured_at = row.get("captured_at") or payload.default_captured_at
        source = row.get("source") or payload.default_source
        if row.get("keyword"):
            rankings.append(
                (
                    project_id,
                    captured_at,
                    source,
                    row["keyword"],
                    row.get("category") or "commercial",
                    row.get("engine") or "baidu",
                    row.get("region_name") or "全国",
                    row.get("language") or "zh-CN",
                    _optional_int(row.get("position", "")),
                    _optional_int(row.get("search_volume", "")),
                    row.get("target_url", ""),
                )
            )
        elif row.get("metric_key") and _optional_float(row.get("value", "")) is not None:
            metrics.append(
                (
                    project_id,
                    captured_at,
                    source,
                    row["metric_key"],
                    row.get("metric_name") or row["metric_key"],
                    _optional_float(row["value"]),
                    row.get("unit", ""),
                    row.get("notes", ""),
                )
            )
        else:
            rejected.append({"line": line_number, "reason": "missing keyword or metric_key/value"})

    db.execute_many(
        """
        INSERT INTO keyword_rankings
        (project_id, captured_at, source, keyword, category, engine, region_name, language, position, search_volume, target_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rankings,
    )
    db.execute_many(
        """
        INSERT INTO seo_metrics
        (project_id, captured_at, source, metric_key, metric_name, value, unit, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        metrics,
    )
    return {
        "filename": payload.filename,
        "rankings_imported": len(rankings),
        "metrics_imported": len(metrics),
        "rejected": rejected,
    }


def create_question_set(db: Database, project_id: int, payload: QuestionSetCreate) -> dict:
    get_project(db, project_id)
    return _insert(db, "geo_question_sets", {"project_id": project_id, **payload.model_dump()})


def list_question_sets(db: Database, project_id: int) -> list[dict]:
    rows = db.fetch_all(
        """
        SELECT qs.*, COUNT(q.id) AS question_count
        FROM geo_question_sets qs
        LEFT JOIN geo_questions q ON q.question_set_id = qs.id
        WHERE qs.project_id = ?
        GROUP BY qs.id
        ORDER BY qs.id DESC
        """,
        (project_id,),
    )
    return rows


def create_question(
    db: Database, question_set_id: int, payload: GeoQuestionCreate
) -> dict:
    _require(
        db.fetch_one("SELECT id FROM geo_question_sets WHERE id = ?", (question_set_id,)),
        "question set",
    )
    return _insert(
        db,
        "geo_questions",
        {"question_set_id": question_set_id, **payload.model_dump()},
    )


def list_questions(db: Database, question_set_id: int) -> list[dict]:
    return db.fetch_all(
        "SELECT * FROM geo_questions WHERE question_set_id = ? ORDER BY intent, id",
        (question_set_id,),
    )


def create_geo_run(db: Database, project_id: int, payload: GeoRunCreate) -> dict:
    get_project(db, project_id)
    question_set = _require(
        db.fetch_one("SELECT * FROM geo_question_sets WHERE id = ?", (payload.question_set_id,)),
        "question set",
    )
    if question_set["project_id"] != project_id:
        raise ValueError("question set does not belong to project")
    return _insert(db, "geo_runs", {"project_id": project_id, **payload.model_dump()})


def list_geo_runs(db: Database, project_id: int) -> list[dict]:
    return db.fetch_all(
        """
        SELECT r.*, qs.name AS question_set_name, qs.version,
               COUNT(resp.id) AS response_count,
               SUM(CASE WHEN resp.review_status = 'reviewed' THEN 1 ELSE 0 END) AS reviewed_count
        FROM geo_runs r
        JOIN geo_question_sets qs ON qs.id = r.question_set_id
        LEFT JOIN geo_responses resp ON resp.geo_run_id = r.id
        WHERE r.project_id = ?
        GROUP BY r.id
        ORDER BY r.run_at DESC, r.id DESC
        """,
        (project_id,),
    )


def _detect_geo_fields(
    project: dict, competitors: list[dict], raw_response: str
) -> dict:
    text = raw_response.casefold()
    brand_aliases = [project["brand_name"], project["domain"].split(".")[0]]
    mentioned = any(alias and alias.casefold() in text for alias in brand_aliases)
    position = None
    for index, line in enumerate(
        [item.strip() for item in raw_response.splitlines() if item.strip()], start=1
    ):
        if any(alias and alias.casefold() in line.casefold() for alias in brand_aliases):
            position = index
            break
    competitor_mentions = [
        item["name"] for item in competitors if item["name"].casefold() in text
    ]
    return {
        "brand_mentioned": mentioned,
        "mention_position": position,
        "recommended": bool(mentioned and position is not None and position <= 3),
        "competitor_mentions": competitor_mentions,
        "cited_source": project["domain"].casefold() in text,
    }


def create_geo_response(
    db: Database, geo_run_id: int, payload: GeoResponseCreate
) -> dict:
    run = _require(db.fetch_one("SELECT * FROM geo_runs WHERE id = ?", (geo_run_id,)), "geo run")
    project = get_project(db, run["project_id"])
    detected = _detect_geo_fields(project, project["competitors"], payload.raw_response)
    values = payload.model_dump()
    for key in ("brand_mentioned", "mention_position", "cited_source"):
        if values[key] is None:
            values[key] = detected[key]
    if not values["competitor_mentions"]:
        values["competitor_mentions"] = detected["competitor_mentions"]
    if not values["recommended"]:
        values["recommended"] = detected["recommended"]
    values["competitor_mentions"] = json.dumps(values["competitor_mentions"], ensure_ascii=False)
    for key in ("brand_mentioned", "accurate", "recommended", "cited_source"):
        if values[key] is not None:
            values[key] = int(values[key])
    return _insert(db, "geo_responses", {"geo_run_id": geo_run_id, **values})


def review_geo_response(
    db: Database, response_id: int, payload: GeoResponseReview
) -> dict:
    _require(
        db.fetch_one("SELECT id FROM geo_responses WHERE id = ?", (response_id,)),
        "geo response",
    )
    values = payload.model_dump()
    values["competitor_mentions"] = json.dumps(values["competitor_mentions"], ensure_ascii=False)
    for key in ("brand_mentioned", "accurate", "recommended", "cited_source"):
        if values[key] is not None:
            values[key] = int(values[key])
    assignments = ", ".join(f"{key} = ?" for key in values)
    db.execute(
        f"UPDATE geo_responses SET {assignments} WHERE id = ?",
        (*values.values(), response_id),
    )
    db.execute(
        """
        INSERT INTO geo_analysis_revisions
            (attempt_id, response_id, parser_version, reviewer, result_json, valid)
        VALUES (NULL, ?, 'judge-1', 'human', ?, 1)
        """,
        (
            response_id,
            json.dumps({"reviewer": "human", "sample_state": "ok", **payload.model_dump()}, ensure_ascii=False),
        ),
    )
    return _require(
        db.fetch_one("SELECT * FROM geo_responses WHERE id = ?", (response_id,)),
        "geo response",
    )


def list_geo_responses(db: Database, geo_run_id: int) -> list[dict]:
    rows = db.fetch_all(
        """
        SELECT r.*, q.question, q.intent, q.probe_type, run.question_set_id
        FROM geo_responses r
        JOIN geo_questions q ON q.id = r.question_id
        JOIN geo_runs run ON run.id = r.geo_run_id
        WHERE r.geo_run_id = ?
        ORDER BY r.platform, q.intent, q.id
        """,
        (geo_run_id,),
    )
    for row in rows:
        row["competitor_mentions"] = json.loads(row["competitor_mentions"] or "[]")
    return rows


def run_geo_batch(
    db: Database, settings: Settings, project_id: int, payload: GeoBatchRunRequest
) -> dict:
    run = create_geo_run(
        db,
        project_id,
        GeoRunCreate(
            question_set_id=payload.question_set_id,
            run_at=payload.run_at,
            status="running",
            notes=payload.notes,
        ),
    )
    questions = list_questions(db, payload.question_set_id)
    saved = 0
    errors: list[dict] = []
    for provider_spec in payload.providers:
        if provider_spec.provider == "openrouter":
            if not settings.openrouter_api_key:
                errors.append(
                    {"platform": provider_spec.platform, "message": "OPENROUTER_API_KEY not configured"}
                )
                continue
            client = OpenRouterClient(
                api_key=settings.openrouter_api_key,
                model=provider_spec.model or "openai/gpt-4.1-mini",
            )
        elif provider_spec.provider == "qianfan":
            if not settings.qianfan_access_key or not settings.qianfan_secret_key:
                errors.append(
                    {"platform": provider_spec.platform, "message": "Qianfan credentials not configured"}
                )
                continue
            client = QianfanClient(
                access_key=settings.qianfan_access_key,
                secret_key=settings.qianfan_secret_key,
            )
        else:
            errors.append(
                {"platform": provider_spec.platform, "message": f"unsupported provider: {provider_spec.provider}"}
            )
            continue

        for question in questions:
            try:
                result = client.query(question["question"])
                create_geo_response(
                    db,
                    run["id"],
                    GeoResponseCreate(
                        question_id=question["id"],
                        platform=provider_spec.platform,
                        model=provider_spec.model,
                        raw_response=result["content"],
                    ),
                )
                saved += 1
            except ProviderError as exc:
                errors.append(
                    {
                        "platform": provider_spec.platform,
                        "question_id": question["id"],
                        "message": str(exc),
                    }
                )
    status = "completed" if saved and not errors else "partial" if saved else "failed"
    db.execute("UPDATE geo_runs SET status = ? WHERE id = ?", (status, run["id"]))
    return {"run_id": run["id"], "status": status, "responses_saved": saved, "errors": errors}


def _latest_geo_summary(db: Database, project_id: int) -> dict:
    run = db.fetch_one(
        "SELECT * FROM geo_runs WHERE project_id = ? ORDER BY run_at DESC, id DESC LIMIT 1",
        (project_id,),
    )
    if not run:
        return {
            "run": None,
            "platforms": [],
            "total": 0,
            "mentioned": 0,
            "mention_rate": None,
            "competitors": [],
        }
    return _geo_run_summary(db, run)


def project_assessment(db: Database, project_id: int) -> dict:
    """Score the newest persisted search and AI observations without inventing data."""
    project = get_project(db, project_id)
    seo = list_seo_data(db, project_id)
    latest_rank_date = seo["rankings"][0]["captured_at"] if seo["rankings"] else None
    latest_rankings = [
        item for item in seo["rankings"] if item["captured_at"] == latest_rank_date
    ]
    seo_breakdown = score_seo(
        SeoInput(
            domain=project["domain"],
            keyword_rankings=[
                KeywordRanking(
                    keyword=item["keyword"], engine=item["engine"], position=item["position"],
                    search_volume=item["search_volume"],
                )
                for item in latest_rankings
            ],
        )
    )
    geo = _latest_geo_summary(db, project_id)
    responses = list_geo_responses(db, geo["run"]["id"]) if geo["run"] else []
    geo_breakdown = score_geo(
        GeoInput(
            brand_name=project["brand_name"], domain=project["domain"],
            mention_results=[
                BrandMentionResult(
                    query=item["question"], engine=item["platform"],
                    brand_mentioned=bool(item["brand_mentioned"]),
                    mention_position=item["mention_position"],
                    cited_as_source=bool(item["cited_source"]),
                )
                for item in responses
            ],
        )
    )
    available = [("SEO", seo_breakdown.score, 0.3), ("GEO", geo_breakdown.score, 0.35)]
    scored = [(score, weight) for _, score, weight in available if score is not None]
    overall = round(sum(score * weight for score, weight in scored) / sum(weight for _, weight in scored), 1) if scored else None
    recommendations: list[dict] = []
    if seo_breakdown.score is None:
        recommendations.append({"dimension": "SEO", "priority": "high", "title": "先完成关键词实测", "description": "录入测试关键词，并按搜索引擎导入或采集最新排名；综合评分不会用缺失数据补分。"})
    elif seo_breakdown.score < 70:
        recommendations.append({"dimension": "SEO", "priority": "high" if seo_breakdown.score < 40 else "medium", "title": "提升重点关键词排名", "description": "优先优化排名靠后且搜索量较高的关键词对应落地页：补足搜索意图内容、标题结构、内链与可抓取性。"})
    if geo_breakdown.score is None:
        recommendations.append({"dimension": "GEO", "priority": "high", "title": "建立 AI 测试问题库", "description": "按认知、比较、决策阶段录入真实提问，并在每个平台保留模型、时间和完整回答。"})
    elif geo_breakdown.score < 70:
        recommendations.append({"dimension": "GEO", "priority": "high" if geo_breakdown.score < 40 else "medium", "title": "提高 AI 回答中的品牌可见度", "description": "围绕未被提及的问题补充可引用的官网事实页、产品对比页、FAQ 与结构化问答；不要用提示词伪造测试结果。"})
    if responses and any(item["accurate"] is False for item in responses):
        recommendations.append({"dimension": "GEO", "priority": "high", "title": "修正 AI 错误信息", "description": "在报告原始回答中定位错误表述，补充官网权威信息和可验证引用，再用相同问题复测。"})
    return {
        "overall_score": overall,
        "scoring_note": "综合分仅按已有实测数据加权：SEO 30%，GEO 35%；缺失维度不补分。",
        "seo": {"score": seo_breakdown.score, "data_complete": seo_breakdown.data_complete, "latest_date": latest_rank_date, "detail": seo_breakdown.detail},
        "geo": {"score": geo_breakdown.score, "data_complete": geo_breakdown.data_complete, "run_at": geo["run"]["run_at"] if geo["run"] else None, "detail": geo_breakdown.detail},
        "recommendations": recommendations,
    }


def _geo_run_summary(db: Database, run: dict) -> dict:
    responses = list_geo_responses(db, run["id"])
    by_platform: dict[str, list[dict]] = defaultdict(list)
    competitor_counts: dict[str, int] = defaultdict(int)
    for item in responses:
        by_platform[item["platform"]].append(item)
        for competitor in item["competitor_mentions"]:
            competitor_counts[competitor] += 1
    platforms = []
    for platform, items in by_platform.items():
        mentioned = sum(item["brand_mentioned"] for item in items)
        accurate_items = [item for item in items if item["accurate"] is not None]
        platforms.append(
            {
                "platform": platform,
                "queries": len(items),
                "mentioned": mentioned,
                "mention_rate": round(mentioned / len(items) * 100, 1) if items else 0,
                "accurate_rate": (
                    round(sum(item["accurate"] for item in accurate_items) / len(accurate_items) * 100, 1)
                    if accurate_items
                    else None
                ),
            }
        )
    mentioned = sum(item["brand_mentioned"] for item in responses)
    return {
        "run": run,
        "platforms": platforms,
        "total": len(responses),
        "mentioned": mentioned,
        "mention_rate": round(mentioned / len(responses) * 100, 1) if responses else None,
        "competitors": [
            {
                "name": name,
                "mentioned": count,
                "mention_rate": round(count / len(responses) * 100, 1) if responses else 0,
            }
            for name, count in sorted(competitor_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def project_dashboard(db: Database, project_id: int) -> dict:
    project = get_project(db, project_id)
    commitments = list_commitments(db, project_id)
    seo_dates = db.fetch_all(
        """
        SELECT captured_at FROM (
            SELECT captured_at FROM seo_metrics WHERE project_id = ?
            UNION
            SELECT captured_at FROM keyword_rankings WHERE project_id = ?
        ) ORDER BY captured_at DESC LIMIT 2
        """,
        (project_id, project_id),
    )
    latest_date = seo_dates[0]["captured_at"] if seo_dates else None
    previous_date = seo_dates[1]["captured_at"] if len(seo_dates) > 1 else None
    latest_metrics = db.fetch_all(
        "SELECT * FROM seo_metrics WHERE project_id = ? AND captured_at = ?",
        (project_id, latest_date),
    ) if latest_date else []
    previous_metrics = db.fetch_all(
        "SELECT * FROM seo_metrics WHERE project_id = ? AND captured_at = ?",
        (project_id, previous_date),
    ) if previous_date else []
    previous_by_key = {item["metric_key"]: item for item in previous_metrics}
    alerts = []
    metric_trends = []
    for item in latest_metrics:
        previous = previous_by_key.get(item["metric_key"])
        change = None
        if previous and previous["value"] != 0:
            change = round((item["value"] - previous["value"]) / abs(previous["value"]) * 100, 1)
            if change <= -abs(project["alert_threshold"]):
                alerts.append(
                    {
                        "type": "seo_decline",
                        "message": f'{item["metric_name"]} 环比下降 {abs(change)}%',
                    }
                )
        metric_trends.append({**item, "previous_value": previous["value"] if previous else None, "change": change})

    geo_runs = db.fetch_all(
        "SELECT * FROM geo_runs WHERE project_id = ? ORDER BY run_at DESC, id DESC LIMIT 2",
        (project_id,),
    )
    geo = _geo_run_summary(db, geo_runs[0]) if geo_runs else _latest_geo_summary(db, project_id)
    previous_geo = _geo_run_summary(db, geo_runs[1]) if len(geo_runs) > 1 else None
    geo_change = None
    if (
        previous_geo
        and previous_geo["mention_rate"] is not None
        and geo["mention_rate"] is not None
    ):
        geo_change = round(geo["mention_rate"] - previous_geo["mention_rate"], 1)
        if geo_change <= -abs(project["alert_threshold"]):
            alerts.append(
                {
                    "type": "geo_decline",
                    "message": f"GEO 品牌提及率较上期下降 {abs(geo_change)} 个百分点",
                }
            )
    geo["previous_mention_rate"] = previous_geo["mention_rate"] if previous_geo else None
    geo["change"] = geo_change
    achieved = sum(item["achievement_status"] == "achieved" for item in commitments)
    assessed = sum(item["achievement_status"] != "pending" for item in commitments)
    return {
        "project": project,
        "commitments": {
            "total": len(commitments),
            "assessed": assessed,
            "achieved": achieved,
            "achievement_rate": round(achieved / assessed * 100, 1) if assessed else None,
        },
        "seo": {
            "latest_date": latest_date,
            "previous_date": previous_date,
            "metrics": metric_trends,
        },
        "geo": geo,
        "alerts": alerts,
        "assessment": project_assessment(db, project_id),
    }


def create_report(db: Database, project_id: int, payload: ReportCreate) -> dict:
    get_project(db, project_id)
    return _insert(db, "reports", {"project_id": project_id, **payload.model_dump()})


def list_reports(db: Database, project_id: int) -> list[dict]:
    return db.fetch_all(
        "SELECT * FROM reports WHERE project_id = ? ORDER BY created_at DESC, id DESC",
        (project_id,),
    )


def _status_label(status: str) -> str:
    return {
        "achieved": "已达成",
        "partial": "部分达成",
        "not_achieved": "未达成",
        "unverifiable": "无法判断",
        "pending": "待核验",
        "draft": "草稿",
        "preview": "实时预览",
        "published": "已发布",
        "reviewed": "已复核",
    }.get(status, status)


def _format_number(value: float | int | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def render_report_html(db: Database, project_id: int, report_id: int | None = None) -> str:
    project = get_project(db, project_id)
    commitments = list_commitments(db, project_id)
    dashboard = project_dashboard(db, project_id)
    assessment = dashboard["assessment"]
    report = (
        _require(db.fetch_one("SELECT * FROM reports WHERE id = ? AND project_id = ?", (report_id, project_id)), "report")
        if report_id
        else {
            "title": "SEO / GEO 服务效果独立第三方测评报告",
            "period_start": project["period_start"],
            "period_end": project["period_end"],
            "executive_summary": "",
            "conclusion": "",
            "recommendations": "",
            "status": "preview",
        }
    )
    seo = list_seo_data(db, project_id)
    latest_rank_date = seo["rankings"][0]["captured_at"] if seo["rankings"] else None
    rankings = [item for item in seo["rankings"] if item["captured_at"] == latest_rank_date]
    geo = dashboard["geo"]
    geo_responses = list_geo_responses(db, geo["run"]["id"]) if geo["run"] else []
    question_set = (
        db.fetch_one(
            "SELECT * FROM geo_question_sets WHERE id = ?",
            (geo["run"]["question_set_id"],),
        )
        if geo["run"]
        else None
    )

    achieved = dashboard["commitments"]["achieved"]
    assessed = dashboard["commitments"]["assessed"]
    achievement_text = f"{achieved}/{assessed}" if assessed else "尚未完成核验"
    summary = report["executive_summary"] or (
        f"本期完成 SEO 关键词与 GEO 平台实测。GEO 最新采样品牌提及率为 "
        f"{geo['mention_rate'] if geo['mention_rate'] is not None else '暂无数据'}%。"
    )
    conclusion = report["conclusion"] or (
        "本报告依据独立数据源和留存的原始回答，呈现网站在搜索引擎和 AI 平台中的实测可见度。"
        "缺失数据不计入评分，也不以演示数据替代真实结果。"
    )
    recommendations = report["recommendations"] or (
        "1. 固定关键词、问题库版本和采样条件，按约定周期复测。\n"
        "2. 优先优化排名靠后但搜索量较高的关键词对应落地页。\n"
        "3. 对品牌错误信息和高意图问题的可见度缺口优先整改。"
    )

    commitment_rows = "".join(
        f"""
        <tr>
          <td>{html.escape(item['category'])}</td>
          <td>{html.escape(item['metric_name'])}</td>
          <td>{html.escape(item['target_operator'])} {_format_number(item['target_value'])} {html.escape(item['unit'])}</td>
          <td>{_format_number(item['actual_value'])}</td>
          <td><span class="status {html.escape(item['achievement_status'])}">{html.escape(_status_label(item['achievement_status']))}</span></td>
          <td>{html.escape(item['evidence_source'] or '待补充')}</td>
        </tr>
        """
        for item in commitments
    ) or '<tr><td colspan="6" class="empty">尚未录入合同承诺</td></tr>'
    ranking_rows = "".join(
        f"""
        <tr>
          <td>{html.escape(item['keyword'])}</td><td>{html.escape(item['category'])}</td>
          <td>{html.escape(item['engine'])}</td><td>{html.escape(item.get('region_name') or '全国')}</td><td>{html.escape(item.get('language') or 'zh-CN')}</td><td>{item['position'] if item['position'] is not None else '100+'}</td>
          <td>{item['search_volume'] if item['search_volume'] is not None else '-'}</td>
          <td>{html.escape(item['source'])}</td>
        </tr>
        """
        for item in rankings[:30]
    ) or '<tr><td colspan="8" class="empty">尚未导入关键词排名</td></tr>'
    geo_rows = "".join(
        f"""
        <tr><td>{html.escape(item['platform'])}</td><td>{item['queries']}</td>
        <td>{item['mention_rate']}%</td>
        <td>{str(item['accurate_rate']) + '%' if item['accurate_rate'] is not None else '待人工复核'}</td></tr>
        """
        for item in geo["platforms"]
    ) or '<tr><td colspan="4" class="empty">尚未创建 GEO 采样结果</td></tr>'
    competitor_rows = "".join(
        f"<tr><td>{html.escape(item['name'])}</td><td>{item['mentioned']}</td><td>{item['mention_rate']}%</td></tr>"
        for item in geo["competitors"]
    ) or '<tr><td colspan="3" class="empty">尚未记录竞品提及</td></tr>'
    metric_rows = "".join(
        f"""
        <tr><td>{html.escape(item['captured_at'])}</td><td>{html.escape(item['metric_name'])}</td>
        <td>{_format_number(item['value'])} {html.escape(item['unit'])}</td>
        <td>{html.escape(item['source'])}</td><td>{html.escape(item['notes'] or '-')}</td></tr>
        """
        for item in seo["metrics"][:100]
    ) or '<tr><td colspan="5" class="empty">尚未录入SEO聚合指标</td></tr>'
    tool_records: dict[tuple[str, str], dict] = {
        ("方法与复核", "SAG独立测评工作台 / 人工复核"): {
            "category": "方法与复核",
            "tool": "SAG独立测评工作台 / 人工复核",
            "purpose": "问题库版本管理、证据留存、人工判定、趋势计算与报告生成",
            "scope": "本报告全流程",
        }
    }
    for item in commitments:
        if item["evidence_source"]:
            key = ("合同核验", item["evidence_source"])
            if key not in tool_records:
                tool_records[key] = {
                    "category": "合同核验",
                    "tool": item["evidence_source"],
                    "purpose": f"核验：{item['metric_name']}",
                    "scope": item["due_date"] or "本报告测评周期",
                }
    for item in seo["metrics"]:
        key = ("SEO指标", item["source"])
        if key not in tool_records:
            tool_records[key] = {
                "category": "SEO指标",
                "tool": item["source"],
                "purpose": "流量、外链或技术指标的独立数据来源",
                "scope": item["captured_at"],
            }
    for item in seo["rankings"]:
        key = ("关键词排名", item["source"])
        if key not in tool_records:
            tool_records[key] = {
                "category": "关键词排名",
                "tool": item["source"],
                "purpose": "关键词排名、搜索量及目标页面核验",
                "scope": item["captured_at"],
            }
    for item in geo_responses:
        tool_name = item["platform"]
        if item["model"]:
            tool_name += f" / {item['model']}"
        key = ("GEO检测", tool_name)
        if key not in tool_records:
            tool_records[key] = {
                "category": "GEO检测",
                "tool": tool_name,
                "purpose": "固定问题库的品牌提及、准确性和竞品测试",
                "scope": geo["run"]["run_at"] if geo["run"] else "-",
            }
    tool_rows = "".join(
        f"<tr><td>{html.escape(item['category'])}</td><td>{html.escape(item['tool'])}</td>"
        f"<td>{html.escape(item['purpose'])}</td><td>{html.escape(item['scope'])}</td></tr>"
        for item in tool_records.values()
    ) or '<tr><td colspan="4" class="empty">尚未记录测评工具或数据来源</td></tr>'
    commitment_evidence = "".join(
        f"""
        <div class="evidence-item">
          <b>{html.escape(item['category'])} · {html.escape(item['metric_name'])}</b>
          <p><strong>合同原文：</strong>{html.escape(item['source_clause'] or '未录入')}</p>
          <p><strong>核验说明：</strong>{html.escape(item['notes'] or '未录入')}</p>
          <p><strong>证据来源：</strong>{html.escape(item['evidence_source'] or '待补充')}</p>
        </div>
        """
        for item in commitments
    ) or '<div class="empty">尚无合同核验依据</div>'
    geo_detail_rows = "".join(
        f"""
        <tr>
          <td>{html.escape(item['intent'])}</td><td>{html.escape(item['question'])}</td>
          <td>{html.escape(item['platform'])}<br><span class="small">{html.escape(item['model'] or '未记录模型')}</span></td>
          <td>{'是' if item['brand_mentioned'] else '否'}</td>
          <td>{item['mention_position'] if item['mention_position'] is not None else '-'}</td>
          <td>{'待复核' if item['accurate'] is None else '准确' if item['accurate'] else '不准确'}</td>
          <td>{'、'.join(html.escape(name) for name in item['competitor_mentions']) or '-'}</td>
          <td>{html.escape(_status_label(item['review_status']))}</td>
        </tr>
        """
        for item in geo_responses
    ) or '<tr><td colspan="8" class="empty">尚无GEO逐问题结果</td></tr>'
    geo_evidence = "".join(
        f"""
        <article class="response">
          <div class="response-head">
            <b>{html.escape(item['platform'])} / {html.escape(item['model'] or '未记录模型')}</b>
            <span>{html.escape(item['intent'])} · {html.escape(_status_label(item['review_status']))}</span>
          </div>
          <p><strong>测试问题：</strong>{html.escape(item['question'])}</p>
          <div class="response-text">{html.escape(item['raw_response'])}</div>
          <div class="response-meta">
            品牌提及：{'是' if item['brand_mentioned'] else '否'}；
            提及位置：{item['mention_position'] if item['mention_position'] is not None else '-'}；
            准确性：{'待复核' if item['accurate'] is None else '准确' if item['accurate'] else '不准确'}；
            进入推荐：{'是' if item['recommended'] else '否'}；
            引用官网：{'是' if item['cited_source'] else '否'}；
            竞品：{'、'.join(html.escape(name) for name in item['competitor_mentions']) or '无'}。
          </div>
          <p><strong>错误/过时信息：</strong>{html.escape(item['misinformation'] or '未发现或未记录')}</p>
          <p><strong>人工复核备注：</strong>{html.escape(item['reviewer_notes'] or '未填写')}</p>
        </article>
        """
        for item in geo_responses
    ) or '<div class="empty">尚无可展示的原始回答</div>'
    reviewed_count = sum(item["review_status"] == "reviewed" for item in geo_responses)
    plan_actions = db.fetch_all(
        """
        SELECT a.priority, a.action, a.acceptance, a.status,
               pb.code AS playbook_code, pv.version AS playbook_version, pb.title AS playbook_title
        FROM plan_actions a
        LEFT JOIN playbook_versions pv ON pv.id = a.playbook_version_id
        LEFT JOIN playbooks pb ON pb.id = pv.playbook_id
        WHERE a.project_id = ?
        ORDER BY a.id
        """,
        (project_id,),
    )
    plan_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['priority'])}</td>"
        f"<td>{html.escape(item['action'])}</td>"
        f"<td>{html.escape((item['playbook_code'] or '自定义') + (' v' + str(item['playbook_version']) if item['playbook_version'] else ''))}</td>"
        f"<td>{html.escape(item['acceptance'] or '')}</td>"
        f"<td>{html.escape(item['status'])}</td>"
        "</tr>"
        for item in plan_actions
    ) or '<tr><td colspan="5" class="empty">尚未引用整改建议</td></tr>'

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(report['title'])}</title>
<style>
@page {{ size: A4; margin: 18mm 16mm; }}
* {{ box-sizing: border-box; }} body {{ margin:0; color:#172033; font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; background:#eef3f7; }}
.report {{ width:210mm; min-height:297mm; margin:24px auto; padding:18mm 16mm; background:white; box-shadow:0 12px 40px #17203320; }}
.cover {{ min-height:240mm; display:flex; flex-direction:column; justify-content:center; border-top:8px solid #167c80; }}
.kicker {{ color:#167c80; font-weight:700; letter-spacing:.16em; }} h1 {{ font-size:34px; line-height:1.2; margin:18px 0; }} h2 {{ color:#167c80; border-bottom:2px solid #dce8e8; padding-bottom:8px; margin-top:34px; }}
.meta {{ margin-top:60px; display:grid; grid-template-columns:110px 1fr; gap:10px; }} .meta b {{ color:#5b6877; }}
.lead {{ border-left:5px solid #ef7c45; background:#fff6ef; padding:18px 20px; font-size:16px; }}
.cards {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:18px 0; }} .card {{ border:1px solid #dce5ea; padding:16px; border-radius:10px; }} .card strong {{ display:block; font-size:24px; color:#167c80; }}
table {{ width:100%; border-collapse:collapse; margin:14px 0 24px; font-size:12px; }} th {{ background:#1d2a39; color:white; text-align:left; }} th,td {{ border:1px solid #d5dde3; padding:8px 9px; vertical-align:top; }} tr:nth-child(even) td {{ background:#f7f9fa; }}
.status {{ font-weight:700; }} .achieved {{ color:#12824c; }} .not_achieved {{ color:#c43b2f; }} .partial {{ color:#b66a00; }} .unverifiable,.pending {{ color:#697586; }}
.empty {{ text-align:center; color:#7a8794; padding:20px; }} .pre {{ white-space:pre-line; }} .page-break {{ margin-top:40px; }} .footer-note,.small {{ color:#667381; font-size:11px; }}
.note {{ background:#edf7f7; border:1px solid #cfe3e3; border-radius:8px; padding:14px 16px; margin:12px 0; }}
.method-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }} .method {{ border:1px solid #dce5ea; border-radius:8px; padding:14px; }} .method h3 {{ margin:0 0 7px; color:#167c80; }}
.evidence-list {{ display:grid; gap:10px; }} .evidence-item {{ border-left:4px solid #167c80; background:#f7f9fa; padding:11px 14px; }} .evidence-item p {{ margin:4px 0; }}
.response {{ border:1px solid #d5dde3; border-radius:9px; padding:14px; margin:12px 0; break-inside:avoid; }} .response-head {{ display:flex; justify-content:space-between; gap:12px; border-bottom:1px solid #e1e7ea; padding-bottom:8px; }}
.response-text {{ white-space:pre-wrap; background:#f6f8f9; border-radius:7px; padding:12px; margin:9px 0; }} .response-meta {{ color:#44535f; font-size:12px; }}
.print-action {{ position:fixed; right:24px; top:24px; border:0; border-radius:9px; padding:11px 16px; background:#167c80; color:white; font-weight:700; cursor:pointer; box-shadow:0 8px 24px #17203330; }}
@media print {{ body {{ background:white; }} .report {{ width:auto; min-height:auto; margin:0; padding:0; box-shadow:none; }} .page-break {{ break-before:page; margin-top:0; }} .no-print {{ display:none; }} .response,.method,.evidence-item {{ break-inside:avoid; }} }}
</style></head><body><button class="print-action no-print" onclick="window.print()">打印 / 导出 PDF</button>
<main class="report">
<section class="cover">
  <div class="kicker">INDEPENDENT SEO / GEO ASSESSMENT</div>
  <h1>{html.escape(report['title'])}</h1>
  <p>围绕网站关键词排名与 AI 回答可见度形成可追溯、可复现的实测结论。</p>
  <div class="meta">
    <b>测评对象</b><span>{html.escape(project['client_name'])}</span>
    <b>品牌 / 官网</b><span>{html.escape(project['brand_name'])} / {html.escape(project['domain'])}</span>
    <b>测评周期</b><span>{html.escape(report['period_start'] or '-')} 至 {html.escape(report['period_end'] or '-')}</span>
    <b>报告状态</b><span>{html.escape(_status_label(report['status']))}</span>
  </div>
</section>
<section class="page-break"><h2>一、执行摘要</h2><div class="lead">{html.escape(summary)}</div>
  <div class="cards"><div class="card"><span>综合可见度评分</span><strong>{_format_number(assessment['overall_score'])}</strong></div>
  <div class="card"><span>SEO 实测评分</span><strong>{_format_number(assessment['seo']['score'])}</strong></div>
  <div class="card"><span>GEO 实测评分</span><strong>{_format_number(assessment['geo']['score'])}</strong></div>
  <div class="card"><span>最新关键词样本</span><strong>{len(rankings)}</strong></div>
  <div class="card"><span>GEO 品牌提及率</span><strong>{str(geo['mention_rate']) + '%' if geo['mention_rate'] is not None else '-'}</strong></div></div>
  <h2>二、测评范围、工具与数据来源</h2>
  <p>本次测评覆盖官网 SEO 表现和品牌 GEO 可见度。每项数据保留来源、采样日期和原始记录；自动识别只作为初判，准确性、竞品排序和错误信息须经人工复核。</p>
  <table><thead><tr><th>测评类别</th><th>工具 / 平台 / 模型</th><th>用途</th><th>采样日期或范围</th></tr></thead><tbody>{tool_rows}</tbody></table>
  <div class="note"><b>数据完整性：</b>本期GEO共保存 {len(geo_responses)} 条原始回答，其中 {reviewed_count} 条已人工复核，{len(geo_responses) - reviewed_count} 条待复核。SEO最新关键词采样日期为 {html.escape(latest_rank_date or '暂无')}，共 {len(rankings)} 条。</div>

  <h2>三、测评方法与计算口径</h2>
  <div class="method-grid">
    <div class="method"><h3>SEO测评</h3><p>按固定搜索引擎、地域、语言、日期和关键词分类记录排名；地域不同的结果不可直接混合比较。流量、外链和技术指标按相同指标编码进行跨期比较。</p></div>
    <div class="method"><h3>GEO测评</h3><p>使用版本化问题库，覆盖认知期、比较期和决策期。问题原文、平台、模型、原始回答、自动初判和人工复核全部留存。</p></div>
    <div class="method"><h3>指标公式</h3><p>品牌提及率 = 品牌被提及回答数 ÷ 有效回答数；准确提及率 = 人工判定准确的回答数 ÷ 已复核回答数；竞品提及率采用相同有效回答总数。</p></div>
  </div>
  <div class="note"><b>独立性声明：</b>测评结论仅依据本报告列明的第三方数据与留存证据；平台不把单次AI回答视为稳定排名，也不把不可归因数据强行计入服务商成果。</div>
  <h3>方法与局限</h3>
  <p>D 类问题会直接点名品牌，只用来检查 AI 的描述是否准确，不能拿来计算自然发现率。K 类问题不点名品牌，提及率、推荐率和首位率只在这类问题上统计。分母只包含成功解析的样本，模拟结果、缺少密钥而跳过的调用、以及证据校验失败的样本会单独列出，不混进比率。推荐和首位必须能在原始回答里找到对应原句，而且同一条回答里只能有一个“唯一第一”。引擎返回的结构化引用才计入来源，正文里的普通链接不算。引用不代表来源正确，也不代表它对排序有因果作用。每题少数几次采样不能当成统计显著的结论。官方 API 打开联网搜索后的结果，和用户在网页或 App 里看到的结果不一定相同；浏览器采集尚未启用，报告里会分开标注通道。</p>

  <h2>四、SEO现状详细测评</h2>
  <h3>SEO 指标详细内容与时间序列</h3>
  <p>除关键词排名外，以下指标用于解释可见度是否转化为流量、页面是否被收录、站外引用是否增长，以及技术体验是否限制抓取和点击。</p>
  <table><thead><tr><th>采样日期</th><th>指标</th><th>数值</th><th>工具 / 数据源</th><th>指标作用与说明</th></tr></thead><tbody>{metric_rows}</tbody></table>
  <h3>最新关键词排名明细</h3><p>最新采样日期：{html.escape(latest_rank_date or '暂无')}。下表保留关键词分类、搜索引擎、地域、语言、排名、搜索量和来源。</p>
  <table><thead><tr><th>关键词</th><th>分类</th><th>引擎</th><th>地域</th><th>语言</th><th>排名</th><th>搜索量</th><th>工具 / 来源</th></tr></thead><tbody>{ranking_rows}</tbody></table>

  <h2>五、GEO现状详细测评</h2>
  <p>问题库：{html.escape(question_set['name'] if question_set else '暂无')}；
  版本：{html.escape(question_set['version'] if question_set else '-')}；
  采样日期：{html.escape(geo['run']['run_at'] if geo['run'] else '-')}；
  采样条件/备注：{html.escape(geo['run']['notes'] if geo['run'] and geo['run']['notes'] else '未记录')}。</p>
  <h3>平台汇总</h3><table><thead><tr><th>AI平台</th><th>测试回答数</th><th>品牌提及率</th><th>准确提及率</th></tr></thead><tbody>{geo_rows}</tbody></table>
  <h3>竞品提及对比</h3><table><thead><tr><th>竞品</th><th>被提及次数</th><th>提及率</th></tr></thead><tbody>{competitor_rows}</tbody></table>
  <h3>逐问题、逐平台判定明细</h3>
  <table><thead><tr><th>意图</th><th>测试问题</th><th>平台 / 模型</th><th>提及</th><th>位置</th><th>准确性</th><th>竞品</th><th>复核</th></tr></thead><tbody>{geo_detail_rows}</tbody></table>

  <h2>六、综合结论与建议</h2><p>{html.escape(conclusion)}</p><div class="pre">{html.escape(recommendations)}</div>
  <h3>改进计划（引用建议库版本）</h3>
  <table><thead><tr><th>优先级</th><th>行动</th><th>来源建议</th><th>验收</th><th>状态</th></tr></thead><tbody>{plan_rows}</tbody></table>
  <p class="small">行动项绑定建议的具体版本。之后升级建议库不会改写已经写进本报告的版本号。</p>
  <h3>基于实测数据的优化建议</h3><div class="evidence-list">{''.join(f"<div class='evidence-item'><b>{html.escape(item['dimension'])} · {html.escape(item['title'])}</b><p>{html.escape(item['description'])}</p></div>" for item in assessment['recommendations']) or '<div class="empty">暂无待优化缺口。</div>'}</div>
  <h2>附录A：GEO原始回答与复核证据</h2>{geo_evidence}
  <h2>附录B：方法论与复现说明</h2><p>问题库按认知、比较、决策意图分层并版本化。同一客户跨期复测使用相同版本、同一平台和尽可能一致的模型及采样条件；如需调整，创建新版本并保留旧版本。原始回答不得被自动判定结果覆盖，人工修正须保留复核状态和备注。</p>
  <p class="footer-note">本报告记录特定时间、关键词、平台与模型下的实测结果，不承诺未来搜索排名或 AI 平台推荐结果。</p>
</section></main></body></html>"""


def _ensure_demo_seo_metrics(db: Database, project_id: int) -> None:
    records = [
        ("GA4", "organic_traffic", "自然搜索会话", 1063, "访问", "衡量自然搜索带来的实际访问量，观察排名变化是否转化为流量。"),
        ("Google Search Console", "impressions", "Google 自然曝光", 18400, "次", "衡量网站在 Google 搜索结果中被展示的次数。"),
        ("Google Search Console", "clicks", "Google 自然点击", 742, "次", "衡量 Google 搜索结果实际带来的点击。"),
        ("Google Search Console", "ctr", "Google 平均点击率", 4.03, "%", "用于判断标题和摘要是否足够吸引目标用户点击。"),
        ("Bing Webmaster Tools", "bing_clicks", "Bing 自然点击", 96, "次", "衡量 Bing 搜索结果带来的访问。"),
        ("百度搜索资源平台", "baidu_indexed", "百度收录页面", 328, "页", "用于判断重要页面是否被百度发现和收录。"),
        ("5118", "top_10_keywords", "百度前十关键词", 18, "个", "衡量核心词进入百度首页的数量。"),
        ("Ahrefs", "referring_domains", "引用域名", 74, "个", "衡量外部独立网站对官网的引用覆盖。"),
        ("Semrush", "organic_keywords", "Google 自然关键词", 146, "个", "衡量 Google 可见关键词的覆盖范围。"),
        ("Screaming Frog", "indexable_pages", "可索引页面", 286, "页", "发现 robots、canonical、状态码等影响抓取和收录的问题。"),
        ("PageSpeed Insights", "performance_score", "移动端性能评分", 72, "分", "衡量页面加载与交互体验，辅助定位技术优化优先级。"),
    ]
    for source, metric_key, metric_name, value, unit, notes in records:
        exists = db.fetch_one(
            "SELECT id FROM seo_metrics WHERE project_id = ? AND metric_key = ? AND captured_at = ?",
            (project_id, metric_key, "2026-06-30"),
        )
        if not exists:
            create_seo_metric(db, project_id, SeoMetricCreate(captured_at="2026-06-30", source=source, metric_key=metric_key, metric_name=metric_name, value=value, unit=unit, notes=notes))


def seed_demo(db: Database) -> dict:
    existing = db.fetch_one("SELECT * FROM clients WHERE domain = ?", ("demo.example.com",))
    if existing:
        projects = list_projects(db, existing["id"])
        _ensure_demo_seo_metrics(db, projects[0]["id"])
        return {"client_id": existing["id"], "project_id": projects[0]["id"], "created": False}
    client = create_client(
        db,
        ClientCreate(
            name="睿驰科技有限公司（演示）",
            brand_name="睿驰科技",
            domain="demo.example.com",
            industry="工业设备",
            contact_name="市场负责人",
        ),
    )
    project = create_project(
        db,
        ProjectCreate(
            client_id=client["id"],
            name="SEO / GEO 网站可见度实测",
            period_start="2026-04-01",
            period_end="2026-06-30",
        ),
    )
    create_competitor(db, project["id"], CompetitorCreate(name="竞品A"))
    create_competitor(db, project["id"], CompetitorCreate(name="竞品B"))
    keywords = [
        ("工业空压机厂家", 16, 1200),
        ("空压机节能改造", 8, 680),
        ("螺杆空压机品牌", 23, 900),
    ]
    engines = ["baidu", "google", "bing", "360", "sogou", "shenma", "yahoo", "yandex", "duckduckgo"]
    for engine_index, engine in enumerate(engines):
        for keyword, position, volume in keywords:
            create_keyword_target(db, project["id"], KeywordTargetCreate(keyword=keyword, engine=engine))
            create_keyword_ranking(db, project["id"], KeywordRankingCreate(captured_at="2026-06-30", source="演示采样（非真实结果）", keyword=keyword, engine=engine, position=min(position + engine_index * 2, 100), search_volume=volume))
    create_seo_metric(db, project["id"], SeoMetricCreate(captured_at="2026-05-31", source="GA4", metric_key="organic_traffic", metric_name="自然搜索会话", value=1000, unit="访问", notes="用于计算自然搜索流量月度趋势。"))
    _ensure_demo_seo_metrics(db, project["id"])
    question_set = create_question_set(
        db, project["id"], QuestionSetCreate(name="工业设备采购问题库", version="v1.0", status="active")
    )
    questions = []
    for intent, text in [
        ("认知期", "国内有哪些值得关注的工业空压机品牌？"),
        ("比较期", "购买75kW螺杆空压机，哪些品牌比较好？"),
        ("决策期", "华东地区有哪些提供节能改造和售后的空压机厂家？"),
    ]:
        questions.append(create_question(db, question_set["id"], GeoQuestionCreate(intent=intent, question=text)))
    run = create_geo_run(
        db,
        project["id"],
        GeoRunCreate(question_set_id=question_set["id"], run_at="2026-06-30", status="completed", notes="演示采样"),
    )
    platforms = [
        ("ChatGPT", "GPT-4.1"), ("Gemini", "Gemini 2.5"), ("Claude", "Claude 4"),
        ("Perplexity", "Sonar"), ("Grok", "Grok 3"), ("DeepSeek", "DeepSeek-V3"),
        ("通义千问", "Qwen"), ("豆包", "Doubao"), ("腾讯元宝", "Hunyuan"),
        ("Kimi", "Moonshot"), ("文心一言", "ERNIE"), ("智谱清言", "GLM"),
    ]
    for platform_index, (platform, model) in enumerate(platforms):
        for question_index, question in enumerate(questions):
            if (platform_index + question_index) % 3 == 0:
                answer = "推荐名单：1. 竞品A；2. 竞品B；3. 睿驰科技。选择时应核对能效、售后与项目案例。"
            elif (platform_index + question_index) % 3 == 1:
                answer = "常见选择包括竞品A和竞品B，睿驰科技也提供相关产品；建议进一步核对具体参数和交付区域。"
            else:
                answer = "可以关注竞品A的区域服务网络。睿驰科技官网 demo.example.com 列出了节能改造与售后服务。"
            response = create_geo_response(db, run["id"], GeoResponseCreate(question_id=question["id"], platform=platform, model=model, raw_response=answer))
            review_geo_response(db, response["id"], GeoResponseReview(brand_mentioned=bool(response["brand_mentioned"]), mention_position=response["mention_position"], accurate=True, recommended=bool(response["recommended"]), competitor_mentions=json.loads(response["competitor_mentions"]), cited_source=bool(response["cited_source"]), reviewer_notes="完整平台覆盖的演示数据，非真实线上采样"))
    return {"client_id": client["id"], "project_id": project["id"], "created": True}
