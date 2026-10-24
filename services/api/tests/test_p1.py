import json

from test_geo_platform import _bootstrap, make_client

from api.collection_settings import select_sampled_questions
from api.geo_platform import aggregate_trends, closed_loop_metrics
from api.site_crawl import crawl_site, parse_page


HOME_HTML = """
<html><head>
<title>绿联氮化镓</title>
<meta name="description" content="多口充电器">
</head><body>
<h1>Nexode</h1>
<h2>100W</h2>
<main><p>适合出差。</p></main>
<a href="/products">产品</a>
<a href="https://other.example/x">外站</a>
</body></html>
"""

PRODUCT_HTML = """
<html><head><title>产品页</title></head>
<body><h1>充电器</h1><h2>氮化镓</h2><p>多口。</p>
<a href="https://other.example/about">外站关于</a>
<a href="/about">关于</a>
</body></html>
"""


def test_parse_page_extracts_headings_and_meta():
    page = parse_page(HOME_HTML, "https://brand.example/")
    assert page["title"] == "绿联氮化镓"
    assert page["h1"] == ["Nexode"]
    assert page["h2"] == ["100W"]
    assert page["meta_description"] == "多口充电器"
    assert any("出差" in item for item in page["snippets"])


def test_crawl_stays_on_host_and_reports_timeout():
    pages = {
        "https://brand.example/": HOME_HTML.encode(),
        "https://brand.example/products": PRODUCT_HTML.encode(),
        "https://brand.example/about": "<html><head><title>关于</title></head><body><h1>关于绿联</h1><p>公司。</p></body></html>".encode(),
    }

    def fetcher(url, _timeout):
        body = pages.get(url)
        if body is None:
            return 404, b""
        return 200, body

    result = crawl_site("brand.example", fetcher=fetcher, max_pages=4)
    assert result["ok"] is True
    urls = [item["url"] for item in result["pages"]]
    assert urls[0] == "https://brand.example/"
    assert any(url.endswith("/products") for url in urls)
    assert all("other.example" not in url for url in urls)
    assert any(item["source"] == "site_crawl" and item["kind"] == "产品线" for item in result["items"])

    def timed_out(_url, _timeout):
        raise TimeoutError("slow")

    failed = crawl_site("https://brand.example/", fetcher=timed_out)
    assert failed["ok"] is False
    assert "超时" in failed["error"]
    assert failed["items"] == []


