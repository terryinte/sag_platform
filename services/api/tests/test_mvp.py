from fastapi.testclient import TestClient

from api.main import create_app


def make_client(tmp_path):
    return TestClient(create_app(tmp_path / "test.db"))


def test_demo_seed_creates_complete_mvp_dataset(tmp_path):
    client = make_client(tmp_path)

    seeded = client.post("/api/demo/seed", json={})
    assert seeded.status_code == 200
    project_id = seeded.json()["project_id"]

    dashboard = client.get(f"/api/projects/{project_id}/dashboard")
    assert dashboard.status_code == 200
    data = dashboard.json()
    assert data["commitments"]["total"] == 0
    assert data["geo"]["total"] == 36
    assert data["geo"]["mention_rate"] == 100.0
    assert data["assessment"]["overall_score"] is not None

    seo = client.get(f"/api/projects/{project_id}/seo").json()
    assert len(seo["metrics"]) >= 12
    assert {item["source"] for item in seo["metrics"]} >= {
        "GA4", "Google Search Console", "Bing Webmaster Tools", "百度搜索资源平台",
        "5118", "Ahrefs", "Semrush", "Screaming Frog", "PageSpeed Insights",
    }
    question_sets = client.get(f"/api/projects/{project_id}/geo/question-sets").json()
    questions = client.get(f"/api/geo/question-sets/{question_sets[0]['id']}/questions")
    assert len(questions.json()) == 3

    report = client.get(f"/reports/{project_id}/preview")
    assert report.status_code == 200
    assert "睿驰科技有限公司" in report.text
    assert "GEO 品牌提及率" in report.text
    assert "SEO 指标详细内容与时间序列" in report.text
    assert "指标作用与说明" in report.text
    assert "测评范围、工具与数据来源" in report.text
    assert "GA4" in report.text
    assert "DeepSeek / DeepSeek-V3" in report.text
    assert "测评方法与计算口径" in report.text
    assert "逐问题、逐平台判定明细" in report.text
    assert "GEO原始回答与复核证据" in report.text
    assert "推荐名单：1. 竞品A" in report.text


def test_client_project_commitment_and_report_flow(tmp_path):
    client = make_client(tmp_path)
    created_client = client.post(
        "/api/clients",
        json={
            "name": "Example Ltd",
            "brand_name": "Acme",
            "domain": "acme.example",
            "industry": "software",
        },
    )
    assert created_client.status_code == 201
    client_id = created_client.json()["id"]

    created_project = client.post(
        "/api/projects",
        json={
            "client_id": client_id,
            "name": "Q3 audit",
            "service_provider": "Agency",
            "period_start": "2026-07-01",
            "period_end": "2026-09-30",
        },
    )
    assert created_project.status_code == 201
    project_id = created_project.json()["id"]

    commitment = client.post(
        f"/api/projects/{project_id}/commitments",
        json={
            "category": "SEO",
            "metric_name": "Top 10 keywords",
            "target_value": 20,
            "unit": "keywords",
            "actual_value": 8,
            "achievement_status": "not_achieved",
            "evidence_source": "Ahrefs",
        },
    )
    assert commitment.status_code == 201
    updated_commitment = client.put(
        f"/api/commitments/{commitment.json()['id']}",
        json={
            "category": "SEO",
            "metric_name": "Top 10 keywords",
            "target_operator": ">=",
            "target_value": 20,
            "unit": "keywords",
            "due_date": "2026-09-30",
            "source_clause": "Contract clause",
            "actual_value": 12,
            "achievement_status": "partial",
            "evidence_source": "Ahrefs export",
            "notes": "Updated after verification",
        },
    )
    assert updated_commitment.status_code == 200
    assert updated_commitment.json()["actual_value"] == 12
    assert updated_commitment.json()["achievement_status"] == "partial"

    report = client.post(
        f"/api/projects/{project_id}/reports",
        json={
            "period_start": "2026-07-01",
            "period_end": "2026-09-30",
            "executive_summary": "Independent audit summary",
            "conclusion": "Contract target not achieved.",
            "recommendations": "Request delivery evidence.",
        },
    )
    assert report.status_code == 201
    fixed_report = client.get(f"/reports/{project_id}/{report.json()['id']}")
    assert fixed_report.status_code == 200
    assert "Independent audit summary" in fixed_report.text


def test_assessment_scores_saved_rankings_and_ai_responses(tmp_path):
    client = make_client(tmp_path)
    project_id = client.post("/api/demo/seed", json={}).json()["project_id"]

    assessment = client.get(f"/api/projects/{project_id}/assessment")

    assert assessment.status_code == 200
    body = assessment.json()
    assert body["overall_score"] is not None
    assert body["seo"]["score"] is not None
    assert body["geo"]["score"] is not None
    assert "缺失维度不补分" in body["scoring_note"]


def test_keyword_target_and_ranking_keep_region_and_language(tmp_path):
    client = make_client(tmp_path)
    project_id = client.post("/api/demo/seed", json={}).json()["project_id"]

    target = client.post(
        f"/api/projects/{project_id}/keyword-targets",
        json={"keyword": "工业空压机厂家", "engine": "baidu", "region_name": "上海", "language": "zh-CN"},
    )
    ranking = client.post(
        f"/api/projects/{project_id}/seo/rankings",
        json={"captured_at": "2026-07-26", "source": "5118", "keyword": "工业空压机厂家", "engine": "baidu", "region_name": "上海", "language": "zh-CN", "position": 5},
    )

    assert target.status_code == 201
    assert target.json()["region_name"] == "上海"
    assert ranking.status_code == 201
    assert ranking.json()["language"] == "zh-CN"


