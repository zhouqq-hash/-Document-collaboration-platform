import io
import json

from app import ai, ai_review, db
from app.ai_review import apply_checklist_result, parse_review_result
from app.models import Document, DocumentAiReview, User
from app.review_templates import get_template
from conftest import create_document, login


def _configure_ai(app):
    app.config["COSMOS_API_KEY"] = "test-key"
    app.config["COSMOS_MODEL"] = "test-model"


def _create_document(client, title, content, category_id=1, owner_id=2):
    login(client, "admin", "admin123")
    return client.post(
        "/api/documents",
        data={
            "title": title,
            "category_id": str(category_id),
            "owner_id": str(owner_id),
            "changelog": "初始版本",
            "description": "",
            "file": (io.BytesIO(content), "document.txt"),
        },
        content_type="multipart/form-data",
    )


def test_document_qa_requires_login(client):
    response = client.post(
        "/api/documents/1/ai/qa", json={"question": "你好"}
    )
    assert response.status_code == 401


def test_document_qa_without_key_returns_503(app, client, monkeypatch):
    monkeypatch.delenv("COSMOS_API_KEY", raising=False)
    app.config["COSMOS_API_KEY"] = ""
    create_document(client)

    response = client.post(
        "/api/documents/1/ai/qa",
        json={"question": "这份文档讲了什么？"},
    )

    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "ai_not_configured"


def test_manual_review_without_key_leaves_manual_fallback_record(
    app, client, monkeypatch
):
    monkeypatch.delenv("COSMOS_API_KEY", raising=False)
    app.config["COSMOS_API_KEY"] = ""
    create_document(client)

    response = client.post("/api/documents/1/ai/review", json={})
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "ai_not_configured"

    reviews = client.get("/api/documents/1/ai/reviews").get_json()["data"]
    assert len(reviews) == 1
    assert reviews[0]["status"] == "skipped"
    assert reviews[0]["manual_fallback_available"] is True
    assert "人工兜底" in reviews[0]["error"]


