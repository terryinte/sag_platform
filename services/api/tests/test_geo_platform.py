import math

import httpx
import pytest
from fastapi.testclient import TestClient

from api.collection_settings import probe_channel
from api.geo_platform import compute_config_hash, draft_questions, fields_from_judge
from api.main import create_app
from api.secret_box import decrypt_text, encrypt_text
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
    assert "function tabKey" in script.text
    assert "state.tabs.find" in script.text
    assert "data-open=\"dashboard\"" in script.text
    assert "answer:${extra.attemptId}" not in script.text
    assert "w-project" in script.text
    assert "readContents(panel, true)" in script.text
    assert "加入计划" in script.text
    assert "report-frame" in script.text
    assert 'data-nav="geo-check"' in page.text
    assert 'rel="icon"' in page.text
    icon = client.get("/favicon.ico")
    assert icon.status_code == 200
    assert icon.content.startswith(b"\x89PNG")


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


def test_questions_split_items_and_keep_every_competitor():
    drafts = draft_questions(
        {
            "brand_name": "UGREEN",
            "aliases": ["UGREEN"],
            "language": "en-US",
            "products": ["GaN chargers (Nexode 100W), USB-C hubs, power banks"],
            "selling_points": ["Fast charging, GaN tech, value for money：Selling points: compact and cool"],
            "competitors": ["Anker", "Baseus", "Belkin"],
        }
    )
    text = "\n".join(item["question"] for item in drafts)
    assert "What are the best GaN chargers (Nexode 100W) to buy?" in text
    assert "What are the best USB-C hubs to buy?" in text
    assert "What are the best power banks to buy?" in text
    assert "What are good alternatives to Anker?" in text
    assert "What are good alternatives to Baseus?" in text
    assert "What are good alternatives to Belkin?" in text
    assert "：" not in text
    assert "Selling points" not in text
    assert "is best for Fast charging, GaN" not in text
    assert all("UGREEN" not in item["question"] for item in drafts if item["probe_type"] == "K")


def test_bootstrap_saves_comma_separated_competitors(tmp_path):
    client = make_client(tmp_path)
    created = client.post(
        "/api/geo/bootstrap",
        json={
            "client_name": "U",
            "brand_name": "UGREEN",
            "domain": "ugreen.example",
            "language": "en-US",
            "competitors": ["Anker, Baseus|baseus.example, Belkin"],
            "project_name": "UGREEN US monitor",
            "key_contents": [
                {"kind": "产品线", "title": "GaN chargers (Nexode 100W), USB-C hubs, power banks", "body": "ignored description", "confirmed": True},
                {"kind": "卖点", "title": "Fast charging, GaN tech, value for money", "body": "Selling points: compact", "confirmed": True},
            ],
        },
    )
    assert created.status_code == 201
    project = created.json()
    assert project["name"] == "UGREEN US monitor"
    assert [item["name"] for item in project["competitors"]] == ["Anker", "Baseus", "Belkin"]
    generated = client.post(f"/api/projects/{project['id']}/geo/questions/generate", json={"llm": False})
    assert generated.status_code == 201
    text = "\n".join(item["question"] for item in generated.json()["questions"])
    assert "Baseus" in text and "Belkin" in text and "Anker" in text
    assert "Selling points" not in text
    assert "ignored description" not in text
    assert "：" not in text


