from __future__ import annotations

from pydantic import BaseModel, Field


class ClientCreate(BaseModel):
    name: str
    brand_name: str
    domain: str
    industry: str = ""
    contact_name: str = ""
    contact_email: str = ""


class ClientUpdate(ClientCreate):
    pass


class ProjectCreate(BaseModel):
    client_id: int
    name: str
    service_provider: str = ""
    period_start: str | None = None
    period_end: str | None = None
    cadence: str = "monthly"
    subscription_status: str = "trial"
    alert_threshold: float = 20


class ProjectUpdate(ProjectCreate):
    status: str = "active"


class CompetitorCreate(BaseModel):
    name: str
    domain: str = ""


class CommitmentCreate(BaseModel):
    category: str
    metric_name: str
    target_operator: str = ">="
    target_value: float | None = None
    unit: str = ""
    due_date: str | None = None
    source_clause: str = ""
    actual_value: float | None = None
    achievement_status: str = "pending"
    evidence_source: str = ""
    notes: str = ""


class KeywordTargetCreate(BaseModel):
    keyword: str
    category: str = "commercial"
    engine: str = "baidu"
    region_name: str = "全国"
    language: str = "zh-CN"
    target_position: int | None = None
    target_url: str = ""


class SeoMetricCreate(BaseModel):
    captured_at: str
    source: str
    metric_key: str
    metric_name: str
    value: float
    unit: str = ""
    notes: str = ""


class KeywordRankingCreate(BaseModel):
    captured_at: str
    source: str
    keyword: str
    category: str = "commercial"
    engine: str = "baidu"
    region_name: str = "全国"
    language: str = "zh-CN"
    position: int | None = None
    search_volume: int | None = None
    target_url: str = ""


class SeoImportRequest(BaseModel):
    filename: str = "seo-data.csv"
    content: str
    default_source: str = "CSV import"
    default_captured_at: str


class QuestionSetCreate(BaseModel):
    name: str
    version: str
    status: str = "draft"


class GeoQuestionCreate(BaseModel):
    intent: str
    question: str
    weight: float = 1
    expected_facts: str = ""
    probe_type: str = "K"
    language: str = "zh-CN"
    rationale: str = ""


class GeoQuestionUpdate(BaseModel):
    intent: str
    question: str
    weight: float = 1
    expected_facts: str = ""
    probe_type: str = "K"
    language: str = "zh-CN"
    rationale: str = ""


class GeoRunCreate(BaseModel):
    question_set_id: int
    run_at: str
    status: str = "draft"
    notes: str = ""


class GeoResponseCreate(BaseModel):
    question_id: int
    platform: str
    model: str = ""
    raw_response: str
    brand_mentioned: bool | None = None
    mention_position: int | None = None
    accurate: bool | None = None
    recommended: bool = False
    competitor_mentions: list[str] = Field(default_factory=list)
    cited_source: bool | None = None
    misinformation: str = ""
    review_status: str = "pending"
    reviewer_notes: str = ""
    sample_index: int = 0


class GeoResponseReview(BaseModel):
    brand_mentioned: bool
    mention_position: int | None = None
    accurate: bool | None = None
    recommended: bool = False
    competitor_mentions: list[str] = Field(default_factory=list)
    cited_source: bool = False
    misinformation: str = ""
    review_status: str = "reviewed"
    reviewer_notes: str = ""


class GeoProviderSpec(BaseModel):
    platform: str
    provider: str = "openrouter"
    model: str = ""


class GeoBatchRunRequest(BaseModel):
    question_set_id: int
    run_at: str
    providers: list[GeoProviderSpec]
    notes: str = ""


class ReportCreate(BaseModel):
    period_start: str | None = None
    period_end: str | None = None
    title: str = "SEO / GEO 服务效果独立第三方测评报告"
    executive_summary: str = ""
    conclusion: str = ""
    recommendations: str = ""
    status: str = "draft"


class KeyContentCreate(BaseModel):
    kind: str
    title: str
    body: str = ""
    confirmed: bool = False


class ProjectProfileUpdate(BaseModel):
    delivery_stage: str | None = None
    delivery_status: str | None = None
    language: str | None = None
    region: str | None = None
    aliases: str | None = None
    monthly_budget_usd: float | None = None
    cadence: str | None = None


class BootstrapRequest(BaseModel):
    client_name: str
    brand_name: str
    domain: str
    industry: str = ""
    aliases: str = ""
    competitors: list[str] = Field(default_factory=list)
    language: str = "zh-CN"
    region: str = "中国大陆"
    cadence: str = "monthly"
    delivery_stage: str = "诊断报告"
    delivery_status: str = "试用"
    monthly_budget_usd: float | None = None
    project_name: str = ""
    key_contents: list[KeyContentCreate] = Field(default_factory=list)


class GenerateQuestionsRequest(BaseModel):
    name: str = "自动问题库"
    llm: bool = True


class BaselineCreate(BaseModel):
    question_set_id: int
    engines: list[str]
    language: str = "zh-CN"
    region: str = "中国大陆"
    sample_count: int = 1
    web_sample_percent: int | None = None


class ChannelUpdate(BaseModel):
    enabled: bool | None = None
    api_key: str | None = None
    api_secret: str | None = None
    clear_key: bool = False
    model: str | None = None
    web_search: bool | None = None
    region: str | None = None
    language: str | None = None
    concurrency: int | None = None
    rate_limit_rpm: int | None = None
    budget_cap_usd: float | None = None


class StrategyUpdate(BaseModel):
    channels: list[str] = Field(default_factory=list)
    sample_count: int = 1
    cadence: str = "monthly"
    web_sample_percent: int = 15


class BudgetEstimateRequest(BaseModel):
    engines: list[str] = Field(default_factory=list)
    sample_count: int = 1
    question_set_id: int | None = None


class MonitorRequest(BaseModel):
    baseline_id: int


class PlaybookCreate(BaseModel):
    code: str
    title: str
    category: str = ""
    industries: str = ""
    markets: str = ""
    engines: str = ""
    trigger_condition: str = ""
    steps: str = ""
    acceptance_metric: str = ""
    status: str = "草稿"


class PlaybookVersionCreate(BaseModel):
    trigger_condition: str
    steps: str
    acceptance_metric: str = ""
    change_note: str = ""
    status: str = "草稿"


class PlanActionCreate(BaseModel):
    playbook_version_id: int | None = None
    report_id: int | None = None
    priority: str = "P1"
    action: str
    action_type: str = ""
    acceptance: str = ""
    status: str = "待开始"


class OutcomeCreate(BaseModel):
    metric_name: str = "k_mention_rate"
    before_value: float | None = None
    after_value: float | None = None
    sample_n: int | None = None
    note: str = ""
