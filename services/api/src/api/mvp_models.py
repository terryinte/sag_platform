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
