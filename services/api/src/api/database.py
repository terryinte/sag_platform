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
    expected_facts TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS geo_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    question_set_id INTEGER NOT NULL REFERENCES geo_question_sets(id),
    run_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    notes TEXT NOT NULL DEFAULT ''
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
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(geo_run_id, question_id, platform, model)
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

CREATE INDEX IF NOT EXISTS idx_projects_client ON projects(client_id);
CREATE INDEX IF NOT EXISTS idx_commitments_project ON commitments(project_id);
CREATE INDEX IF NOT EXISTS idx_seo_metrics_project_date ON seo_metrics(project_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_rankings_project_date ON keyword_rankings(project_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_geo_runs_project_date ON geo_runs(project_id, run_at);
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
