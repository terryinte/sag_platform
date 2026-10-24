from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    brand_name TEXT NOT NULL,
    domain TEXT NOT NULL,
    industry TEXT NOT NULL DEFAULT '',
    contact_name TEXT NOT NULL DEFAULT '',
    contact_email TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    service_provider TEXT NOT NULL DEFAULT '',
    period_start TEXT,
    period_end TEXT,
    cadence TEXT NOT NULL DEFAULT 'monthly',
    subscription_status TEXT NOT NULL DEFAULT 'trial',
    alert_threshold REAL NOT NULL DEFAULT 20,
    status TEXT NOT NULL DEFAULT 'active',
    delivery_stage TEXT NOT NULL DEFAULT '诊断报告',
    delivery_status TEXT NOT NULL DEFAULT '试用',
    language TEXT NOT NULL DEFAULT 'zh-CN',
    region TEXT NOT NULL DEFAULT '中国大陆',
    aliases TEXT NOT NULL DEFAULT '',
    monthly_budget_usd REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS competitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS commitments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    target_operator TEXT NOT NULL DEFAULT '>=',
    target_value REAL,
    unit TEXT NOT NULL DEFAULT '',
    due_date TEXT,
    source_clause TEXT NOT NULL DEFAULT '',
    actual_value REAL,
    achievement_status TEXT NOT NULL DEFAULT 'pending',
    evidence_source TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS keyword_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'commercial',
    engine TEXT NOT NULL DEFAULT 'baidu',
    region_name TEXT NOT NULL DEFAULT '全国',
    language TEXT NOT NULL DEFAULT 'zh-CN',
    target_position INTEGER,
    target_url TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS seo_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    captured_at TEXT NOT NULL,
    source TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS keyword_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    captured_at TEXT NOT NULL,
    source TEXT NOT NULL,
    keyword TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'commercial',
    engine TEXT NOT NULL DEFAULT 'baidu',
    region_name TEXT NOT NULL DEFAULT '全国',
    language TEXT NOT NULL DEFAULT 'zh-CN',
    position INTEGER,
    search_volume INTEGER,
    target_url TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS geo_question_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, version)
);