def test_csv_import_supports_chinese_and_english_headers(tmp_path):
    client = make_client(tmp_path)
    project_id = client.post("/api/demo/seed", json={}).json()["project_id"]

    response = client.post(
        f"/api/projects/{project_id}/seo/import",
        json={
            "filename": "rankings.csv",
            "default_captured_at": "2026-07-31",
            "default_source": "5118",
            "content": "关键词,排名,搜索量,搜索引擎\n工业空压机,7,1000,baidu\n节能改造,12,500,baidu\n",
        },
    )
    assert response.status_code == 200
    assert response.json()["rankings_imported"] == 2

    seo = client.get(f"/api/projects/{project_id}/seo").json()
    imported = [item for item in seo["rankings"] if item["captured_at"] == "2026-07-31"]
    assert {item["keyword"] for item in imported} == {"工业空压机", "节能改造"}


def test_geo_question_run_response_and_review_flow(tmp_path):
    client = make_client(tmp_path)
    project_id = client.post("/api/demo/seed", json={}).json()["project_id"]
    question_set = client.post(
        f"/api/projects/{project_id}/geo/question-sets",
        json={"name": "New baseline", "version": "v2.0", "status": "active"},
    ).json()
    question = client.post(
        f"/api/geo/question-sets/{question_set['id']}/questions",
        json={"intent": "比较期", "question": "哪些品牌值得比较？"},
    ).json()
    run = client.post(
        f"/api/projects/{project_id}/geo/runs",
        json={"question_set_id": question_set["id"], "run_at": "2026-07-31"},
    ).json()
    response = client.post(
        f"/api/geo/runs/{run['id']}/responses",
        json={
            "question_id": question["id"],
            "platform": "DeepSeek",
            "model": "manual",
            "raw_response": "1. 竞品A\n2. 睿驰科技",
        },
    )
    assert response.status_code == 201
    assert response.json()["brand_mentioned"] == 1

    reviewed = client.put(
        f"/api/geo/responses/{response.json()['id']}/review",
        json={
            "brand_mentioned": True,
            "mention_position": 2,
            "accurate": False,
            "recommended": True,
            "competitor_mentions": ["竞品A"],
            "misinformation": "产品线描述错误",
            "reviewer_notes": "人工复核",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["accurate"] == 0
    assert reviewed.json()["review_status"] == "reviewed"


def test_geo_batch_without_credentials_returns_auditable_failure(tmp_path):
    client = make_client(tmp_path)
    project_id = client.post("/api/demo/seed", json={}).json()["project_id"]
    question_set_id = client.get(
        f"/api/projects/{project_id}/geo/question-sets"
    ).json()[0]["id"]
    response = client.post(
        f"/api/projects/{project_id}/geo/runs/batch",
        json={
            "question_set_id": question_set_id,
            "run_at": "2026-07-31",
            "providers": [
                {
                    "platform": "DeepSeek",
                    "provider": "openrouter",
                    "model": "deepseek/example",
                }
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert "OPENROUTER_API_KEY" in response.json()["errors"][0]["message"]


def test_subscription_dashboard_reports_geo_decline_and_project_updates(tmp_path):
    client = make_client(tmp_path)
    project_id = client.post("/api/demo/seed", json={}).json()["project_id"]
    project = client.get(f"/api/projects/{project_id}").json()

    updated = client.put(
        f"/api/projects/{project_id}",
        json={
            "client_id": project["client_id"],
            "name": project["name"],
            "service_provider": project["service_provider"],
            "period_start": project["period_start"],
            "period_end": project["period_end"],
            "cadence": "quarterly",
            "subscription_status": "active",
            "alert_threshold": 20,
            "status": "active",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["cadence"] == "quarterly"
    assert updated.json()["subscription_status"] == "active"

    question_set_id = client.get(
        f"/api/projects/{project_id}/geo/question-sets"
    ).json()[0]["id"]
    questions = client.get(
        f"/api/geo/question-sets/{question_set_id}/questions"
    ).json()
    run = client.post(
        f"/api/projects/{project_id}/geo/runs",
        json={
            "question_set_id": question_set_id,
            "run_at": "2026-07-31",
            "status": "completed",
        },
    ).json()
    for question in questions:
        response = client.post(
            f"/api/geo/runs/{run['id']}/responses",
            json={
                "question_id": question["id"],
                "platform": "DeepSeek（演示）",
                "model": "demo-v2",
                "raw_response": "本次回答只提到其他供应商。",
            },
        )
        assert response.status_code == 201

    dashboard = client.get(f"/api/projects/{project_id}/dashboard").json()
    assert dashboard["geo"]["mention_rate"] == 0.0
    assert dashboard["geo"]["previous_mention_rate"] == 100.0
    assert dashboard["geo"]["change"] == -100.0
    assert any(item["type"] == "geo_decline" for item in dashboard["alerts"])