def test_channel_secret_is_masked_and_refused_without_key(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sag_secret_key", "")
    monkeypatch.delenv("SAG_SECRET_KEY", raising=False)
    client = make_client(tmp_path)
    refused = client.put("/api/geo/channels/openai", json={"api_key": "sk-live-secret-1234", "enabled": True})
    assert refused.status_code == 400
    assert "SAG_SECRET_KEY" in refused.json()["detail"]

    monkeypatch.setattr(settings, "sag_secret_key", "unit-secret")
    token = encrypt_text("sk-live-secret-1234")
    assert "sk-live-secret-1234" not in token
    assert decrypt_text(token) == "sk-live-secret-1234"

    saved = client.put(
        "/api/geo/channels/openai",
        json={
            "api_key": "sk-stored-1111",
            "enabled": True,
            "model": "gpt-4.1-mini",
            "web_search": True,
            "region": "US",
            "language": "en-US",
            "concurrency": 2,
            "rate_limit_rpm": 15,
            "budget_cap_usd": 3,
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["key_last4"] == "1111"
    assert body["key_source"] == "stored"
    assert "sk-stored" not in saved.text
    row = client.app.state.database.fetch_one("SELECT api_key_enc FROM collection_channels WHERE channel_id = 'openai'")
    assert row["api_key_enc"]
    assert "sk-stored-1111" not in row["api_key_enc"]
    assert "sk-stored-1111" in decrypt_text(row["api_key_enc"])

    monkeypatch.setattr(settings, "openai_api_key", "sk-env-key-9999")
    listed = client.get("/api/geo/channels")
    assert listed.status_code == 200
    openai = next(item for item in listed.json() if item["id"] == "openai")
    assert openai["key_source"] == "env"
    assert openai["key_last4"] == "9999"
    assert "sk-env-key" not in listed.text
    assert "sk-stored" not in listed.text
    web = next(item for item in listed.json() if item["id"] == "chatgpt_web")
    assert web["status"] == "未实现"
    assert web["phase"] == "P1"


def test_probe_uses_env_key_and_reports_latency(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sag_secret_key", "unit-secret")
    client = make_client(tmp_path)
    saved = client.put("/api/geo/channels/openai", json={"api_key": "sk-stored-1111"})
    assert saved.status_code == 200

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer sk-env-key-9999"
        return httpx.Response(
            200,
            json={
                "model": "gpt-4.1-mini",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "pong"}]}],
            },
        )

    database = client.app.state.database
    result = probe_channel(
        database,
        "openai",
        {"OPENAI_API_KEY": "sk-env-key-9999"},
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert result["ok"] is True
    assert result["status"] == "已连接"
    assert result["latency_ms"] >= 0
    assert "sk-env" not in str(result)
    assert result["channel"]["key_last4"] == "9999"

    def explode(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("missing key must not call the network")

    missing = probe_channel(
        database,
        "deepseek",
        {},
        http_client=httpx.Client(transport=httpx.MockTransport(explode)),
    )
    assert missing["status"] == "未配置"
    web = probe_channel(database, "doubao", {}, http_client=httpx.Client(transport=httpx.MockTransport(explode)))
    assert web["status"] == "未实现"


def test_channel_settings_are_part_of_config_hash_and_web_sample_is_planned(tmp_path):
    client = make_client(tmp_path)
    project = _bootstrap(client)
    generated = client.post(
        f"/api/projects/{project['id']}/geo/questions/generate",
        json={"llm": False},
    ).json()
    payload = {
        "question_set_id": generated["question_set"]["id"],
        "engines": ["ChatGPT"],
        "language": "zh-CN",
        "region": "美国",
        "sample_count": 1,
        "web_sample_percent": 15,
    }
    first = client.post(f"/api/projects/{project['id']}/geo/baselines", json=payload)
    assert first.status_code == 201
    changed = client.put("/api/geo/channels/openai", json={"model": "gpt-hash-check", "web_search": False, "concurrency": 4, "rate_limit_rpm": 9})
    assert changed.status_code == 200
    second = client.post(f"/api/projects/{project['id']}/geo/baselines", json=payload)
    third = client.post(f"/api/projects/{project['id']}/geo/baselines", json=payload)
    assert first.json()["config_hash"] != second.json()["config_hash"]
    assert second.json()["config_hash"] == third.json()["config_hash"]
    snapshot = client.app.state.database.fetch_one("SELECT snapshot_json FROM geo_baselines WHERE id = ?", (second.json()["id"],))
    assert "gpt-hash-check" in snapshot["snapshot_json"]
    assert "sk-" not in snapshot["snapshot_json"]

    monitored = client.post(f"/api/projects/{project['id']}/geo/monitor", json={"baseline_id": second.json()["id"]})
    assert monitored.status_code == 200
    attempts = client.get(f"/api/projects/{project['id']}/geo/attempts").json()
    questions = generated["questions"]
    core = [item for item in questions if item["probe_type"] == "D" or item["intent"] in {"对比", "替代", "品牌"}]
    stubs = [item for item in attempts if item["error_code"] == "browser_stub"]
    assert len(stubs) == math.ceil(len(core) * 15 / 100)
    assert stubs[0]["engine"] == "ChatGPT 网页"
    assert all(item["error_code"] == "missing_api_key" for item in attempts if item["engine"] == "ChatGPT")
    detail = client.get(f"/api/geo/attempts/{stubs[0]['id']}").json()
    assert detail["attempt"]["error_code"] == "browser_stub"
    assert detail["response"] is None
    preview = client.get(f"/reports/{project['id']}/preview")
    assert preview.status_code == 200
    assert "API 通道" in preview.text
    assert "网页抽样" in preview.text
    assert "ChatGPT 网页" in preview.text

    estimate = client.post(
        f"/api/projects/{project['id']}/geo/budget-estimate",
        json={"engines": ["ChatGPT"], "sample_count": 1, "question_set_id": generated["question_set"]["id"]},
    )
    assert estimate.status_code == 200
    assert estimate.json()["api_calls"] == len(questions)
    assert estimate.json()["estimated_cost_usd"] == round(len(questions) * 0.01, 4)
    assert estimate.json()["spent_usd"] >= 0
