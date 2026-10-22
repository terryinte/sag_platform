import pytest
from fastapi.testclient import TestClient

from api.geo_platform import compute_config_hash, draft_questions, fields_from_judge
from api.main import create_app
from api.settings import settings
from analysis_engine.geo_judge import heuristic_judge


@pytest.fixture(autouse=True)
def blank_provider_keys(monkeypatch):
    for name in (
        "openai_api_key",
        "perplexity_api_key",
        "gemini_api_key",
        "anthropic_api_key",
        "deepseek_api_key",
        "kimi_api_key",
        "openrouter_api_key",
        "qianfan_access_key",
        "qianfan_secret_key",
    ):
        monkeypatch.setattr(settings, name, "")


def make_client(tmp_path):
    return TestClient(create_app(tmp_path / "geo.db"))


def _bootstrap(client, brand="绿联", domain="ugreen.example"):
    created = client.post(
        "/api/geo/bootstrap",
        json={
            "client_name": f"{brand} 客户",
            "brand_name": brand,
            "domain": domain,
            "industry": "3C",
            "aliases": f"{brand}, {domain}",
            "competitors": ["Anker|anker.example"],
            "language": "zh-CN",
            "region": "美国",
            "key_contents": [
                {"kind": "产品线", "title": "氮化镓充电器", "body": "多口", "confirmed": True},
                {"kind": "卖点", "title": "单口最高 100W", "body": "", "confirmed": True},
            ],
        },
    )
    assert created.status_code == 201
    return created.json()


def test_question_drafts_split_d_and_k_and_reject_branded_k():
    drafts = draft_questions(
        {
            "brand_name": "绿联",
            "aliases": ["绿联", "UGREEN"],
            "language": "zh-CN",
            "products": ["氮化镓充电器"],
            "selling_points": ["多口智能分配"],
            "competitors": ["Anker"],
        }
    )
    kinds = {item["probe_type"] for item in drafts}
    assert kinds == {"D", "K"}
    assert all("绿联" not in item["question"] and "UGREEN" not in item["question"] for item in drafts if item["probe_type"] == "K")
    assert any("绿联" in item["question"] for item in drafts if item["probe_type"] == "D")


def test_generate_edit_hash_and_monitor_without_keys(tmp_path):
    client = make_client(tmp_path)
    project = _bootstrap(client)
    generated = client.post(
        f"/api/projects/{project['id']}/geo/questions/generate",
        json={"name": "自动问题库", "llm": False},
    )
    assert generated.status_code == 201
    body = generated.json()
    assert body["source"] == "template"
    questions = body["questions"]
    assert {item["probe_type"] for item in questions} == {"D", "K"}

    branded = client.put(
        f"/api/geo/questions/{questions[0]['id']}",
        json={
            "intent": "发现",
            "question": "绿联充电器怎么样？",
            "probe_type": "K",
            "language": "zh-CN",
        },
    )
    assert branded.status_code == 400

    neutral = next(item for item in questions if item["probe_type"] == "K")
    edited = client.put(
        f"/api/geo/questions/{neutral['id']}",
        json={
            "intent": neutral["intent"],
            "question": "出差时怎么选多口充电器？",
            "probe_type": "K",
            "language": "zh-CN",
            "rationale": "人工改写",
        },
    )
    assert edited.status_code == 200
    assert edited.json()["question"] == "出差时怎么选多口充电器？"

    baseline = client.post(
        f"/api/projects/{project['id']}/geo/baselines",
        json={
            "question_set_id": body["question_set"]["id"],
            "engines": ["ChatGPT", "DeepSeek"],
            "language": "zh-CN",
            "region": "美国",
            "sample_count": 1,
        },
    )
    assert baseline.status_code == 201
    first_hash = baseline.json()["config_hash"]
    again = client.post(
        f"/api/projects/{project['id']}/geo/baselines",
        json={
            "question_set_id": body["question_set"]["id"],
            "engines": ["DeepSeek", "ChatGPT"],
            "language": "zh-CN",
            "region": "美国",
            "sample_count": 1,
        },
    )
    changed = client.post(
        f"/api/projects/{project['id']}/geo/baselines",
        json={
            "question_set_id": body["question_set"]["id"],
            "engines": ["ChatGPT"],
            "language": "zh-CN",
            "region": "美国",
            "sample_count": 1,
        },
    )
    assert again.json()["config_hash"] == first_hash
    assert changed.json()["config_hash"] != first_hash

    monitored = client.post(
        f"/api/projects/{project['id']}/geo/monitor",
        json={"baseline_id": baseline.json()["id"]},
    )
    assert monitored.status_code == 200
    assert monitored.json()["status"] in {"degraded", "skipped"}
    attempts = client.get(f"/api/projects/{project['id']}/geo/attempts").json()
    assert len(attempts) == len(questions) * 2
    assert all(item["error_code"] == "missing_api_key" for item in attempts)
    assert all(item["config_hash"] == first_hash for item in attempts)
    visibility = client.get(f"/api/projects/{project['id']}/geo/visibility").json()
    assert visibility["project_id"] == project["id"]
    assert visibility["n_mock"] == len(attempts)
    assert visibility["n_valid"] == 0
    assert visibility["k"]["mention_rate"] is None


