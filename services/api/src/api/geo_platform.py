"""Internal GEO workflow: project setup, D/K questions, monitoring, playbooks.

Collection reuses the shared answer-provider interface. Missing API keys are
recorded as skipped mocks. Browser collection stays a stub.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta
from urllib.parse import urlparse

from analysis_engine.geo_judge import PARSER_VERSION, judge_answer, parse_json_object

from api.database import Database
from api.mvp_models import (
    BaselineCreate,
    BootstrapRequest,
    ClientCreate,
    CompetitorCreate,
    GeoQuestionCreate,
    GeoQuestionUpdate,
    GeoResponseCreate,
    GeoRunCreate,
    KeyContentCreate,
    OutcomeCreate,
    PlanActionCreate,
    PlaybookCreate,
    PlaybookVersionCreate,
    ProjectCreate,
    ProjectProfileUpdate,
    QuestionSetCreate,
)
from api.mvp_service import (
    _insert,
    _require,
    create_client,
    create_competitor,
    create_geo_response,
    create_geo_run,
    create_project,
    create_question,
    create_question_set,
    get_project,
    list_projects,
    list_questions,
)
from data_collectors.providers.answers import ScrapeResult, build_answer_providers, resolve_provider

PROTOCOL_VERSION = "geo-p0-1"
MAX_SAMPLES = 5

COLLECTION_CATALOG = [
    {"platform": "ChatGPT（API）", "method": "OpenAI Responses API，tools=web_search", "citations": "annotations.url_citation", "third_party": "无", "difficulty": "低", "risk": "低（官方 API）", "cost": "按官方搜索与 token 计费", "phase": "P0", "notes": "API 结果不等于 chatgpt.com 网页结果"},
    {"platform": "ChatGPT 网页", "method": "Playwright + Camoufox 接口（未实现）", "citations": "页面来源卡片", "third_party": "住宅代理、验证码", "difficulty": "高", "risk": "高（服务条款与封号）", "cost": "代理与账号", "phase": "P1", "notes": "当前只保留接口，不启动浏览器"},
    {"platform": "Perplexity", "method": "Agent API + web_search", "citations": "search_results", "third_party": "无", "difficulty": "低", "risk": "低", "cost": "按官方 web_search 与 token 计费", "phase": "P0", "notes": "返回格式变化时只替换抽取器"},
    {"platform": "Gemini", "method": "Gemini API + Google Search grounding", "citations": "groundingChunks / webSearchQueries", "third_party": "无", "difficulty": "低", "risk": "低", "cost": "按官方 grounding 计费", "phase": "P0", "notes": "vertexaisearch 重定向链接按原样保存，不在采集时跟随跳转"},
    {"platform": "Google AI 概览", "method": "无官方 API，浏览器采集接口", "citations": "来源卡片", "third_party": "代理或备选 SERP", "difficulty": "高", "risk": "高", "cost": "未启用", "phase": "P1", "notes": "出现与否都要记录；当前为 stub"},
    {"platform": "Claude", "method": "Anthropic Messages API + web_search", "citations": "web_search_result_location", "third_party": "无", "difficulty": "低", "risk": "低", "cost": "按官方搜索与 token 计费", "phase": "P0", "notes": "与 claude.ai 网页结果分开标注"},
    {"platform": "DeepSeek", "method": "对话 API + 官方搜索接口", "citations": "搜索结果列表", "third_party": "无", "difficulty": "低", "risk": "低", "cost": "按官方成功请求计费", "phase": "P0", "notes": "自行拼接的检索不等于 App 内回答"},
    {"platform": "Kimi", "method": "Kimi / Moonshot API + 搜索接口", "citations": "搜索结果列表", "third_party": "无", "difficulty": "低", "risk": "低", "cost": "按官方搜索计费", "phase": "P0", "notes": "缺少密钥时跳过并记模拟"},
    {"platform": "文心 / 千帆", "method": "复用已有 QianfanClient", "citations": "当前聊天接口不返回结构化引用", "third_party": "无", "difficulty": "低", "risk": "低", "cost": "按千帆计费", "phase": "P0", "notes": "access=api"},
    {"platform": "OpenRouter", "method": "复用已有 OpenRouterClient", "citations": "默认聊天补全，无原生引用", "third_party": "OpenRouter", "difficulty": "低", "risk": "低", "cost": "按路由模型计费", "phase": "P0", "notes": "不能把 OpenRouter 结果说成模型官网的网页结果"},
    {"platform": "Copilot", "method": "浏览器采集接口", "citations": "页面来源", "third_party": "代理", "difficulty": "中高", "risk": "中高", "cost": "未启用", "phase": "P2", "notes": "stub"},
]

_LIBRARY = [
    {
        "code": "PB-004",
        "title": "产品页补 FAQ 结构化数据",
        "category": "结构化数据",
        "industries": "3C / 家电",
        "markets": "全部市场",
        "engines": "Gemini、Google AI 概览",
        "status": "已发布",
        "trigger_condition": "自家域名在结构化引用中的占比低于 5%，且参数类问题提及率偏低",
        "steps": "1. 选出被问到但官网没写清的参数问题\n2. 用客户确认过的事实写 FAQ\n3. 加上 FAQPage 结构化数据\n4. 下一期采集核验官网引用次数",
        "acceptance_metric": "自家域名被引用次数上升，或参数类 K 问题提及率上升",
        "change_note": "首个发布版本",
    },
    {
        "code": "PB-012",
        "title": "向已引用竞品的评测页送测",
        "category": "第三方评测",
        "industries": "3C",
        "markets": "美国、英国",
        "engines": "全部引擎",
        "status": "已发布",
        "trigger_condition": "同一评测页的结构化引用出现竞品、没有出现我方，且相关 K 类问题提及率低于 30%",
        "steps": "1. 从引用缺口里选出评测页\n2. 准备样品、参数和与竞品的差异\n3. 只生成外联草稿，由人发送\n4. 评测上线后把网址纳入下一期复测",
        "acceptance_metric": "相关问题至少有一个引擎提及我方",
        "change_note": "首个发布版本",
    },
    {
        "code": "PB-017",
        "title": "发布我方与主要竞品的对比页",
        "category": "站内内容",
        "industries": "全部行业",
        "markets": "全部市场",
        "engines": "ChatGPT、Perplexity",
        "status": "已发布",
        "trigger_condition": "对比类问题里竞品排在前面，我方没有进入前三位",
        "steps": "1. 只使用已核实的参数\n2. 按场景写对比，不贬低竞品\n3. 发布在自有域名\n4. 用同一条对比问题复测",
        "acceptance_metric": "对比类 K 问题的首位率或提及率上升",
        "change_note": "首个发布版本",
    },
    {
        "code": "PB-021",
        "title": "在高引用社区用官方身份答疑",
        "category": "社区",
        "industries": "3C、SaaS",
        "markets": "美国",
        "engines": "Perplexity、ChatGPT",
        "status": "已发布",
        "trigger_condition": "社区域名引用占比高，且品牌情感样本里出现负面原句",
        "steps": "1. 找出被引用的讨论串\n2. 用官方账号回答可核实的问题\n3. 不删除负面，只补充事实\n4. 下一期看负面占比",
        "acceptance_metric": "D 类问题的负面占比下降",
        "change_note": "首个发布版本",
    },
    {
        "code": "PB-030",
        "title": "放行 AI 爬虫并提供 llms.txt",
        "category": "技术爬虫",
        "industries": "全部",
        "markets": "全部",
        "engines": "ChatGPT、Claude、Perplexity",
        "status": "草稿",
        "trigger_condition": "robots.txt 屏蔽 GPTBot、ClaudeBot 或 PerplexityBot",
        "steps": "1. 核对 robots.txt\n2. 与客户确认哪些路径可以抓取\n3. 增加 llms.txt 指向权威页面",
        "acceptance_metric": "下一期采集中自家页面进入结构化引用",
        "change_note": "草稿，样本不足时不对外宣称效果",
    },
    {
        "code": "PB-002",
        "title": "低质软文铺量",
        "category": "第三方评测",
        "industries": "全部",
        "markets": "全部",
        "engines": "全部",
        "status": "已废弃",
        "trigger_condition": "不建议再触发",
        "steps": "历史做法。新项目不要选用。",
        "acceptance_metric": "无",
        "change_note": "已废弃：和引用质量对不上",
    },
]


def provider_env_from_settings(settings) -> dict[str, str]:
    return {
        "OPENAI_API_KEY": settings.openai_api_key,
        "PERPLEXITY_API_KEY": settings.perplexity_api_key,
        "GEMINI_API_KEY": settings.gemini_api_key,
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        "DEEPSEEK_API_KEY": settings.deepseek_api_key,
        "KIMI_API_KEY": settings.kimi_api_key,
        "OPENROUTER_API_KEY": settings.openrouter_api_key,
        "QIANFAN_ACCESS_KEY": settings.qianfan_access_key,
        "QIANFAN_SECRET_KEY": settings.qianfan_secret_key,
    }


def collection_catalog() -> list[dict]:
    return list(COLLECTION_CATALOG)


def _split_terms(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,，、;；\n]", value or "") if part.strip()]


def _host(value: str) -> str:
    raw = (value or "").strip().lower()
    if "://" not in raw:
        raw = "https://" + raw
    host = (urlparse(raw).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _contains_brand(text: str, aliases: list[str]) -> bool:
    folded = text.casefold()
    return any(alias.casefold() in folded for alias in aliases if len(alias.strip()) >= 2)


def _brand_aliases(project: dict) -> list[str]:
    aliases = [project.get("brand_name") or ""]
    aliases.extend(_split_terms(project.get("aliases") or ""))
    domain = _host(project.get("domain") or "")
    if domain:
        aliases.append(domain)
    seen: list[str] = []
    for alias in aliases:
        if alias and alias.casefold() not in {item.casefold() for item in seen}:
            seen.append(alias)
    return seen


def compute_config_hash(snapshot: dict) -> str:
    blob = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def draft_questions(profile: dict, llm_items: list[dict] | None = None) -> list[dict]:
    """Build an editable D/K question list. K questions never name the brand."""
    if llm_items:
        cleaned = _normalize_drafts(profile, llm_items)
        if cleaned and any(item["probe_type"] == "D" for item in cleaned) and any(item["probe_type"] == "K" for item in cleaned):
            return cleaned[:12]
    return _template_questions(profile)


def _normalize_drafts(profile: dict, items: list[dict]) -> list[dict]:
    aliases = [profile.get("brand_name") or "", *list(profile.get("aliases") or [])]
    language = profile.get("language") or "zh-CN"
    cleaned = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question or question.casefold() in seen:
            continue
        seen.add(question.casefold())
        probe = item.get("probe_type") if item.get("probe_type") in {"D", "K"} else "K"
        if _contains_brand(question, aliases):
            probe = "D"
        intent = str(item.get("intent") or ("品牌" if probe == "D" else "发现"))
        cleaned.append(
            {
                "probe_type": probe,
                "intent": intent,
                "language": str(item.get("language") or language),
                "question": question,
                "rationale": str(item.get("rationale") or "模型生成，发布前可改"),
                "weight": 1,
            }
        )
    return cleaned


def _template_questions(profile: dict) -> list[dict]:
    brand = profile.get("brand_name") or "该品牌"
    aliases = [brand, *list(profile.get("aliases") or [])]
    language = profile.get("language") or "zh-CN"
    chinese = language.lower().startswith("zh")
    products = list(profile.get("products") or []) or ["这类产品"]
    points = list(profile.get("selling_points") or [])
    competitors = list(profile.get("competitors") or []) or ["主要竞品"]
    drafts: list[dict] = []

    def add(probe: str, intent: str, question: str, rationale: str) -> None:
        if probe == "K" and _contains_brand(question, aliases):
            return
        if any(item["question"] == question for item in drafts):
            return
        drafts.append(
            {
                "probe_type": probe,
                "intent": intent,
                "language": "zh-CN" if chinese else "en-US",
                "question": question,
                "rationale": rationale,
                "weight": 1,
            }
        )

    product = products[0]
    competitor = competitors[0]
    if chinese:
        add("D", "品牌", f"{brand} 是什么品牌，值得信任吗？", "D 类模板：品牌认知")
        add("D", "品牌", f"{brand} 的{product}有哪些优缺点？", "D 类模板：产品评价")
        add("K", "发现", f"最好的{product}有哪些推荐？", f"来自产品：{product}")
        if points:
            add("K", "发现", f"注重「{points[0]}」时，{product}怎么选？", f"来自卖点：{points[0]}")
        add("K", "替代", f"{competitor} 的替代品牌有哪些？", f"来自竞品：{competitor}")
        add("K", "对比", f"{competitor} 和同价位品牌怎么选？", f"来自竞品：{competitor}")
        add("K", "使用场景", f"家用或办公场景下怎么选{product}？", f"来自产品：{product}")
        if len(products) > 1:
            add("K", "发现", f"最好的{products[1]}有哪些推荐？", f"来自产品：{products[1]}")
    else:
        add("D", "品牌", f"Is {brand} a trustworthy brand?", "D-type template: brand trust")
        add("D", "品牌", f"What are the pros and cons of {brand} {product}?", "D-type template: product review")
        add("K", "发现", f"What is the best {product} to buy?", f"From product: {product}")
        if points:
            add("K", "发现", f"Which {product} is best for {points[0]}?", f"From selling point: {points[0]}")
        add("K", "替代", f"What are good alternatives to {competitor}?", f"From competitor: {competitor}")
        add("K", "对比", f"How should I compare {competitor} with similar brands?", f"From competitor: {competitor}")
        add("K", "使用场景", f"How do I choose a {product} for home or office use?", f"From product: {product}")
    if not any(item["probe_type"] == "K" for item in drafts):
        neutral = "这类产品怎么选？" if chinese else "How should buyers compare options in this category?"
        add("K", "发现", neutral, "中性品类问题")
    return drafts[:12]


def _profile_for_project(db: Database, project_id: int) -> dict:
    project = get_project(db, project_id)
    contents = list_key_contents(db, project_id)
    products = [item["title"] for item in contents if item["kind"] in {"产品线", "产品"}]
    points = [item["title"] if not item["body"] else f"{item['title']}：{item['body']}" for item in contents if item["kind"] == "卖点"]
    for item in contents:
        if item["kind"] == "参数" and item["title"]:
            points.append(item["title"])
    return {
        "brand_name": project["brand_name"],
        "aliases": _brand_aliases(project),
        "domain": project["domain"],
        "language": project.get("language") or "zh-CN",
        "products": products,
        "selling_points": points,
        "competitors": [item["name"] for item in project["competitors"]],
    }


def ensure_playbook_library(db: Database) -> None:
    for item in _LIBRARY:
        existing = db.fetch_one("SELECT * FROM playbooks WHERE code = ?", (item["code"],))
        if existing is None:
            playbook = _insert(
                db,
                "playbooks",
                {
                    "code": item["code"],
                    "title": item["title"],
                    "category": item["category"],
                    "industries": item["industries"],
                    "markets": item["markets"],
                    "engines": item["engines"],
                    "status": item["status"],
                },
            )
            playbook_id = playbook["id"]
        else:
            playbook_id = existing["id"]
        version = db.fetch_one(
            "SELECT id FROM playbook_versions WHERE playbook_id = ? ORDER BY version DESC LIMIT 1",
            (playbook_id,),
        )
        if version is None:
            _insert(
                db,
                "playbook_versions",
                {
                    "playbook_id": playbook_id,
                    "version": 1,
                    "trigger_condition": item["trigger_condition"],
                    "steps": item["steps"],
                    "acceptance_metric": item["acceptance_metric"],
                    "status": item["status"],
                    "change_note": item["change_note"],
                },
            )


def list_portfolio(db: Database) -> dict:
    ensure_playbook_library(db)
    projects = list_projects(db)
    rows = []
    for project in projects:
        visibility = project_visibility(db, project["id"])
        schedule = db.fetch_one(
            "SELECT * FROM geo_schedules WHERE project_id = ? ORDER BY id DESC LIMIT 1",
            (project["id"],),
        )
        rate = visibility["k"]["mention_rate"]
        if rate is None and visibility["run"] is not None:
            rate = visibility.get("legacy_mention_rate")
        rows.append(
            {
                "project_id": project["id"],
                "client_name": project["client_name"],
                "brand_name": project["brand_name"],
                "project_name": project["name"],
                "industry": project.get("industry") or "",
                "delivery_status": project.get("delivery_status") or "试用",
                "delivery_stage": project.get("delivery_stage") or "诊断报告",
                "mention_rate": rate,
                "next_run_at": schedule["next_run_at"] if schedule else None,
                "config_hash": visibility.get("config_hash"),
            }
        )
    month = date.today().strftime("%Y-%m")
    attempt_count = db.fetch_one(
        "SELECT COUNT(*) AS n FROM geo_attempts WHERE created_at LIKE ?",
        (f"{month}%",),
    )
    pending = db.fetch_one(
        "SELECT COUNT(*) AS n FROM geo_responses WHERE review_status != 'reviewed'"
    )
    spend = db.fetch_one(
        "SELECT COALESCE(SUM(COALESCE(actual_cost_usd, est_cost_usd, 0)), 0) AS n FROM budget_ledger WHERE created_at LIKE ?",
        (f"{month}%",),
    )
    return {
        "kpis": {
            "clients": len({row["client_name"] for row in rows}),
            "projects": len(rows),
            "attempts_this_month": int(attempt_count["n"] if attempt_count else 0),
            "pending_reviews": int(pending["n"] if pending else 0),
            "spend_usd": round(float(spend["n"] if spend else 0), 2),
        },
        "projects": rows,
    }


def bootstrap_project(db: Database, payload: BootstrapRequest) -> dict:
    client = create_client(
        db,
        ClientCreate(
            name=payload.client_name,
            brand_name=payload.brand_name,
            domain=payload.domain,
            industry=payload.industry,
        ),
    )
    project = create_project(
        db,
        ProjectCreate(
            client_id=client["id"],
            name=payload.project_name or f"{payload.brand_name} GEO 监测",
            cadence=payload.cadence,
        ),
    )
    update_profile(
        db,
        project["id"],
        ProjectProfileUpdate(
            delivery_stage=payload.delivery_stage,
            delivery_status=payload.delivery_status,
            language=payload.language,
            region=payload.region,
            aliases=payload.aliases,
            monthly_budget_usd=payload.monthly_budget_usd,
            cadence=payload.cadence,
        ),
    )
    for raw in payload.competitors:
        name, _, domain = raw.partition("|")
        create_competitor(db, project["id"], CompetitorCreate(name=name.strip(), domain=domain.strip()))
    for content in payload.key_contents:
        add_key_content(db, project["id"], content)
    return get_project(db, project["id"])


def update_profile(db: Database, project_id: int, payload: ProjectProfileUpdate) -> dict:
    get_project(db, project_id)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return get_project(db, project_id)
    assignments = ", ".join(f"{key} = ?" for key in values)
    db.execute(
        f"UPDATE projects SET {assignments} WHERE id = ?",
        (*values.values(), project_id),
    )
    return get_project(db, project_id)


def add_key_content(db: Database, project_id: int, payload: KeyContentCreate) -> dict:
    get_project(db, project_id)
    values = payload.model_dump()
    values["confirmed"] = int(bool(values["confirmed"]))
    return _insert(db, "project_key_contents", {"project_id": project_id, **values})


def list_key_contents(db: Database, project_id: int) -> list[dict]:
    get_project(db, project_id)
    return db.fetch_all(
        "SELECT * FROM project_key_contents WHERE project_id = ? ORDER BY id",
        (project_id,),
    )


def _question_items_from_llm(text: str) -> list[dict]:
    obj = parse_json_object(text)
    if obj and isinstance(obj.get("questions"), list):
        return obj["questions"]
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def generate_questions_for_project(db: Database, project_id: int, name: str = "自动问题库", llm_complete=None) -> dict:
    profile = _profile_for_project(db, project_id)
    llm_items = None
    if llm_complete is not None:
        prompt = (
            "你是 GEO 问题库编辑。只输出 JSON 对象，键为 questions，数组元素包含 "
            "probe_type（D 或 K）、intent（发现、替代、对比、品牌、使用场景）、language、question、rationale。"
            "D 类必须点名品牌，用来检查描述是否准确。K 类是中性品类问题，正文不能出现品牌名、别名或域名。"
            f"品牌={profile['brand_name']}；别名={profile['aliases']}；产品={profile['products']}；"
            f"卖点={profile['selling_points']}；竞品={profile['competitors']}；语言={profile['language']}。"
        )
        try:
            llm_items = _question_items_from_llm(llm_complete(prompt))
        except Exception:
            llm_items = None
    drafts = draft_questions(profile, llm_items)
    existing = db.fetch_all("SELECT version FROM geo_question_sets WHERE project_id = ?", (project_id,))
    version = f"v{len(existing) + 1}"
    question_set = create_question_set(
        db,
        project_id,
        QuestionSetCreate(name=name, version=version, status="draft"),
    )
    saved = [
        create_question(
            db,
            question_set["id"],
            GeoQuestionCreate(
                intent=item["intent"],
                question=item["question"],
                weight=item["weight"],
                probe_type=item["probe_type"],
                language=item["language"],
                rationale=item["rationale"],
            ),
        )
        for item in drafts
    ]
    return {"question_set": question_set, "questions": saved, "source": "llm" if llm_items else "template"}


def update_question(db: Database, question_id: int, payload: GeoQuestionUpdate) -> dict:
    row = _require(db.fetch_one("SELECT * FROM geo_questions WHERE id = ?", (question_id,)), "question")
    question_set = _require(
        db.fetch_one("SELECT * FROM geo_question_sets WHERE id = ?", (row["question_set_id"],)),
        "question set",
    )
    project = get_project(db, question_set["project_id"])
    if payload.probe_type not in {"D", "K"}:
        raise ValueError("probe_type 只能是 D 或 K")
    if payload.probe_type == "K" and _contains_brand(payload.question, _brand_aliases(project)):
        raise ValueError("K 类问题不能点名品牌或域名，请改为 D 类或改写成中性问法")
    values = payload.model_dump()
    assignments = ", ".join(f"{key} = ?" for key in values)
    db.execute(f"UPDATE geo_questions SET {assignments} WHERE id = ?", (*values.values(), question_id))
    return _require(db.fetch_one("SELECT * FROM geo_questions WHERE id = ?", (question_id,)), "question")


def delete_question(db: Database, question_id: int) -> dict:
    _require(db.fetch_one("SELECT id FROM geo_questions WHERE id = ?", (question_id,)), "question")
    db.execute("DELETE FROM geo_questions WHERE id = ?", (question_id,))
    return {"ok": True, "id": question_id}


def create_baseline(db: Database, project_id: int, payload: BaselineCreate) -> dict:
    project = get_project(db, project_id)
    question_set = _require(
        db.fetch_one("SELECT * FROM geo_question_sets WHERE id = ?", (payload.question_set_id,)),
        "question set",
    )
    if question_set["project_id"] != project_id:
        raise ValueError("question set does not belong to project")
    if not payload.engines:
        raise ValueError("至少选择一个引擎")
    if payload.sample_count < 1 or payload.sample_count > MAX_SAMPLES:
        raise ValueError(f"采样次数需在 1 到 {MAX_SAMPLES} 之间")
    questions = list_questions(db, payload.question_set_id)
    if not questions:
        raise ValueError("问题库是空的")
    snapshot = {
        "protocol_version": PROTOCOL_VERSION,
        "parser_version": PARSER_VERSION,
        "question_set_id": payload.question_set_id,
        "questions": [
            {
                "id": item["id"],
                "probe_type": item.get("probe_type") or "K",
                "intent": item["intent"],
                "question": item["question"],
                "language": item.get("language") or payload.language,
                "weight": item["weight"],
            }
            for item in questions
        ],
        "engines": sorted(payload.engines),
        "language": payload.language,
        "region": payload.region,
        "sample_count": payload.sample_count,
        "aliases": sorted(_brand_aliases(project)),
        "competitors": sorted(item["name"] for item in project["competitors"]),
    }
    config_hash = compute_config_hash(snapshot)
    return _insert(
        db,
        "geo_baselines",
        {
            "project_id": project_id,
            "question_set_id": payload.question_set_id,
            "engines_json": json.dumps(payload.engines, ensure_ascii=False),
            "language": payload.language,
            "region": payload.region,
            "sample_count": payload.sample_count,
            "protocol_version": PROTOCOL_VERSION,
            "parser_version": PARSER_VERSION,
            "config_hash": config_hash,
            "snapshot_json": json.dumps(snapshot, ensure_ascii=False),
        },
    )


def list_baselines(db: Database, project_id: int) -> list[dict]:
    get_project(db, project_id)
    return db.fetch_all(
        "SELECT * FROM geo_baselines WHERE project_id = ? ORDER BY id DESC",
        (project_id,),
    )


def fields_from_judge(brand_name: str, aliases: list[str], judged: dict) -> dict:
    names = [brand_name, *aliases]
    entities = list(judged.get("entities") or [])
    brand = next(
        (
            entity
            for entity in entities
            if entity.get("role") == "brand" or entity.get("name", "").casefold() in {name.casefold() for name in names if name}
        ),
        None,
    )
    mentioned = bool(brand and brand.get("counts_as_mention"))
    position = None
    if mentioned and brand.get("counts_as_first"):
        position = 1
    elif mentioned:
        ordered = [entity for entity in entities if entity.get("counts_as_mention")]
        ordered.sort(key=lambda entity: entity.get("first_mention_offset") if isinstance(entity.get("first_mention_offset"), int) else 10**9)
        for index, entity in enumerate(ordered, start=1):
            if entity.get("name") == brand.get("name"):
                position = index
                break
    competitors = []
    for entity in entities:
        if entity.get("counts_as_mention") and entity.get("role") == "competitor":
            competitors.append(entity.get("name"))
    return {
        "brand_mentioned": mentioned,
        "mention_position": position,
        "recommended": bool(mentioned and brand and brand.get("recommendation") == "positive"),
        "competitor_mentions": [name for name in competitors if name],
        "sample_state": judged.get("sample_state") or "unresolved",
    }


def _citation_category(domain: str, own: str, competitor_domains: set[str]) -> str:
    if own and (domain == own or domain.endswith("." + own)):
        return "own"
    if domain in competitor_domains or any(domain.endswith("." + item) for item in competitor_domains if item):
        return "competitor"
    return "other"


def _judge_subjects(project: dict) -> list[dict]:
    subjects = [{"name": project["brand_name"], "role": "brand", "aliases": _brand_aliases(project)}]
    for competitor in project["competitors"]:
        subjects.append({"name": competitor["name"], "role": "competitor", "aliases": []})
    return subjects


def start_monitoring(db: Database, project_id: int, baseline_id: int, *, env: dict, http_client=None, llm_complete=None) -> dict:
    project = get_project(db, project_id)
    baseline = _require(db.fetch_one("SELECT * FROM geo_baselines WHERE id = ?", (baseline_id,)), "baseline")
    if baseline["project_id"] != project_id:
        raise ValueError("baseline does not belong to project")
    engines = json.loads(baseline["engines_json"])
    questions = list_questions(db, baseline["question_set_id"])
    sample_count = int(baseline["sample_count"] or 1)
    run = create_geo_run(
        db,
        project_id,
        GeoRunCreate(
            question_set_id=baseline["question_set_id"],
            run_at=date.today().isoformat(),
            status="running",
            notes="P0 官方 API 采集。缺少密钥的通道记为模拟，不计入有效样本。",
        ),
    )
    db.execute(
        "UPDATE geo_runs SET baseline_id = ?, sample_count = ? WHERE id = ?",
        (baseline_id, sample_count, run["id"]),
    )
    db.execute(
        "UPDATE geo_question_sets SET status = 'active' WHERE id = ?",
        (baseline["question_set_id"],),
    )
    providers = build_answer_providers(env, http_client)
    own = _host(project["domain"])
    competitor_domains = {_host(item["domain"]) for item in project["competitors"] if item.get("domain")}
    saved = 0
    errors: list[dict] = []
    for question in questions:
        for engine in engines:
            provider = resolve_provider(providers, engine)
            for sample_index in range(sample_count):
                if provider is None:
                    result = ScrapeResult(
                        provider_id="unknown",
                        engine=engine,
                        access="api",
                        status="skipped",
                        error_code="unsupported_engine",
                        text="",
                    )
                else:
                    result = provider.run(
                        engine,
                        question["question"],
                        country=baseline["region"],
                        language=baseline["language"],
                        web_search=True,
                    )
                raw_json = json.dumps(result.raw_output, ensure_ascii=False, sort_keys=True, default=str)
                digest = hashlib.sha256((raw_json + "\n" + result.text).encode()).hexdigest()
                attempt = _insert(
                    db,
                    "geo_attempts",
                    {
                        "response_id": None,
                        "geo_run_id": run["id"],
                        "question_id": question["id"],
                        "platform": engine,
                        "provider_id": result.provider_id,
                        "engine": engine,
                        "attempt_no": 1,
                        "sample_index": sample_index,
                        "status": result.status,
                        "error_code": result.error_code,
                        "access": result.access,
                        "request_params_json": json.dumps(
                            {
                                "engine": engine,
                                "provider": result.provider_id,
                                "model": result.model_version,
                                "country": baseline["region"],
                                "language": baseline["language"],
                                "web_search": True,
                                "sample_index": sample_index,
                            },
                            ensure_ascii=False,
                        ),
                        "raw_response": result.text,
                        "raw_payload_json": raw_json,
                        "payload_sha256": digest,
                        "web_queries_json": json.dumps(result.web_queries, ensure_ascii=False),
                        "model_version": result.model_version or "",
                        "config_hash": baseline["config_hash"],
                        "cost_usd": result.cost_usd,
                    },
                )
                if result.status != "ok" and not result.text:
                    errors.append({"engine": engine, "question_id": question["id"], "error_code": result.error_code})
                    continue
                citations = []
                own_cited = False
                for citation in result.citations:
                    if citation.get("source_kind") != "provider_citation":
                        continue
                    category = _citation_category(citation.get("domain") or "", own, competitor_domains)
                    if category == "own":
                        own_cited = True
                    citations.append((citation, category))
                if result.access == "api" and result.status == "ok":
                    judged = judge_answer(result.text, _judge_subjects(project), None)
                    if llm_complete is not None:
                        try:
                            raw = llm_complete(_judge_prompt(result.text, _judge_subjects(project)))
                            parsed = parse_json_object(raw or "")
                            if parsed:
                                judged = judge_answer(result.text, _judge_subjects(project), parsed)
                        except Exception:
                            pass
                else:
                    judged = {
                        "parser_version": PARSER_VERSION,
                        "sample_state": "unresolved",
                        "entities": [],
                        "counts_for_first_position": False,
                        "reviewer": "skipped",
                        "reason": result.error_code or result.status,
                    }
                derived = fields_from_judge(project["brand_name"], _brand_aliases(project), judged)
                response = create_geo_response(
                    db,
                    run["id"],
                    GeoResponseCreate(
                        question_id=question["id"],
                        platform=engine,
                        model=result.model_version or result.provider_id,
                        raw_response=result.text,
                        sample_index=sample_index,
                        brand_mentioned=derived["brand_mentioned"],
                        mention_position=derived["mention_position"],
                        recommended=derived["recommended"],
                        competitor_mentions=derived["competitor_mentions"],
                        cited_source=own_cited,
                    ),
                )
                # create_geo_response treats recommended=False as "use the string heuristic".
                db.execute(
                    """
                    UPDATE geo_responses
                    SET brand_mentioned = ?, mention_position = ?, recommended = ?,
                        competitor_mentions = ?, cited_source = ?
                    WHERE id = ?
                    """,
                    (
                        int(derived["brand_mentioned"]),
                        derived["mention_position"],
                        int(derived["recommended"]),
                        json.dumps(derived["competitor_mentions"], ensure_ascii=False),
                        int(own_cited),
                        response["id"],
                    ),
                )
                db.execute(
                    "UPDATE geo_attempts SET response_id = ? WHERE id = ?",
                    (response["id"], attempt["id"]),
                )
                for citation, category in citations:
                    _insert(
                        db,
                        "geo_citations",
                        {
                            "attempt_id": attempt["id"],
                            "url": citation.get("url") or "",
                            "domain": citation.get("domain") or "",
                            "title": citation.get("title") or "",
                            "position": citation.get("position"),
                            "source_kind": "provider_citation",
                            "payload_path": citation.get("payload_path") or "",
                            "category": category,
                        },
                    )
                _insert(
                    db,
                    "geo_analysis_revisions",
                    {
                        "attempt_id": attempt["id"],
                        "response_id": response["id"],
                        "parser_version": PARSER_VERSION,
                        "reviewer": judged.get("reviewer") or "heuristic",
                        "result_json": json.dumps(judged, ensure_ascii=False),
                        "valid": int(judged.get("sample_state") != "unresolved"),
                    },
                )
                saved += 1
                if result.status != "ok":
                    errors.append({"engine": engine, "question_id": question["id"], "error_code": result.error_code or result.status})
    real_ok = db.fetch_one(
        "SELECT COUNT(*) AS n FROM geo_attempts WHERE geo_run_id = ? AND status = 'ok' AND access = 'api'",
        (run["id"],),
    )
    skipped = db.fetch_one(
        "SELECT COUNT(*) AS n FROM geo_attempts WHERE geo_run_id = ? AND status != 'ok'",
        (run["id"],),
    )
    ok_count = int(real_ok["n"] if real_ok else 0)
    skip_count = int(skipped["n"] if skipped else 0)
    if ok_count and not skip_count:
        status = "completed"
    elif ok_count:
        status = "partial"
    elif saved:
        status = "degraded"
    else:
        status = "skipped"
    db.execute("UPDATE geo_runs SET status = ? WHERE id = ?", (status, run["id"]))
    days = 30 if (project.get("cadence") or "monthly") == "monthly" else 7
    next_run = (date.today() + timedelta(days=days)).isoformat()
    _insert(
        db,
        "geo_schedules",
        {
            "project_id": project_id,
            "baseline_id": baseline_id,
            "cron": project.get("cadence") or "monthly",
            "next_run_at": next_run,
            "status": "active",
            "monthly_budget_usd": project.get("monthly_budget_usd"),
        },
    )
    _insert(
        db,
        "budget_ledger",
        {
            "project_id": project_id,
            "geo_run_id": run["id"],
            "kind": "api_estimate",
            "est_cost_usd": 0 if ok_count == 0 else round(ok_count * 0.01, 4),
            "actual_cost_usd": 0 if ok_count == 0 else None,
            "note": "缺少密钥或浏览器 stub 的调用不产生费用。有真实调用时金额只是粗估。",
        },
    )
    return {
        "run_id": run["id"],
        "status": status,
        "responses_saved": saved,
        "config_hash": baseline["config_hash"],
        "errors": errors,
        "next_run_at": next_run,
    }


def _judge_prompt(raw_text: str, subjects: list[dict]) -> str:
    names = ", ".join(f"{item['name']}（{item['role']}）" for item in subjects)
    return (
        "判断下面这篇 AI 回答里列出的对象。只输出 JSON 对象，键 entities 是数组。"
        "每个元素包含 name、role、recommendation（positive/negative/mentioned/uncertain）、"
        "mention_quote、recommendation_quote、first_mention_state（unique/tied/none/unresolved）、sentiment。"
        "引用必须是回答中的原句。只有回答给出明确的第一名时，才能把一个对象标成 unique，且最多一个。"
        f"对象：{names}\n回答：\n{raw_text[:6000]}"
    )


def _empty_visibility(project: dict) -> dict:
    return {
        "project_id": project["id"],
        "project_name": project["name"],
        "brand_name": project["brand_name"],
        "client_name": project.get("client_name"),
        "run": None,
        "config_hash": None,
        "comparable": False,
        "compare_note": "尚无采集",
        "n_total": 0,
        "n_valid": 0,
        "n_excluded": 0,
        "n_mock": 0,
        "k": {"n_valid": 0, "mention_rate": None, "recommend_rate": None, "first_rate": None, "share": None},
        "d": {"n_valid": 0, "mention_rate": None, "note": "D 类直接点名品牌，不能当作自然发现率"},
        "share": [],
        "matrix": [],
        "engines": [],
        "sentiment": [],
        "previous_mention_rate": None,
        "mention_rate_change": None,
        "legacy_mention_rate": None,
    }


def _revision_state(revision: dict | None) -> str:
    if not revision:
        return "ok"
    if revision.get("reviewer") == "human":
        return "ok"
    try:
        payload = json.loads(revision["result_json"] or "{}")
    except json.JSONDecodeError:
        return "unresolved"
    return payload.get("sample_state") or "ok"


def _summarize_run(db: Database, project: dict, run: dict) -> dict:
    attempts = db.fetch_all("SELECT * FROM geo_attempts WHERE geo_run_id = ? ORDER BY id", (run["id"],))
    responses = db.fetch_all(
        """
        SELECT r.*, q.question, q.intent, q.probe_type
        FROM geo_responses r
        JOIN geo_questions q ON q.id = r.question_id
        WHERE r.geo_run_id = ?
        ORDER BY r.id
        """,
        (run["id"],),
    )
    revisions = db.fetch_all(
        """
        SELECT * FROM geo_analysis_revisions
        WHERE response_id IN (SELECT id FROM geo_responses WHERE geo_run_id = ?)
           OR attempt_id IN (SELECT id FROM geo_attempts WHERE geo_run_id = ?)
        ORDER BY id
        """,
        (run["id"], run["id"]),
    )
    by_attempt: dict[int, dict] = {}
    by_response: dict[int, dict] = {}
    for revision in revisions:
        if revision["attempt_id"]:
            by_attempt[revision["attempt_id"]] = revision
        if revision["response_id"]:
            by_response[revision["response_id"]] = revision
    response_by_id = {item["id"]: item for item in responses}
    question_by_id = {
        item["id"]: item
        for item in db.fetch_all(
            "SELECT * FROM geo_questions WHERE question_set_id = ?",
            (run["question_set_id"],),
        )
    }
    baseline = None
    if run.get("baseline_id"):
        baseline = db.fetch_one("SELECT * FROM geo_baselines WHERE id = ?", (run["baseline_id"],))
    summary = _empty_visibility(project)
    summary["run"] = {"id": run["id"], "run_at": run["run_at"], "status": run["status"], "notes": run["notes"]}
    summary["config_hash"] = baseline["config_hash"] if baseline else None
    if not attempts:
        return _legacy_summary(summary, responses)
    engines: list[str] = []
    matrix: dict[int, dict] = {}
    share_counts: dict[str, int] = {}
    k_flags: list[dict] = []
    d_flags: list[dict] = []
    sentiment = []
    for attempt in attempts:
        if attempt["engine"] not in engines:
            engines.append(attempt["engine"])
        revision = by_attempt.get(attempt["id"]) or by_response.get(attempt["response_id"])
        state = _revision_state(revision)
        is_mock = attempt["access"] in {"mock", "scraped"} or attempt["status"] == "skipped" or attempt["error_code"] == "missing_api_key"
        is_valid = attempt["status"] == "ok" and attempt["access"] == "api" and state != "unresolved"
        summary["n_total"] += 1
        if is_mock:
            summary["n_mock"] += 1
        if is_valid:
            summary["n_valid"] += 1
        else:
            summary["n_excluded"] += 1
        response = response_by_id.get(attempt["response_id"])
        question = question_by_id.get(attempt["question_id"], {})
        probe = question.get("probe_type") or (response or {}).get("probe_type") or "K"
        bucket = matrix.setdefault(
            attempt["question_id"],
            {
                "question_id": attempt["question_id"],
                "question": question.get("question") or (response or {}).get("question") or "",
                "probe_type": probe,
                "intent": question.get("intent") or (response or {}).get("intent") or "",
                "cells": {},
            },
        )
        cell = bucket["cells"].setdefault(attempt["engine"], {"mentioned": 0, "valid": 0})
        if is_valid and response:
            cell["valid"] += 1
            if response["brand_mentioned"]:
                cell["mentioned"] += 1
            target = k_flags if probe != "D" else d_flags
            target.append(response)
            if probe != "D":
                if response["brand_mentioned"]:
                    share_counts[project["brand_name"]] = share_counts.get(project["brand_name"], 0) + 1
                for name in json.loads(response["competitor_mentions"] or "[]"):
                    share_counts[name] = share_counts.get(name, 0) + 1
        if revision and is_valid:
            try:
                payload = json.loads(revision["result_json"] or "{}")
            except json.JSONDecodeError:
                payload = {}
            for entity in payload.get("entities") or []:
                if entity.get("role") == "brand" and entity.get("mention_quote"):
                    sentiment.append(
                        {
                            "sentiment": entity.get("sentiment"),
                            "quote": entity.get("mention_quote"),
                            "attempt_id": attempt["id"],
                        }
                    )
    summary["n_excluded"] = summary["n_total"] - summary["n_valid"]
    summary["engines"] = engines
    summary["matrix"] = list(matrix.values())
    for row in summary["matrix"]:
        for cell in row["cells"].values():
            cell["text"] = f"{cell['mentioned']}/{cell['valid']}"
    summary["k"] = _rate_block(k_flags)
    summary["d"] = {
        "n_valid": len(d_flags),
        "mention_rate": _rate_block(d_flags)["mention_rate"],
        "note": "D 类直接点名品牌，不能当作自然发现率",
    }
    total_share = sum(share_counts.values())
    summary["share"] = [
        {"name": name, "count": count, "share": round(count / total_share * 100, 1)}
        for name, count in sorted(share_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    if summary["share"]:
        own = next((item for item in summary["share"] if item["name"] == project["brand_name"]), None)
        summary["k"]["share"] = own["share"] if own else 0
    summary["sentiment"] = sentiment[:6]
    summary["legacy_mention_rate"] = summary["k"]["mention_rate"]
    return summary


def _rate_block(rows: list[dict]) -> dict:
    if not rows:
        return {"n_valid": 0, "mention_rate": None, "recommend_rate": None, "first_rate": None, "share": None}
    mentioned = sum(bool(item["brand_mentioned"]) for item in rows)
    recommended = sum(bool(item["recommended"]) for item in rows)
    firsts = sum(item["mention_position"] == 1 for item in rows)
    return {
        "n_valid": len(rows),
        "mention_rate": round(mentioned / len(rows) * 100, 1),
        "recommend_rate": round(recommended / len(rows) * 100, 1),
        "first_rate": round(firsts / len(rows) * 100, 1),
        "share": None,
    }


def _legacy_summary(summary: dict, responses: list[dict]) -> dict:
    summary["n_total"] = len(responses)
    summary["n_valid"] = len(responses)
    summary["compare_note"] = "这期没有配置快照，比率只供参考"
    engines = []
    matrix: dict[int, dict] = {}
    for item in responses:
        if item["platform"] not in engines:
            engines.append(item["platform"])
        bucket = matrix.setdefault(
            item["question_id"],
            {
                "question_id": item["question_id"],
                "question": item["question"],
                "probe_type": item.get("probe_type") or "K",
                "intent": item["intent"],
                "cells": {},
            },
        )
        cell = bucket["cells"].setdefault(item["platform"], {"mentioned": 0, "valid": 0})
        cell["valid"] += 1
        cell["mentioned"] += int(bool(item["brand_mentioned"]))
    summary["engines"] = engines
    summary["matrix"] = list(matrix.values())
    for row in summary["matrix"]:
        for cell in row["cells"].values():
            cell["text"] = f"{cell['mentioned']}/{cell['valid']}"
    k_rows = [item for item in responses if (item.get("probe_type") or "K") != "D"]
    d_rows = [item for item in responses if item.get("probe_type") == "D"]
    summary["k"] = _rate_block(k_rows)
    summary["d"] = {
        "n_valid": len(d_rows),
        "mention_rate": _rate_block(d_rows)["mention_rate"],
        "note": "D 类直接点名品牌，不能当作自然发现率",
    }
    summary["legacy_mention_rate"] = summary["k"]["mention_rate"]
    return summary


def project_visibility(db: Database, project_id: int) -> dict:
    project = get_project(db, project_id)
    runs = db.fetch_all(
        "SELECT * FROM geo_runs WHERE project_id = ? ORDER BY run_at DESC, id DESC LIMIT 2",
        (project_id,),
    )
    if not runs:
        return _empty_visibility(project)
    current = _summarize_run(db, project, runs[0])
    if len(runs) == 1:
        current["compare_note"] = current["compare_note"] if current["compare_note"] != "尚无采集" else "没有上一期"
        return current
    previous = _summarize_run(db, project, runs[1])
    current["previous_mention_rate"] = previous["k"]["mention_rate"]
    same_hash = bool(current["config_hash"] and current["config_hash"] == previous["config_hash"])
    current["comparable"] = same_hash
    if same_hash and current["k"]["mention_rate"] is not None and previous["k"]["mention_rate"] is not None:
        current["mention_rate_change"] = round(current["k"]["mention_rate"] - previous["k"]["mention_rate"], 1)
        current["compare_note"] = "配置哈希一致，可以和上一期比较"
    elif current["config_hash"] != previous["config_hash"]:
        current["compare_note"] = "口径变化：配置哈希不同，不能把两期比率直接相减"
    return current


def project_sources(db: Database, project_id: int) -> dict:
    project = get_project(db, project_id)
    run = db.fetch_one(
        "SELECT * FROM geo_runs WHERE project_id = ? ORDER BY run_at DESC, id DESC LIMIT 1",
        (project_id,),
    )
    empty = {"domains": [], "gaps": [], "own_share": None, "total": 0, "note": "尚无结构化引用"}
    if not run:
        return empty
    rows = db.fetch_all(
        """
        SELECT c.*, a.access, a.status, a.response_id, r.brand_mentioned
        FROM geo_citations c
        JOIN geo_attempts a ON a.id = c.attempt_id
        LEFT JOIN geo_responses r ON r.id = a.response_id
        WHERE a.geo_run_id = ? AND c.source_kind = 'provider_citation'
          AND a.status = 'ok' AND a.access = 'api'
        """,
        (run["id"],),
    )
    if not rows:
        empty["note"] = "本期没有可计入的结构化引用（模拟和浏览器 stub 不计入）"
        return empty
    domains: dict[str, dict] = {}
    gaps: dict[str, dict] = {}
    for row in rows:
        bucket = domains.setdefault(
            row["domain"] or row["url"],
            {"domain": row["domain"], "category": row["category"], "count": 0, "mentions_brand": 0},
        )
        bucket["count"] += 1
        if row["brand_mentioned"]:
            bucket["mentions_brand"] += 1
        if row["category"] == "competitor" and not row["brand_mentioned"]:
            gap = gaps.setdefault(
                row["url"],
                {"url": row["url"], "domain": row["domain"], "count": 0, "category": row["category"]},
            )
            gap["count"] += 1
    total = sum(item["count"] for item in domains.values())
    own = sum(item["count"] for item in domains.values() if item["category"] == "own")
    return {
        "domains": sorted(domains.values(), key=lambda item: (-item["count"], item["domain"])),
        "gaps": sorted(gaps.values(), key=lambda item: -item["count"])[:8],
        "own_share": round(own / total * 100, 1) if total else None,
        "total": total,
        "note": "只统计引擎返回的结构化引用",
    }


def list_attempts(db: Database, project_id: int, run_id: int | None = None) -> list[dict]:
    get_project(db, project_id)
    if run_id is None:
        run = db.fetch_one(
            "SELECT id FROM geo_runs WHERE project_id = ? ORDER BY run_at DESC, id DESC LIMIT 1",
            (project_id,),
        )
        if not run:
            return []
        run_id = run["id"]
    else:
        run = _require(db.fetch_one("SELECT * FROM geo_runs WHERE id = ?", (run_id,)), "geo run")
        if run["project_id"] != project_id:
            raise ValueError("run does not belong to project")
    return db.fetch_all(
        """
        SELECT a.*, q.question, q.probe_type, q.intent
        FROM geo_attempts a
        JOIN geo_questions q ON q.id = a.question_id
        WHERE a.geo_run_id = ?
        ORDER BY a.id
        """,
        (run_id,),
    )


def get_attempt_detail(db: Database, attempt_id: int) -> dict:
    attempt = _require(
        db.fetch_one(
            """
            SELECT a.*, q.question, q.probe_type, q.intent, q.question_set_id, r.project_id
            FROM geo_attempts a
            JOIN geo_questions q ON q.id = a.question_id
            JOIN geo_runs r ON r.id = a.geo_run_id
            WHERE a.id = ?
            """,
            (attempt_id,),
        ),
        "attempt",
    )
    attempt["request_params"] = json.loads(attempt["request_params_json"] or "{}")
    attempt["web_queries"] = json.loads(attempt["web_queries_json"] or "[]")
    citations = db.fetch_all("SELECT * FROM geo_citations WHERE attempt_id = ? ORDER BY position, id", (attempt_id,))
    revisions = db.fetch_all(
        """
        SELECT * FROM geo_analysis_revisions
        WHERE attempt_id = ? OR (response_id IS NOT NULL AND response_id = ?)
        ORDER BY id
        """,
        (attempt_id, attempt["response_id"]),
    )
    for revision in revisions:
        revision["result"] = json.loads(revision["result_json"] or "{}")
    response = None
    if attempt["response_id"]:
        response = db.fetch_one("SELECT * FROM geo_responses WHERE id = ?", (attempt["response_id"],))
        if response:
            response["competitor_mentions"] = json.loads(response["competitor_mentions"] or "[]")
    return {"attempt": attempt, "citations": citations, "revisions": revisions, "response": response}


def list_revisions(db: Database, response_id: int) -> list[dict]:
    _require(db.fetch_one("SELECT id FROM geo_responses WHERE id = ?", (response_id,)), "geo response")
    rows = db.fetch_all(
        "SELECT * FROM geo_analysis_revisions WHERE response_id = ? ORDER BY id",
        (response_id,),
    )
    for row in rows:
        row["result"] = json.loads(row["result_json"] or "{}")
    return rows


def _playbook_stats(db: Database) -> dict[int, dict]:
    action_rows = db.fetch_all(
        """
        SELECT pv.playbook_id AS playbook_id, COUNT(DISTINCT a.project_id) AS project_count
        FROM playbook_versions pv
        LEFT JOIN plan_actions a ON a.playbook_version_id = pv.id
        GROUP BY pv.playbook_id
        """
    )
    outcome_rows = db.fetch_all(
        """
        SELECT pv.playbook_id AS playbook_id, AVG(o.delta) AS avg_delta,
               COALESCE(SUM(o.sample_n), 0) AS sample_n
        FROM playbook_versions pv
        LEFT JOIN playbook_outcomes o ON o.playbook_version_id = pv.id
        GROUP BY pv.playbook_id
        """
    )
    stats = {row["playbook_id"]: {"project_count": row["project_count"] or 0, "avg_delta": None, "sample_n": 0} for row in action_rows}
    for row in outcome_rows:
        bucket = stats.setdefault(row["playbook_id"], {"project_count": 0, "avg_delta": None, "sample_n": 0})
        bucket["avg_delta"] = row["avg_delta"]
        bucket["sample_n"] = row["sample_n"] or 0
    return stats


def list_playbooks(db: Database) -> list[dict]:
    ensure_playbook_library(db)
    stats = _playbook_stats(db)
    playbooks = db.fetch_all("SELECT * FROM playbooks ORDER BY code")
    items = []
    for playbook in playbooks:
        version = db.fetch_one(
            "SELECT * FROM playbook_versions WHERE playbook_id = ? ORDER BY version DESC LIMIT 1",
            (playbook["id"],),
        )
        stat = stats.get(playbook["id"], {})
        items.append(
            {
                **playbook,
                "latest_version": version["version"] if version else None,
                "latest_version_id": version["id"] if version else None,
                "trigger_condition": version["trigger_condition"] if version else "",
                "acceptance_metric": version["acceptance_metric"] if version else "",
                "project_count": stat.get("project_count") or 0,
                "avg_delta": None if stat.get("avg_delta") is None else round(float(stat["avg_delta"]), 2),
                "sample_n": stat.get("sample_n") or 0,
            }
        )
    return items


def get_playbook(db: Database, playbook_id: int) -> dict:
    ensure_playbook_library(db)
    playbook = _require(db.fetch_one("SELECT * FROM playbooks WHERE id = ?", (playbook_id,)), "playbook")
    versions = db.fetch_all(
        "SELECT * FROM playbook_versions WHERE playbook_id = ? ORDER BY version DESC",
        (playbook_id,),
    )
    actions = db.fetch_all(
        """
        SELECT a.*, p.name AS project_name, pv.version AS playbook_version
        FROM plan_actions a
        JOIN projects p ON p.id = a.project_id
        JOIN playbook_versions pv ON pv.id = a.playbook_version_id
        WHERE pv.playbook_id = ?
        ORDER BY a.id DESC
        """,
        (playbook_id,),
    )
    outcomes = db.fetch_all(
        """
        SELECT o.*, p.name AS project_name, pv.version AS playbook_version
        FROM playbook_outcomes o
        JOIN projects p ON p.id = o.project_id
        LEFT JOIN playbook_versions pv ON pv.id = o.playbook_version_id
        WHERE pv.playbook_id = ?
        ORDER BY o.id DESC
        """,
        (playbook_id,),
    )
    return {"playbook": playbook, "versions": versions, "actions": actions, "outcomes": outcomes}


def create_playbook(db: Database, payload: PlaybookCreate) -> dict:
    ensure_playbook_library(db)
    playbook = _insert(
        db,
        "playbooks",
        {
            "code": payload.code.strip(),
            "title": payload.title.strip(),
            "category": payload.category,
            "industries": payload.industries,
            "markets": payload.markets,
            "engines": payload.engines,
            "status": payload.status,
        },
    )
    version = _insert(
        db,
        "playbook_versions",
        {
            "playbook_id": playbook["id"],
            "version": 1,
            "trigger_condition": payload.trigger_condition,
            "steps": payload.steps,
            "acceptance_metric": payload.acceptance_metric,
            "status": payload.status,
            "change_note": "首个版本",
        },
    )
    return {"playbook": playbook, "version": version}


def add_playbook_version(db: Database, playbook_id: int, payload: PlaybookVersionCreate) -> dict:
    _require(db.fetch_one("SELECT id FROM playbooks WHERE id = ?", (playbook_id,)), "playbook")
    current = db.fetch_one(
        "SELECT MAX(version) AS version FROM playbook_versions WHERE playbook_id = ?",
        (playbook_id,),
    )
    version_no = int(current["version"] or 0) + 1
    version = _insert(
        db,
        "playbook_versions",
        {
            "playbook_id": playbook_id,
            "version": version_no,
            "trigger_condition": payload.trigger_condition,
            "steps": payload.steps,
            "acceptance_metric": payload.acceptance_metric,
            "status": payload.status,
            "change_note": payload.change_note,
        },
    )
    if payload.status == "已发布":
        db.execute("UPDATE playbooks SET status = '已发布' WHERE id = ?", (playbook_id,))
    return version


def list_plan(db: Database, project_id: int) -> list[dict]:
    get_project(db, project_id)
    return db.fetch_all(
        """
        SELECT a.*, pb.code AS playbook_code, pb.title AS playbook_title, pv.version AS playbook_version
        FROM plan_actions a
        LEFT JOIN playbook_versions pv ON pv.id = a.playbook_version_id
        LEFT JOIN playbooks pb ON pb.id = pv.playbook_id
        WHERE a.project_id = ?
        ORDER BY a.id
        """,
        (project_id,),
    )


def add_plan_action(db: Database, project_id: int, payload: PlanActionCreate) -> dict:
    get_project(db, project_id)
    if payload.playbook_version_id is not None:
        _require(
            db.fetch_one("SELECT id FROM playbook_versions WHERE id = ?", (payload.playbook_version_id,)),
            "playbook version",
        )
    return _insert(db, "plan_actions", {"project_id": project_id, **payload.model_dump()})


def add_outcome(db: Database, plan_action_id: int, payload: OutcomeCreate) -> dict:
    action = _require(db.fetch_one("SELECT * FROM plan_actions WHERE id = ?", (plan_action_id,)), "plan action")
    delta = None
    if payload.before_value is not None and payload.after_value is not None:
        delta = round(payload.after_value - payload.before_value, 4)
    return _insert(
        db,
        "playbook_outcomes",
        {
            "plan_action_id": plan_action_id,
            "playbook_version_id": action["playbook_version_id"],
            "project_id": action["project_id"],
            "metric_name": payload.metric_name,
            "before_value": payload.before_value,
            "after_value": payload.after_value,
            "delta": delta,
            "sample_n": payload.sample_n,
            "note": payload.note,
        },
    )


def suggest_plan(db: Database, project_id: int) -> list[dict]:
    ensure_playbook_library(db)
    get_project(db, project_id)
    sources = project_sources(db, project_id)
    visibility = project_visibility(db, project_id)
    created = []
    existing = {
        row["playbook_version_id"]
        for row in db.fetch_all(
            "SELECT playbook_version_id FROM plan_actions WHERE project_id = ? AND status != '完成'",
            (project_id,),
        )
        if row["playbook_version_id"]
    }

    def attach(code: str, action: str, priority: str) -> None:
        version = db.fetch_one(
            """
            SELECT pv.*, pb.category FROM playbook_versions pv
            JOIN playbooks pb ON pb.id = pv.playbook_id
            WHERE pb.code = ? AND pv.status = '已发布'
            ORDER BY pv.version DESC LIMIT 1
            """,
            (code,),
        )
        if version is None or version["id"] in existing:
            return
        created.append(
            add_plan_action(
                db,
                project_id,
                PlanActionCreate(
                    playbook_version_id=version["id"],
                    priority=priority,
                    action=action,
                    action_type=version["category"],
                    acceptance=version["acceptance_metric"],
                    status="待开始",
                ),
            )
        )
        existing.add(version["id"])

    own_share = sources["own_share"]
    if own_share is None or own_share < 5:
        attach("PB-004", "在官网产品页补充已核实的 FAQ，并加上结构化数据", "P0")
    mention = visibility["k"]["mention_rate"]
    if sources["gaps"] or (mention is not None and mention < 50):
        attach("PB-012", "从引用缺口里挑选评测页，准备送测材料", "P0")
    if not created:
        attach("PB-017", "写一页只使用已核实参数的竞品对比", "P1")
    return created