CREATE TABLE IF NOT EXISTS geo_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_set_id INTEGER NOT NULL REFERENCES geo_question_sets(id) ON DELETE CASCADE,
    intent TEXT NOT NULL,
    question TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1,
    expected_facts TEXT NOT NULL DEFAULT '',
    probe_type TEXT NOT NULL DEFAULT 'K',
    language TEXT NOT NULL DEFAULT 'zh-CN',
    rationale TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS geo_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    question_set_id INTEGER NOT NULL REFERENCES geo_question_sets(id),
    run_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    notes TEXT NOT NULL DEFAULT '',
    baseline_id INTEGER,
    sample_count INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS geo_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    geo_run_id INTEGER NOT NULL REFERENCES geo_runs(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES geo_questions(id),
    platform TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    raw_response TEXT NOT NULL,
    brand_mentioned INTEGER NOT NULL DEFAULT 0,
    mention_position INTEGER,
    accurate INTEGER,
    recommended INTEGER NOT NULL DEFAULT 0,
    competitor_mentions TEXT NOT NULL DEFAULT '[]',
    cited_source INTEGER NOT NULL DEFAULT 0,
    misinformation TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'pending',
    reviewer_notes TEXT NOT NULL DEFAULT '',
    sample_index INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(geo_run_id, question_id, platform, model, sample_index)
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    period_start TEXT,
    period_end TEXT,
    title TEXT NOT NULL,
    executive_summary TEXT NOT NULL DEFAULT '',
    conclusion TEXT NOT NULL DEFAULT '',
    recommendations TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_key_contents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    confirmed INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS geo_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    question_set_id INTEGER NOT NULL REFERENCES geo_question_sets(id),
    engines_json TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'zh-CN',
    region TEXT NOT NULL DEFAULT '中国大陆',
    sample_count INTEGER NOT NULL DEFAULT 1,
    protocol_version TEXT NOT NULL DEFAULT 'geo-p0-1',
    parser_version TEXT NOT NULL DEFAULT 'judge-1',
    config_hash TEXT NOT NULL,
    snapshot_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS geo_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    response_id INTEGER REFERENCES geo_responses(id) ON DELETE SET NULL,
    geo_run_id INTEGER NOT NULL REFERENCES geo_runs(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    engine TEXT NOT NULL,
    attempt_no INTEGER NOT NULL DEFAULT 1,
    sample_index INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error_code TEXT NOT NULL DEFAULT '',
    access TEXT NOT NULL DEFAULT 'api',
    request_params_json TEXT NOT NULL DEFAULT '{}',
    raw_response TEXT NOT NULL DEFAULT '',
    raw_payload_json TEXT NOT NULL DEFAULT '{}',
    payload_sha256 TEXT NOT NULL DEFAULT '',
    web_queries_json TEXT NOT NULL DEFAULT '[]',
    model_version TEXT NOT NULL DEFAULT '',
    config_hash TEXT NOT NULL DEFAULT '',
    cost_usd REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS geo_citations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL REFERENCES geo_attempts(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    position INTEGER,
    source_kind TEXT NOT NULL DEFAULT 'provider_citation',
    payload_path TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'other'
);

CREATE TABLE IF NOT EXISTS geo_analysis_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER REFERENCES geo_attempts(id) ON DELETE CASCADE,
    response_id INTEGER REFERENCES geo_responses(id) ON DELETE CASCADE,
    parser_version TEXT NOT NULL,
    reviewer TEXT NOT NULL DEFAULT 'llm',
    result_json TEXT NOT NULL,
    valid INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS playbooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    industries TEXT NOT NULL DEFAULT '',
    markets TEXT NOT NULL DEFAULT '',
    engines TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '草稿',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS playbook_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playbook_id INTEGER NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    trigger_condition TEXT NOT NULL DEFAULT '',
    steps TEXT NOT NULL DEFAULT '',
    acceptance_metric TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '草稿',
    change_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(playbook_id, version)
);

CREATE TABLE IF NOT EXISTS plan_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    report_id INTEGER REFERENCES reports(id) ON DELETE SET NULL,
    playbook_version_id INTEGER REFERENCES playbook_versions(id),
    priority TEXT NOT NULL DEFAULT 'P1',
    action TEXT NOT NULL,
    action_type TEXT NOT NULL DEFAULT '',
    acceptance TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '待开始',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS playbook_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_action_id INTEGER NOT NULL REFERENCES plan_actions(id) ON DELETE CASCADE,
    playbook_version_id INTEGER REFERENCES playbook_versions(id),
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    metric_name TEXT NOT NULL DEFAULT 'k_mention_rate',
    before_value REAL,
    after_value REAL,
    delta REAL,
    sample_n INTEGER,
    note TEXT NOT NULL DEFAULT '',
    before_run_id INTEGER,
    after_run_id INTEGER,
    before_k_rate REAL,
    after_k_rate REAL,
    before_d_rate REAL,
    after_d_rate REAL,
    before_first_rate REAL,
    after_first_rate REAL,
    success INTEGER,
    measured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS geo_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    baseline_id INTEGER REFERENCES geo_baselines(id),
    cron TEXT NOT NULL DEFAULT 'monthly',
    next_run_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    monthly_budget_usd REAL
);