def test_visibility_is_scoped_to_each_project(tmp_path):
    client = make_client(tmp_path)
    first = _bootstrap(client, "甲品牌", "a.example")
    second = _bootstrap(client, "乙品牌", "b.example")
    for project, mentioned in ((first, True), (second, False)):
        generated = client.post(
            f"/api/projects/{project['id']}/geo/questions/generate",
            json={"llm": False},
        ).json()
        question = next(item for item in generated["questions"] if item["probe_type"] == "K")
        run = client.post(
            f"/api/projects/{project['id']}/geo/runs",
            json={"question_set_id": generated["question_set"]["id"], "run_at": "2026-10-22", "status": "completed"},
        ).json()
        text = f"{project['brand_name']} 值得看看。" if mentioned else "这里只讨论其他选择。"
        saved = client.post(
            f"/api/geo/runs/{run['id']}/responses",
            json={"question_id": question["id"], "platform": "DeepSeek", "model": "manual", "raw_response": text},
        )
        assert saved.status_code == 201
    first_view = client.get(f"/api/projects/{first['id']}/geo/visibility").json()
    second_view = client.get(f"/api/projects/{second['id']}/geo/visibility").json()
    assert first_view["brand_name"] == "甲品牌"
    assert second_view["brand_name"] == "乙品牌"
    assert first_view["k"]["mention_rate"] == 100.0
    assert second_view["k"]["mention_rate"] == 0.0


def test_playbook_version_stays_pinned_and_records_outcome(tmp_path):
    client = make_client(tmp_path)
    project = _bootstrap(client)
    library = client.get("/api/playbooks")
    assert library.status_code == 200
    playbook = next(item for item in library.json() if item["code"] == "PB-004")
    version_id = playbook["latest_version_id"]
    action = client.post(
        f"/api/projects/{project['id']}/plan-actions",
        json={
            "playbook_version_id": version_id,
            "priority": "P0",
            "action": "补 FAQ",
            "acceptance": "引用上升",
        },
    )
    assert action.status_code == 201
    assert action.json()["playbook_version_id"] == version_id
    upgraded = client.post(
        f"/api/playbooks/{playbook['id']}/versions",
        json={
            "trigger_condition": "占比低于 3%",
            "steps": "增加一个核对步骤",
            "acceptance_metric": "引用次数上升",
            "change_note": "收紧阈值",
            "status": "已发布",
        },
    )
    assert upgraded.status_code == 201
    assert upgraded.json()["version"] == playbook["latest_version"] + 1
    still = client.get(f"/api/projects/{project['id']}/plan").json()[0]
    assert still["playbook_version_id"] == version_id
    outcome = client.post(
        f"/api/plan-actions/{action.json()['id']}/outcomes",
        json={"before_value": 10, "after_value": 16, "sample_n": 30, "note": "下期复测"},
    )
    assert outcome.status_code == 201
    assert outcome.json()["delta"] == 6
    assert outcome.json()["playbook_version_id"] == version_id
    detail = client.get(f"/api/playbooks/{playbook['id']}").json()
    assert any(item["version"] == playbook["latest_version"] + 1 for item in detail["versions"])
    assert detail["outcomes"][0]["delta"] == 6


def test_human_review_appends_revision(tmp_path):
    client = make_client(tmp_path)
    project_id = client.post("/api/demo/seed", json={}).json()["project_id"]
    question_set = client.get(f"/api/projects/{project_id}/geo/question-sets").json()[0]
    question = client.get(f"/api/geo/question-sets/{question_set['id']}/questions").json()[0]
    run = client.post(
        f"/api/projects/{project_id}/geo/runs",
        json={"question_set_id": question_set["id"], "run_at": "2026-10-22"},
    ).json()
    response = client.post(
        f"/api/geo/runs/{run['id']}/responses",
        json={"question_id": question["id"], "platform": "DeepSeek", "model": "manual", "raw_response": "1. 竞品A\n2. 睿驰科技"},
    ).json()
    reviewed = client.put(
        f"/api/geo/responses/{response['id']}/review",
        json={
            "brand_mentioned": True,
            "mention_position": 2,
            "accurate": True,
            "recommended": False,
            "competitor_mentions": ["竞品A"],
            "reviewer_notes": "同意初判",
        },
    )
    assert reviewed.status_code == 200
    revisions = client.get(f"/api/geo/responses/{response['id']}/revisions").json()
    assert revisions[-1]["reviewer"] == "human"
    assert revisions[-1]["result"]["reviewer_notes"] == "同意初判"


def test_homepage_opens_tabbed_shell(tmp_path):
    client = make_client(tmp_path)
    page = client.get("/")
    script = client.get("/geo-static/app.js")
    assert page.status_code == 200
    assert "SAG 测评台" in page.text
    assert "GEO检测" in page.text
    assert "/api/demo/seed" in page.text
    assert "function openTab" in script.text
    assert "state.tabs.find" in script.text
    assert "data-open=\"dashboard\"" in script.text


def test_judge_fields_follow_validated_evidence():
    judged = heuristic_judge(
        "最好的选择是绿联。Anker 也常见。",
        [
            {"name": "绿联", "role": "brand", "aliases": ["绿联"]},
            {"name": "Anker", "role": "competitor", "aliases": []},
        ],
    )
    fields = fields_from_judge("绿联", ["绿联"], judged)
    assert fields["brand_mentioned"] is True
    assert fields["mention_position"] == 1
    assert fields["recommended"] is True
    assert fields["competitor_mentions"] == ["Anker"]
    same = compute_config_hash({"engines": ["A", "B"], "sample_count": 1})
    assert same == compute_config_hash({"sample_count": 1, "engines": ["A", "B"]})
