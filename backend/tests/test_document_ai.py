import io
import json

from app import ai, db
from app.models import DocumentAiReview
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

    passed = client.patch(
        f"/api/documents/1/ai/reviews/{review_id}/decision",
        json={"decision": "pass", "note": "已修改"},
    )
    assert passed.status_code == 200
    assert passed.get_json()["data"]["human_decision"] == "pass"

    login(client, "other", "other123")
    denied = client.patch(
        f"/api/documents/1/ai/reviews/{review_id}/decision",
        json={"decision": "pass"},
    )
    assert denied.status_code == 403