CREATE TABLE IF NOT EXISTS budget_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    geo_run_id INTEGER REFERENCES geo_runs(id),
    kind TEXT NOT NULL,
    est_cost_usd REAL,
    actual_cost_usd REAL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collection_channels (
    channel_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    api_key_enc TEXT NOT NULL DEFAULT '',
    key_last4 TEXT NOT NULL DEFAULT '',
    secret_last4 TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    web_search INTEGER NOT NULL DEFAULT 1,
    region TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    concurrency INTEGER NOT NULL DEFAULT 2,
    rate_limit_rpm INTEGER NOT NULL DEFAULT 30,
    budget_cap_usd REAL,
    session_note TEXT NOT NULL DEFAULT '',
    timeout_seconds INTEGER,
    last_status TEXT NOT NULL DEFAULT '',
    last_latency_ms INTEGER,
    last_error TEXT NOT NULL DEFAULT '',
    last_tested_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_collection_strategies (
    project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    channels_json TEXT NOT NULL DEFAULT '[]',
    sample_count INTEGER NOT NULL DEFAULT 1,
    cadence TEXT NOT NULL DEFAULT 'monthly',
    web_sample_percent INTEGER NOT NULL DEFAULT 15,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_projects_client ON projects(client_id);
CREATE INDEX IF NOT EXISTS idx_commitments_project ON commitments(project_id);
CREATE INDEX IF NOT EXISTS idx_seo_metrics_project_date ON seo_metrics(project_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_rankings_project_date ON keyword_rankings(project_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_geo_runs_project_date ON geo_runs(project_id, run_at);
CREATE INDEX IF NOT EXISTS idx_geo_attempts_run ON geo_attempts(geo_run_id);
CREATE INDEX IF NOT EXISTS idx_geo_citations_attempt ON geo_citations(attempt_id);
CREATE INDEX IF NOT EXISTS idx_plan_actions_project ON plan_actions(project_id);
"""


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._ensure_column(connection, "keyword_targets", "region_name", "TEXT NOT NULL DEFAULT '全国'")
            self._ensure_column(connection, "keyword_targets", "language", "TEXT NOT NULL DEFAULT 'zh-CN'")
            self._ensure_column(connection, "keyword_rankings", "region_name", "TEXT NOT NULL DEFAULT '全国'")
            self._ensure_column(connection, "keyword_rankings", "language", "TEXT NOT NULL DEFAULT 'zh-CN'")
            self._ensure_column(connection, "projects", "delivery_stage", "TEXT NOT NULL DEFAULT '诊断报告'")
            self._ensure_column(connection, "projects", "delivery_status", "TEXT NOT NULL DEFAULT '试用'")
            self._ensure_column(connection, "projects", "language", "TEXT NOT NULL DEFAULT 'zh-CN'")
            self._ensure_column(connection, "projects", "region", "TEXT NOT NULL DEFAULT '中国大陆'")
            self._ensure_column(connection, "projects", "aliases", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "projects", "monthly_budget_usd", "REAL")
            self._ensure_column(connection, "geo_questions", "probe_type", "TEXT NOT NULL DEFAULT 'K'")
            self._ensure_column(connection, "geo_questions", "language", "TEXT NOT NULL DEFAULT 'zh-CN'")
            self._ensure_column(connection, "geo_questions", "rationale", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "geo_runs", "baseline_id", "INTEGER")
            self._ensure_column(connection, "geo_runs", "sample_count", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(connection, "geo_responses", "sample_index", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "project_key_contents", "source", "TEXT NOT NULL DEFAULT 'manual'")
            self._ensure_column(connection, "collection_channels", "session_note", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "collection_channels", "timeout_seconds", "INTEGER")
            self._ensure_column(connection, "playbook_outcomes", "before_run_id", "INTEGER")
            self._ensure_column(connection, "playbook_outcomes", "after_run_id", "INTEGER")
            self._ensure_column(connection, "playbook_outcomes", "before_k_rate", "REAL")
            self._ensure_column(connection, "playbook_outcomes", "after_k_rate", "REAL")
            self._ensure_column(connection, "playbook_outcomes", "before_d_rate", "REAL")
            self._ensure_column(connection, "playbook_outcomes", "after_d_rate", "REAL")
            self._ensure_column(connection, "playbook_outcomes", "before_first_rate", "REAL")
            self._ensure_column(connection, "playbook_outcomes", "after_first_rate", "REAL")
            self._ensure_column(connection, "playbook_outcomes", "success", "INTEGER")

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(query, params).fetchone()
        return dict(row) if row else None

    def execute(self, query: str, params: tuple = ()) -> int:
        with self.connect() as connection:
            cursor = connection.execute(query, params)
            return int(cursor.lastrowid)

    def execute_many(self, query: str, params: list[tuple]) -> int:
        if not params:
            return 0
        with self.connect() as connection:
            connection.executemany(query, params)
        return len(params)