def test_document_qa_sends_document_text(app, client, monkeypatch):
    create_document(client)
    _configure_ai(app)
    captured = {}

    def fake_chat(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return "文档第一版的内容是 first version。"

    monkeypatch.setattr(ai, "chat", fake_chat)

    response = client.post(
        "/api/documents/1/ai/qa",
        json={"question": "文档内容是什么？"},
    )

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["answer"].startswith("文档第一版的内容")
    assert payload["version_number"] == 1
    assert payload["truncated"] is False
    assert "first version" in captured["messages"][0]["content"]
    assert captured["messages"][-1]["content"] == "文档内容是什么？"


def test_document_review_requires_owner(app, client):
    create_document(client)
    login(client, "other", "other123")

    response = client.post("/api/documents/1/ai/review", json={})

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "permission_denied"


def test_document_review_saves_result(app, client, monkeypatch):
    create_document(client)
    login(client, "teacher", "teacher123")
    _configure_ai(app)

    review_payload = {
        "verdict": "risk",
        "summary": "发现一处前后矛盾",
        "issues": [
            {
                "severity": "high",
                "category": "矛盾",
                "location": "第 1 段",
                "description": "学分总数前后不一致",
                "suggestion": "统一为 160 学分",
            }
        ],
        "spec_checks": [],
        "changes": [{"type": "修改", "description": "调整了学分说明"}],
    }

    def fake_chat(messages, **kwargs):
        assert "first version" in messages[1]["content"]
        return json.dumps(review_payload, ensure_ascii=False)

    monkeypatch.setattr(ai, "chat", fake_chat)

    response = client.post(
        "/api/documents/1/ai/review",
        json={"version_id": 1, "spec_document_ids": []},
    )

    assert response.status_code == 201
    review = response.get_json()["data"]
    assert review["verdict"] == "risk"
    assert review["result"]["issues"][0]["description"] == "学分总数前后不一致"
    assert review["requester"]["username"] == "teacher"

    with app.app_context():
        saved = db.session.query(DocumentAiReview).one()
        assert saved.version_id == 1
        assert saved.verdict == "risk"


def test_document_review_reads_spec_document(app, client, monkeypatch):
    create_document(client)
    spec_response = _create_document(
        client,
        "教学规范",
        "规范要求：总学分不少于160".encode("utf-8"),
        category_id=2,
        owner_id=1,
    )
    spec_id = spec_response.get_json()["data"]["id"]
    _configure_ai(app)
    captured = {}

    def fake_chat(messages, **kwargs):
        captured["user"] = messages[1]["content"]
        return json.dumps(
            {
                "verdict": "pass",
                "summary": "符合规范",
                "issues": [],
                "spec_checks": [
                    {
                        "spec": "教学规范",
                        "compliant": True,
                        "note": "学分满足要求",
                    }
                ],
                "changes": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(ai, "chat", fake_chat)

    response = client.post(
        "/api/documents/1/ai/review",
        json={"spec_document_ids": [spec_id]},
    )

    assert response.status_code == 201
    assert "规范要求：总学分不少于160" in captured["user"]
    result = response.get_json()["data"]["result"]
    assert result["checked_spec_ids"] == [spec_id]


def test_document_review_history(app, client, monkeypatch):
    create_document(client)
    _configure_ai(app)
    monkeypatch.setattr(
        ai,
        "chat",
        lambda messages, **kwargs: (
            '{"verdict":"pass","summary":"没问题",'
            '"issues":[],"spec_checks":[],"changes":[]}'
        ),
    )

    created = client.post("/api/documents/1/ai/review", json={})
    assert created.status_code == 201

    response = client.get("/api/documents/1/ai/reviews")
    assert response.status_code == 200
    reviews = response.get_json()["data"]
    assert len(reviews) == 1
    assert reviews[0]["verdict"] == "pass"
    assert reviews[0]["result"]["summary"] == "没问题"


def test_review_templates_are_selectable_per_category(client):
    login(client, "admin", "admin123")

    templates = client.get("/api/review-templates")
    assert templates.status_code == 200
    keys = {item["key"] for item in templates.get_json()["data"]}
    assert keys == {"generic_document_v1", "syllabus_v1"}

    updated = client.patch(
        "/api/categories/2",
        json={"review_template_key": "syllabus_v1"},
    )
    assert updated.status_code == 200
    data = updated.get_json()["data"]
    assert data["review_template_key"] == "syllabus_v1"
    assert data["review_template_name"] == "教学大纲规范检查"

    invalid = client.patch(
        "/api/categories/2",
        json={"review_template_key": "not-a-template"},
    )
    assert invalid.status_code == 400
    assert invalid.get_json()["error"]["code"] == "invalid_template"


def test_structured_checklist_is_prompted_and_snapshotted(
    app, client, monkeypatch
):
    create_document(client)
    client.patch(
        "/api/categories/1",
        json={"review_template_key": "syllabus_v1"},
    )
    _configure_ai(app)
    captured = {}

    def fake_chat(messages, **kwargs):
        captured["system"] = messages[0]["content"]
        captured["user"] = messages[1]["content"]
        return json.dumps(
            {
                "summary": "发现学时不一致",
                "check_results": [
                    {
                        "rule_id": "hours_total",
                        "status": "fail",
                        "location": "总学时",
                        "evidence": "48 与 16+12+12 不一致",
                        "explanation": "总学时多出 8",
                        "suggestion": "统一学时",
                    }
                ],
                "spec_checks": [],
                "changes": [],
                "previous_issue_checks": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(ai, "chat", fake_chat)
    response = client.post("/api/documents/1/ai/review", json={})

    assert response.status_code == 201
    review = response.get_json()["data"]
    assert review["review_template_key"] == "syllabus_v1"
    assert review["review_template_version"] == "1.0"
    assert review["review_template_name"] == "教学大纲规范检查"
    assert len(review["checklist"]) == 10
    assert review["verdict"] == "risk"
    assert review["result"]["check_results"][0]["rule_id"] == (
        "basic_completeness"
    )
    assert review["result"]["checklist_summary"] == {
        "total": 10,
        "pass": 0,
        "fail": 1,
        "unknown": 9,
        "available": True,
    }
    assert review["result"]["issues"][0]["rule_id"] == "hours_total"
    assert "逐项执行用户提供的检查清单" in captured["system"]
    assert "hours_total" in captured["user"]
    assert "教学大纲规范检查" in captured["user"]


def test_backend_derives_verdict_from_required_checklist_items():
    checklist = get_template("syllabus_v1")["rules"]

    partial = apply_checklist_result(
        {
            "check_results": [
                {
                    "rule_id": "basic_completeness",
                    "status": "pass",
                    "evidence": "核心章节齐全",
                }
            ]
        },
        checklist,
    )
    assert partial["verdict"] == "unknown"
    assert partial["checklist_summary"]["unknown"] == 9
    assert {
        item["rule_id"] for item in partial["check_results"]
    } == {rule["id"] for rule in checklist}

    all_pass = apply_checklist_result(
        {
            "check_results": [
                {"rule_id": rule["id"], "status": "pass"}
                for rule in checklist
            ]
        },
        checklist,
    )
    assert all_pass["verdict"] == "pass"
    assert all_pass["checklist_summary"]["pass"] == 10


def test_review_parser_unwraps_json_string_responses():
    payload = {
        "summary": "发现学时不一致",
        "check_results": [
            {
                "rule_id": "hours_total",
                "status": "fail",
                "evidence": "72 不等于 64",
            }
        ],
        "issues": [],
        "spec_checks": [],
        "changes": [],
        "previous_issue_checks": [],
    }

    result = parse_review_result(json.dumps(json.dumps(payload)))

    assert result.get("parse_error") is not True
    assert result["summary"] == "发现学时不一致"
    assert result["check_results"][0]["rule_id"] == "hours_total"


def _upload_new_version(client, document_id, content=b"second version"):
    return client.post(
        f"/api/documents/{document_id}/versions",
        data={
            "changelog": "第二版",
            "file": (io.BytesIO(content), "version-two.txt"),
        },
        content_type="multipart/form-data",
    )


def test_upload_version_creates_auto_review(app, client, monkeypatch):
    create_document(client)
    app.config["AI_AUTO_REVIEW_ENABLED"] = True
    app.config["AI_AUTO_REVIEW_SYNC"] = True
    _configure_ai(app)

    monkeypatch.setattr(
        ai,
        "chat",
        lambda messages, **kwargs: (
            '{"verdict":"pass","summary":"自动预审通过",'
            '"issues":[],"spec_checks":[],"changes":[]}'
        ),
    )

    response = _upload_new_version(client, 1)
    assert response.status_code == 201

    with app.app_context():
        review = db.session.query(DocumentAiReview).one()
        assert review.source == "auto"
        assert review.status == "done"
        assert review.version_id == 2
        assert review.verdict == "pass"
        assert review.human_decision == "pending"


def test_upload_version_skips_auto_review_without_key(
    app, client, monkeypatch
):
    create_document(client)
    app.config["AI_AUTO_REVIEW_ENABLED"] = True
    app.config["AI_AUTO_REVIEW_SYNC"] = True
    monkeypatch.delenv("COSMOS_API_KEY", raising=False)
    app.config["COSMOS_API_KEY"] = ""

    response = _upload_new_version(client, 1)
    assert response.status_code == 201

    with app.app_context():
        review = db.session.query(DocumentAiReview).one()
        assert review.source == "auto"
        assert review.status == "skipped"
        assert "COSMOS_API_KEY" in review.error_message


def test_category_default_specs_are_used(app, client, monkeypatch):
    create_document(client)
    spec_response = _create_document(
        client,
        "教学规范",
        "规范要求：总学分不少于160".encode("utf-8"),
        category_id=2,
        owner_id=1,
    )
    spec_id = spec_response.get_json()["data"]["id"]

    updated = client.patch(
        "/api/categories/1",
        json={"default_spec_document_ids": [spec_id]},
    )
    assert updated.status_code == 200
    category = updated.get_json()["data"]
    assert category["default_spec_document_ids"] == [spec_id]
    assert category["default_spec_documents"][0]["title"] == "教学规范"

    _configure_ai(app)
    captured = {}

    def fake_chat(messages, **kwargs):
        captured["user"] = messages[1]["content"]
        return (
            '{"verdict":"pass","summary":"符合规范",'
            '"issues":[],"spec_checks":[],"changes":[]}'
        )

    monkeypatch.setattr(ai, "chat", fake_chat)
    response = client.post("/api/documents/1/ai/review", json={})
    assert response.status_code == 201
    assert "规范要求：总学分不少于160" in captured["user"]
    assert response.get_json()["data"]["spec_document_ids"] == [spec_id]


def test_human_decision_pass_and_return(app, client, monkeypatch):
    create_document(client)
    _configure_ai(app)
    monkeypatch.setattr(
        ai,
        "chat",
        lambda messages, **kwargs: (
            '{"verdict":"risk","summary":"需要修改",'
            '"issues":[],"spec_checks":[],"changes":[]}'
        ),
    )

    created = client.post("/api/documents/1/ai/review", json={})
    assert created.status_code == 201
    review_id = created.get_json()["data"]["id"]

    missing_note = client.patch(
        f"/api/documents/1/ai/reviews/{review_id}/decision",
        json={"decision": "return"},
    )
    assert missing_note.status_code == 400

    returned = client.patch(
        f"/api/documents/1/ai/reviews/{review_id}/decision",
        json={"decision": "return", "note": "请统一学分说明"},
    )
    assert returned.status_code == 200
    data = returned.get_json()["data"]
    assert data["human_decision"] == "return"
    assert data["human_note"] == "请统一学分说明"
    assert data["human_reviewer"]["username"] == "admin"

    detail = client.get("/api/documents/1").get_json()["data"]
    assert detail["review_state"]["code"] == "changes_required"
    assert detail["review_state"]["review_id"] == review_id

    versions = client.get("/api/documents/1/versions").get_json()["data"]
    assert versions[0]["review"]["human_decision"] == "return"
    assert versions[0]["review"]["human_note"] == "请统一学分说明"

    passed = client.patch(
        f"/api/documents/1/ai/reviews/{review_id}/decision",
        json={"decision": "pass", "note": "已修改"},
    )
    assert passed.status_code == 200
    assert passed.get_json()["data"]["human_decision"] == "pass"

    approved = client.get("/api/documents/1").get_json()["data"]
    assert approved["review_state"]["code"] == "approved"
    versions = client.get("/api/documents/1/versions").get_json()["data"]
    assert versions[0]["review"]["human_decision"] == "pass"

    login(client, "other", "other123")
    denied = client.patch(
        f"/api/documents/1/ai/reviews/{review_id}/decision",
        json={"decision": "pass"},
    )
    assert denied.status_code == 403


def test_new_version_becomes_resubmission_and_review_links_previous(
    app, client, monkeypatch
):
    create_document(client)
    _configure_ai(app)
    monkeypatch.setattr(
        ai,
        "chat",
        lambda messages, **kwargs: json.dumps(
            {
                "verdict": "risk",
                "summary": "总学时不一致",
                "issues": [
                    {
                        "severity": "high",
                        "category": "矛盾",
                        "location": "总学时",
                        "evidence": "48 学时与 40 学时不一致",
                        "description": "总学时前后不一致",
                        "suggestion": "统一学时",
                    }
                ],
                "spec_checks": [],
                "changes": [],
                "previous_issue_checks": [],
            },
            ensure_ascii=False,
        ),
    )

    first_review = client.post(
        "/api/documents/1/ai/review", json={}
    ).get_json()["data"]
    returned = client.patch(
        f"/api/documents/1/ai/reviews/{first_review['id']}/decision",
        json={"decision": "return", "note": "请统一学时"},
    )
    assert returned.status_code == 200

    uploaded = _upload_new_version(
        client, 1, content=b"second version with 40 hours"
    )
    assert uploaded.status_code == 201

    detail = client.get("/api/documents/1").get_json()["data"]
    assert detail["review_state"]["code"] == "resubmitted"
    assert (
        detail["review_state"]["previous_review_id"]
        == first_review["id"]
    )

    captured = {}

    def fake_chat(messages, **kwargs):
        captured["prompt"] = messages[1]["content"]
        return json.dumps(
            {
                "verdict": "pass",
                "summary": "上次问题已解决",
                "issues": [],
                "spec_checks": [],
                "changes": [],
                "previous_issue_checks": [
                    {
                        "issue": "总学时前后不一致",
                        "status": "resolved",
                        "note": "已统一为 40 学时",
                    }
                ],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(ai, "chat", fake_chat)
    second_review = client.post(
        "/api/documents/1/ai/review", json={}
    )
    assert second_review.status_code == 201
    payload = second_review.get_json()["data"]
    assert payload["previous_review_id"] == first_review["id"]
    assert payload["previous_review"]["human_note"] == "请统一学时"
    assert (
        payload["result"]["previous_issue_checks"][0]["status"]
        == "resolved"
    )
    assert "上次人工退回" in captured["prompt"]
    assert "总学时前后不一致" in captured["prompt"]


def test_ai_unavailable_can_be_resolved_by_explicit_manual_fallback(
    app, client, monkeypatch
):
    monkeypatch.delenv("COSMOS_API_KEY", raising=False)
    app.config["COSMOS_API_KEY"] = ""
    created = _create_document(
        client, "AI 不可用流程", "需要人工审核".encode("utf-8")
    )
    document_id = created.get_json()["data"]["id"]

    with app.app_context():
        document = db.session.get(Document, document_id)
        teacher = User.query.filter_by(username="teacher").one()
        review = ai_review.create_review(
            document,
            document.current_version,
            teacher,
            source="auto",
        )
        review.status = "skipped"
        review.error_message = "模型网络不可用"
        db.session.commit()
        review_id = review.id

    endpoint = f"/api/documents/{document_id}/ai/reviews/{review_id}"
    denied = client.patch(f"{endpoint}/decision", json={"decision": "pass"})
    assert denied.status_code == 409
    assert denied.get_json()["error"]["code"] == "manual_fallback_required"

    missing_note = client.patch(
        f"{endpoint}/decision",
        json={
            "decision": "pass",
            "manual_fallback": True,
            "note": "",
        },
    )
    assert missing_note.status_code == 400
    assert missing_note.get_json()["error"]["code"] == "note_required"

    retry = client.post(f"{endpoint}/retry")
    assert retry.status_code == 503
    assert retry.get_json()["error"]["code"] == "ai_not_configured"

    approved = client.patch(
        f"{endpoint}/decision",
        json={
            "decision": "pass",
            "manual_fallback": True,
            "note": "已逐页对照学院模板人工核验",
        },
    )
    assert approved.status_code == 200
    assert approved.get_json()["data"]["human_decision"] == "pass"

    detail = client.get(f"/api/documents/{document_id}").get_json()["data"]
    assert detail["review_state"]["code"] == "approved"
    assert detail["review_state"]["error"] == "模型网络不可用"