def test_site_crawl_keeps_manual_rows(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    project = _bootstrap(client)
    before = client.get(f"/api/projects/{project['id']}/key-contents").json()

    def fake_crawl(_url, **_kwargs):
        return {
            "ok": False,
            "error": "官网返回 403，需要登录或拒绝了访问",
            "items": [],
            "pages": [],
        }

    monkeypatch.setattr("api.site_crawl.crawl_site", fake_crawl)
    denied = client.post(f"/api/projects/{project['id']}/site-crawl", json={})
    assert denied.status_code == 200
    assert denied.json()["ok"] is False
    assert "403" in denied.json()["error"]
    assert client.get(f"/api/projects/{project['id']}/key-contents").json() == before

    def ok_crawl(_url, **_kwargs):
        return {
            "ok": True,
            "error": "",
            "pages": [{"url": "https://ugreen.example/", "title": "绿联"}],
            "items": [
                {"kind": "产品线", "title": "氮化镓充电器", "body": "不应覆盖手工正文", "source": "site_crawl"},
                {"kind": "卖点", "title": "页面卖点", "body": "新卖点", "source": "site_crawl"},
            ],
        }

    monkeypatch.setattr("api.site_crawl.crawl_site", ok_crawl)
    saved = client.post(f"/api/projects/{project['id']}/site-crawl", json={"url": project["domain"]})
    assert saved.status_code == 200
    body = saved.json()
    assert body["ok"] is True
    assert body["kept_manual"] >= 1
    assert body["created"] == 1
    rows = client.get(f"/api/projects/{project['id']}/key-contents").json()
    manual = next(item for item in rows if item["title"] == "氮化镓充电器")
    assert manual["source"] == "manual"
    assert manual["body"] == "多口"
    assert any(item["title"] == "页面卖点" and item["source"] == "site_crawl" for item in rows)


def test_sampling_selects_core_questions_by_percent():
    questions = [
        {"id": 1, "probe_type": "K", "intent": "发现"},
        {"id": 4, "probe_type": "K", "intent": "使用场景"},
        {"id": 2, "probe_type": "D", "intent": "品牌"},
        {"id": 5, "probe_type": "K", "intent": "替代"},
        {"id": 3, "probe_type": "K", "intent": "对比"},
    ]
    picked = select_sampled_questions(questions, 50)
    assert [item["id"] for item in picked] == [2, 3]
    assert select_sampled_questions(questions, 0) == []
    assert select_sampled_questions([], 100) == []


def test_trends_drop_runs_with_a_different_hash():
    points = [
        {"run_id": 1, "run_at": "2026-01-01", "config_hash": "aaa", "k_mention": 10, "d_recommend": 1, "first_rate": 0},
        {"run_id": 2, "run_at": "2026-02-01", "config_hash": "aaa", "k_mention": 20, "d_recommend": 2, "first_rate": 5},
        {"run_id": 3, "run_at": "2026-03-01", "config_hash": "bbb", "k_mention": 90, "d_recommend": 9, "first_rate": 9},
    ]
    latest = aggregate_trends(points)
    assert latest["config_hash"] == "bbb"
    assert [item["run_id"] for item in latest["series"]] == [3]
    assert {item["run_id"] for item in latest["excluded"]} == {1, 2}

    older_hash_first = [
        {"run_id": 3, "run_at": "2026-01-01", "config_hash": "bbb", "k_mention": 90, "d_recommend": 9, "first_rate": 9},
        {"run_id": 1, "run_at": "2026-02-01", "config_hash": "aaa", "k_mention": 10, "d_recommend": 1, "first_rate": 0},
        {"run_id": 2, "run_at": "2026-03-01", "config_hash": "aaa", "k_mention": 20, "d_recommend": 2, "first_rate": 5},
    ]
    older_latest = aggregate_trends(older_hash_first)
    assert older_latest["config_hash"] == "aaa"
    assert [item["run_id"] for item in older_latest["series"]] == [1, 2]
    assert older_latest["excluded"][0]["run_id"] == 3
    legacy = aggregate_trends(
        [
            {"run_id": 7, "run_at": "2026-01-01", "config_hash": None, "k_mention": 10},
            {"run_id": 8, "run_at": "2026-02-01", "config_hash": None, "k_mention": 30},
        ]
    )
    assert legacy["config_hash"] is None
    assert [item["run_id"] for item in legacy["series"]] == [7, 8]
    assert legacy["excluded"] == []


def test_closed_loop_metrics_from_rates():
    metrics = closed_loop_metrics(
        {"k_mention": 10, "d_recommend": 0, "first_rate": 1, "n_valid": 4},
        {"k_mention": 16, "d_recommend": 5, "first_rate": 2, "n_valid": 4},
    )
    assert metrics["delta"] == 6
    assert metrics["success"] == 1
    assert metrics["before_d_rate"] == 0
    assert metrics["after_d_rate"] == 5
    assert metrics["before_first_rate"] == 1
    assert metrics["after_first_rate"] == 2


def _mark_k(db, run_id: int, mentioned: int) -> None:
    attempt = db.fetch_one(
        """
        SELECT a.* FROM geo_attempts a
        JOIN geo_questions q ON q.id = a.question_id
        WHERE a.geo_run_id = ? AND q.probe_type = 'K' AND a.engine = 'ChatGPT'
        ORDER BY a.id LIMIT 1
        """,
        (run_id,),
    )
    response_id = db.execute(
        """
        INSERT INTO geo_responses (
            geo_run_id, question_id, platform, model, raw_response,
            brand_mentioned, mention_position, recommended, competitor_mentions, sample_index
        ) VALUES (?, ?, ?, 'test', '正文', ?, ?, 0, '[]', ?)
        """,
        (run_id, attempt["question_id"], attempt["engine"], mentioned, 1 if mentioned else None, attempt["sample_index"]),
    )
    db.execute(
        "UPDATE geo_attempts SET status = 'ok', access = 'api', error_code = '', response_id = ? WHERE id = ?",
        (response_id, attempt["id"]),
    )
    db.execute(
        """
        INSERT INTO geo_analysis_revisions (attempt_id, response_id, parser_version, reviewer, result_json, valid)
        VALUES (?, ?, 'judge-1', 'heuristic', ?, 1)
        """,
        (attempt["id"], response_id, json.dumps({"sample_state": "ok"})),
    )


def test_outcome_uses_run_rates_and_requires_a_snapshot(tmp_path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("no browser")

    monkeypatch.setattr("api.collection_settings.collect_browser_answer", boom)
    client = make_client(tmp_path)
    project = _bootstrap(client)
    generated = client.post(f"/api/projects/{project['id']}/geo/questions/generate", json={"llm": False}).json()
    enabled = client.put("/api/geo/channels/chatgpt_web", json={"enabled": True, "timeout_seconds": 20, "concurrency": 1, "session_note": "ci-note"})
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True
    assert enabled.json()["timeout_seconds"] == 20
    baseline = client.post(
        f"/api/projects/{project['id']}/geo/baselines",
        json={
            "question_set_id": generated["question_set"]["id"],
            "engines": ["ChatGPT"],
            "language": "zh-CN",
            "region": "美国",
            "sample_count": 1,
            "web_sample_percent": 100,
        },
    )
    assert baseline.status_code == 201
    first = client.post(f"/api/projects/{project['id']}/geo/monitor", json={"baseline_id": baseline.json()["id"]})
    second = client.post(f"/api/projects/{project['id']}/geo/monitor", json={"baseline_id": baseline.json()["id"]})
    assert first.status_code == 200
    assert second.status_code == 200
    runs = client.get(f"/api/projects/{project['id']}/geo/runs").json()
    assert len(runs) >= 2
    ordered = sorted(runs, key=lambda item: item["id"])
    db = client.app.state.database
    _mark_k(db, ordered[0]["id"], 0)
    _mark_k(db, ordered[1]["id"], 1)
    attempts = client.get(f"/api/projects/{project['id']}/geo/attempts?run_id={ordered[1]['id']}").json()
    web = [item for item in attempts if item["engine"] == "ChatGPT 网页"]
    assert web
    assert all(item["error_code"] == "browser_unavailable" for item in web)
    assert json.loads(web[0]["request_params_json"])["sampled"] is True

    trends = client.get(f"/api/projects/{project['id']}/geo/trends").json()
    assert trends["config_hash"]
    assert [item["run_id"] for item in trends["series"]] == [ordered[0]["id"], ordered[1]["id"]]
    assert trends["series"][0]["k_mention"] == 0.0
    assert trends["series"][1]["k_mention"] == 100.0
    assert trends["excluded"] == []

    playbooks = client.get("/api/playbooks").json()
    version_id = next(item["latest_version_id"] for item in playbooks if item["code"] == "PB-004")
    action = client.post(
        f"/api/projects/{project['id']}/plan-actions",
        json={"playbook_version_id": version_id, "action": "补 FAQ", "priority": "P1"},
    )
    assert action.status_code == 201
    missing = client.post(f"/api/plan-actions/{action.json()['id']}/outcomes", json={})
    assert missing.status_code == 400
    outcome = client.post(
        f"/api/plan-actions/{action.json()['id']}/outcomes",
        json={"before_run_id": ordered[0]["id"], "after_run_id": ordered[1]["id"], "metric_name": "k_mention_rate"},
    )
    assert outcome.status_code == 201
    recorded = outcome.json()
    assert recorded["delta"] == 100
    assert recorded["success"] == 1
    assert recorded["before_k_rate"] == 0
    assert recorded["after_k_rate"] == 100
    assert recorded["before_run_id"] == ordered[0]["id"]
    assert recorded["after_run_id"] == ordered[1]["id"]
    detail = client.get(f"/api/playbooks/{next(item['id'] for item in playbooks if item['code'] == 'PB-004')}").json()
    usage = next(item for item in detail["version_usage"] if item["version_id"] == version_id)
    assert usage["projects"][0]["success"] == 1
    assert usage["projects"][0]["delta"] == 100
    plan = client.get(f"/api/projects/{project['id']}/plan").json()
    assert plan[0]["outcome_after_run_id"] == ordered[1]["id"]
    assert plan[0]["outcome_delta"] == 100
    preview = client.get(f"/reports/{project['id']}/preview")
    assert "闭环结果" in preview.text
    assert "达成" in preview.text
