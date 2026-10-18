import io

from datetime import timedelta

from conftest import login

from app import ai, db
from app.models import QaTopic, utcnow


def create_topic(client, title="讨论：课程大纲是否调整", username="teacher", password="teacher123"):
    login(client, username, password)
    return client.post(
        "/api/qa/topics",
        json={"title": title, "description": "这是话题说明"},
    )


def post_statement(client, topic_id, content, position="agree"):
    return client.post(
        f"/api/qa/topics/{topic_id}/statements",
        json={"content": content, "position": position},
    )


def create_document(client, title="关联文档"):
    login(client, "admin", "admin123")
    return client.post(
        "/api/documents",
        data={
            "title": title,
            "category_id": "1",
            "owner_id": "2",
            "changelog": "初始版本",
            "description": "用于话题关联测试",
            "file": (io.BytesIO(b"document content"), "doc.txt"),
        },
        content_type="multipart/form-data",
    ).get_json()["data"]


def test_qa_unauthorized_returns_401(client):
    response = client.get("/api/qa/topics")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthorized"


def test_create_topic(client):
    response = create_topic(client)
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["title"] == "讨论：课程大纲是否调整"
    assert data["status"] == "open"
    assert data["creator"]["username"] == "teacher"
    assert data["statement_count"] == 0


def test_create_topic_requires_title(client):
    login(client)
    response = client.post("/api/qa/topics", json={"title": "  "})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_title"


def test_list_topics_orders_by_latest_activity(client):
    first = create_topic(client, "第一个话题").get_json()["data"]
    second = create_topic(client, "第二个话题").get_json()["data"]
    post_statement(client, first["id"], "补充一条发言")

    topics = client.get("/api/qa/topics").get_json()["data"]["items"]
    assert [topic["id"] for topic in topics] == [first["id"], second["id"]]
    assert topics[0]["statement_count"] == 1
    assert topics[0]["speaker_count"] == 1


def test_topic_detail_returns_timeline_in_ascending_order(client):
    topic = create_topic(client).get_json()["data"]
    first = post_statement(client, topic["id"], "第一条").get_json()["data"]
    second = post_statement(client, topic["id"], "第二条").get_json()["data"]

    detail = client.get(f"/api/qa/topics/{topic['id']}").get_json()["data"]
    assert [s["id"] for s in detail["statements"]] == [first["id"], second["id"]]
    assert detail["statements"][0]["author"]["username"] == "teacher"


def test_statement_validation(client):
    topic = create_topic(client).get_json()["data"]

    empty = client.post(
        f"/api/qa/topics/{topic['id']}/statements",
        json={"content": "  ", "position": "agree"},
    )
    assert empty.status_code == 400
    assert empty.get_json()["error"]["code"] == "invalid_content"

    bad_position = client.post(
        f"/api/qa/topics/{topic['id']}/statements",
        json={"content": "有效内容", "position": "bogus"},
    )
    assert bad_position.status_code == 400
    assert bad_position.get_json()["error"]["code"] == "invalid_position"


def test_statement_defaults_to_neutral_position(client):
    topic = create_topic(client).get_json()["data"]
    response = client.post(
        f"/api/qa/topics/{topic['id']}/statements",
        json={"content": "还没想好，先看看"},
    )
    assert response.status_code == 201
    assert response.get_json()["data"]["position"] == "neutral"


def test_closed_topic_rejects_new_statement(client):
    topic = create_topic(client).get_json()["data"]
    closed = client.patch(
        f"/api/qa/topics/{topic['id']}", json={"status": "closed"}
    )
    assert closed.status_code == 200
    assert closed.get_json()["data"]["status"] == "closed"

    response = post_statement(client, topic["id"], "话题结束了还要发")
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "topic_closed"


def test_only_admin_or_creator_can_close_topic(client):
    topic = create_topic(client).get_json()["data"]  # creator = teacher
    client.post("/api/auth/logout")
    login(client, "other", "other123")

    forbidden = client.patch(
        f"/api/qa/topics/{topic['id']}", json={"status": "closed"}
    )
    assert forbidden.status_code == 403

    client.post("/api/auth/logout")
    login(client, "admin", "admin123")
    allowed = client.patch(
        f"/api/qa/topics/{topic['id']}", json={"status": "closed"}
    )
    assert allowed.status_code == 200


def test_summary_consensus_reached(client):
    topic = create_topic(client).get_json()["data"]
    post_statement(client, topic["id"], "赞成", "agree")
    client.post("/api/auth/logout")
    login(client, "other", "other123")
    post_statement(client, topic["id"], "也赞成", "agree")
    client.post("/api/auth/logout")
    login(client, "admin", "admin123")
    post_statement(client, topic["id"], "同意", "agree")

    summary = client.get(f"/api/qa/topics/{topic['id']}/summary").get_json()["data"]
    assert summary["statement_count"] == 3
    assert summary["speaker_count"] == 3
    assert summary["positions"] == {"agree": 3, "disagree": 0, "neutral": 0}
    assert summary["consensus_reached"] is True
    assert summary["consensus_position"] == "agree"
    assert "初步统一意见" in summary["summary_text"]


def test_summary_not_reached_on_tie(client):
    topic = create_topic(client).get_json()["data"]
    post_statement(client, topic["id"], "赞成", "agree")
    post_statement(client, topic["id"], "反对", "disagree")
    post_statement(client, topic["id"], "中立", "neutral")

    summary = client.get(f"/api/qa/topics/{topic['id']}/summary").get_json()["data"]
    assert summary["consensus_reached"] is False
    assert summary["consensus_position"] is None
    assert summary["dominant_position"] == "agree"
    assert "尚未统一" in summary["summary_text"]


def test_topic_not_found(client):
    login(client)
    assert client.get("/api/qa/topics/999").status_code == 404
    assert client.get("/api/qa/topics/999/summary").status_code == 404
    assert (
        client.post(
            "/api/qa/topics/999/statements",
            json={"content": "不存在的话题", "position": "agree"},
        ).status_code
        == 404
    )


def test_any_teacher_can_participate(client):
    topic = create_topic(client).get_json()["data"]
    client.post("/api/auth/logout")
    login(client, "other", "other123")
    response = post_statement(client, topic["id"], "其他教师也能发言", "disagree")
    assert response.status_code == 201
    assert response.get_json()["data"]["author"]["username"] == "other"


def test_create_topic_with_ends_at(client):
    login(client)
    response = client.post(
        "/api/qa/topics",
        json={
            "title": "定时结束的话题",
            "description": "到点自动结束",
            "ends_at": "2099-01-01T00:00:00Z",
        },
    )
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["ends_at"] is not None
    assert data["expired"] is False
    assert data["status"] == "open"


def test_create_topic_rejects_past_ends_at(client):
    login(client)
    response = client.post(
        "/api/qa/topics",
        json={"title": "过期结束时间", "ends_at": "2000-01-01T00:00:00Z"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_ends_at"


def test_create_topic_rejects_invalid_ends_at(client):
    login(client)
    response = client.post(
        "/api/qa/topics",
        json={"title": "非法结束时间", "ends_at": "not-a-date"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_ends_at"


def test_auto_close_blocks_statement_after_deadline(app, client):
    topic = create_topic(client).get_json()["data"]

    with app.app_context():
        db_topic = db.session.get(QaTopic, topic["id"])
        db_topic.ends_at = utcnow() - timedelta(seconds=1)
        db.session.commit()

    detail = client.get(f"/api/qa/topics/{topic['id']}").get_json()["data"]
    assert detail["status"] == "closed"
    assert detail["expired"] is True

    response = post_statement(client, topic["id"], "已经到点了")
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "topic_closed"


def test_patch_can_set_and_clear_ends_at(client):
    topic = create_topic(client).get_json()["data"]

    set_resp = client.patch(
        f"/api/qa/topics/{topic['id']}",
        json={"ends_at": "2099-01-01T00:00:00Z"},
    )
    assert set_resp.status_code == 200
    assert set_resp.get_json()["data"]["ends_at"] is not None

    clear_resp = client.patch(
        f"/api/qa/topics/{topic['id']}",
        json={"ends_at": None},
    )
    assert clear_resp.status_code == 200
    assert clear_resp.get_json()["data"]["ends_at"] is None


def test_patch_rejects_past_ends_at(client):
    topic = create_topic(client).get_json()["data"]
    response = client.patch(
        f"/api/qa/topics/{topic['id']}",
        json={"ends_at": "2000-01-01T00:00:00Z"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_ends_at"


def test_qa_category_crud(client):
    login(client, "admin", "admin123")

    created = client.post(
        "/api/qa/categories", json={"name": "教学安排", "sort_order": 1}
    )
    assert created.status_code == 201
    category_id = created.get_json()["data"]["id"]

    duplicate = client.post("/api/qa/categories", json={"name": "教学安排"})
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "name_exists"

    client.post("/api/auth/logout")
    login(client, "teacher", "teacher123")
    forbidden = client.post("/api/qa/categories", json={"name": "其他"})
    assert forbidden.status_code == 403

    client.post("/api/auth/logout")
    login(client, "admin", "admin123")
    renamed = client.patch(
        f"/api/qa/categories/{category_id}", json={"name": "教学安排A"}
    )
    assert renamed.status_code == 200
    assert renamed.get_json()["data"]["name"] == "教学安排A"


def test_topic_category_filter_and_search(client):
    login(client, "admin", "admin123")
    category = client.post(
        "/api/qa/categories", json={"name": "毕业设计"}
    ).get_json()["data"]

    topic = client.post(
        "/api/qa/topics",
        json={
            "title": "毕业论文是否需要中期检查",
            "description": "讨论中期检查的时间安排",
            "category_id": category["id"],
        },
    ).get_json()["data"]
    assert topic["category"]["id"] == category["id"]

    uncategorized = client.post(
        "/api/qa/topics", json={"title": "无分类话题"}
    ).get_json()["data"]
    assert uncategorized["category"] is None

    filtered = client.get(
        f"/api/qa/topics?category_id={category['id']}"
    ).get_json()["data"]["items"]
    assert [item["id"] for item in filtered] == [topic["id"]]

    none_filtered = client.get("/api/qa/topics?category_id=none").get_json()["data"][
        "items"
    ]
    assert [item["id"] for item in none_filtered] == [uncategorized["id"]]

    searched = client.get("/api/qa/topics?q=中期检查").get_json()["data"]["items"]
    assert [item["id"] for item in searched] == [topic["id"]]

    client.post(
        f"/api/qa/topics/{uncategorized['id']}/statements",
        json={"content": "这个话题谈考核改革", "position": "neutral"},
    )
    searched_content = client.get("/api/qa/topics?q=考核改革").get_json()["data"][
        "items"
    ]
    assert [item["id"] for item in searched_content] == [uncategorized["id"]]


def test_create_topic_rejects_missing_category(client):
    login(client)
    response = client.post(
        "/api/qa/topics", json={"title": "无效分类", "category_id": 999}
    )
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "category_not_found"


def test_qa_category_delete_requires_empty(client):
    login(client, "admin", "admin123")
    category = client.post(
        "/api/qa/categories", json={"name": "课程考核"}
    ).get_json()["data"]

    client.post(
        "/api/qa/topics",
        json={"title": "考核安排讨论", "category_id": category["id"]},
    )

    blocked = client.delete(f"/api/qa/categories/{category['id']}")
    assert blocked.status_code == 409
    assert blocked.get_json()["error"]["code"] == "category_has_topics"


def test_patch_topic_category(client):
    login(client, "admin", "admin123")
    category_a = client.post(
        "/api/qa/categories", json={"name": "分类A"}
    ).get_json()["data"]
    category_b = client.post(
        "/api/qa/categories", json={"name": "分类B"}
    ).get_json()["data"]

    topic = client.post(
        "/api/qa/topics",
        json={"title": "可移动话题", "category_id": category_a["id"]},
    ).get_json()["data"]

    moved = client.patch(
        f"/api/qa/topics/{topic['id']}", json={"category_id": category_b["id"]}
    )
    assert moved.status_code == 200
    assert moved.get_json()["data"]["category"]["id"] == category_b["id"]

    cleared = client.patch(
        f"/api/qa/topics/{topic['id']}", json={"category_id": None}
    )
    assert cleared.status_code == 200
    assert cleared.get_json()["data"]["category"] is None


def test_post_reply_statement(client):
    topic = create_topic(client).get_json()["data"]
    root = post_statement(client, topic["id"], "我赞成增加中期检查", "agree").get_json()[
        "data"
    ]

    reply = client.post(
        f"/api/qa/topics/{topic['id']}/statements",
        json={
            "content": "补充一下，检查放在第 8 周比较合适。",
            "position": "agree",
            "parent_id": root["id"],
        },
    )
    assert reply.status_code == 201
    data = reply.get_json()["data"]
    assert data["parent_id"] == root["id"]
    assert data["parent"]["id"] == root["id"]
    assert data["parent"]["author"]["username"] == "teacher"
    assert data["quoted"] is None

    detail = client.get(f"/api/qa/topics/{topic['id']}").get_json()["data"]
    assert detail["statement_count"] == 2
    assert detail["statements"][-1]["parent_id"] == root["id"]


def test_post_quote_statement(client):
    topic = create_topic(client).get_json()["data"]
    root = post_statement(client, topic["id"], "建议提前提交截止时间", "agree").get_json()[
        "data"
    ]

    quote = client.post(
        f"/api/qa/topics/{topic['id']}/statements",
        json={
            "content": "我同意这个观点。",
            "position": "agree",
            "quote_statement_id": root["id"],
        },
    )
    assert quote.status_code == 201
    data = quote.get_json()["data"]
    # 只给引用对象时，自动把被引用发言作为回复对象
    assert data["parent_id"] == root["id"]
    assert data["quote_statement_id"] == root["id"]
    assert data["quoted"]["id"] == root["id"]


def test_reply_requires_same_topic(client):
    first = create_topic(client, "第一个话题").get_json()["data"]
    root = post_statement(client, first["id"], "根发言", "neutral").get_json()["data"]

    second = create_topic(client, "第二个话题").get_json()["data"]
    response = client.post(
        f"/api/qa/topics/{second['id']}/statements",
        json={"content": "跨话题回复", "parent_id": root["id"]},
    )
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "statement_not_found"


def test_reply_rejects_invalid_parent(client):
    topic = create_topic(client).get_json()["data"]
    response = client.post(
        f"/api/qa/topics/{topic['id']}/statements",
        json={"content": "无效回复参数", "parent_id": "abc"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_parent"


def test_create_topic_linked_to_document(client):
    doc = create_document(client, "2026级培养计划")
    version = doc["current_version"]
    login(client, "teacher", "teacher123")

    response = client.post(
        "/api/qa/topics",
        json={
            "title": "培养计划学分是否需要调整",
            "document_id": doc["id"],
            "version_id": version["id"],
        },
    )
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["document"]["id"] == doc["id"]
    assert data["document"]["title"] == "2026级培养计划"
    assert data["version"]["id"] == version["id"]
    assert data["version"]["version_number"] == 1


def test_version_alone_derives_document(client):
    doc = create_document(client, "教学大纲")
    version = doc["current_version"]
    login(client, "teacher", "teacher123")

    response = client.post(
        "/api/qa/topics",
        json={"title": "只关联版本", "version_id": version["id"]},
    )
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["document"]["id"] == doc["id"]
    assert data["version"]["id"] == version["id"]


def test_version_must_belong_to_document(client):
    doc_a = create_document(client, "文档A")
    doc_b = create_document(client, "文档B")
    login(client, "teacher", "teacher123")

    response = client.post(
        "/api/qa/topics",
        json={
            "title": "版本不匹配",
            "document_id": doc_b["id"],
            "version_id": doc_a["current_version"]["id"],
        },
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "version_mismatch"


def test_create_topic_rejects_missing_document(client):
    login(client)
    response = client.post(
        "/api/qa/topics", json={"title": "文档不存在", "document_id": 999}
    )
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "document_not_found"


def test_list_topics_filters_by_document(client):
    doc = create_document(client, "筛选文档")
    login(client, "teacher", "teacher123")
    linked = client.post(
        "/api/qa/topics", json={"title": "关联话题", "document_id": doc["id"]}
    ).get_json()["data"]
    client.post("/api/qa/topics", json={"title": "未关联话题"})

    filtered = client.get(
        f"/api/qa/topics?document_id={doc['id']}"
    ).get_json()["data"]["items"]
    assert [item["id"] for item in filtered] == [linked["id"]]


def test_patch_topic_document_link(client):
    doc = create_document(client, "可调整文档")
    topic = create_topic(client, "可调整关联话题").get_json()["data"]

    linked = client.patch(
        f"/api/qa/topics/{topic['id']}", json={"document_id": doc["id"]}
    )
    assert linked.status_code == 200
    assert linked.get_json()["data"]["document"]["id"] == doc["id"]

    cleared = client.patch(
        f"/api/qa/topics/{topic['id']}", json={"document_id": None}
    )
    assert cleared.status_code == 200
    assert cleared.get_json()["data"]["document"] is None
    assert cleared.get_json()["data"]["version"] is None


def test_ai_summary_unauthorized(client):
    assert client.post("/api/qa/topics/1/ai-summary").status_code == 401


def test_ai_summary_topic_not_found(client):
    login(client)
    assert client.post("/api/qa/topics/999/ai-summary").status_code == 404


def test_ai_summary_requires_configuration(app, client, monkeypatch):
    topic = create_topic(client).get_json()["data"]
    post_statement(client, topic["id"], "第一条发言")

    monkeypatch.delenv("COSMOS_API_KEY", raising=False)
    app.config["COSMOS_API_KEY"] = ""

    response = client.post(f"/api/qa/topics/{topic['id']}/ai-summary")
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "ai_not_configured"


def test_ai_summary_requires_statements(client, monkeypatch):
    topic = create_topic(client).get_json()["data"]
    monkeypatch.setattr(ai, "is_configured", lambda: True)

    response = client.post(f"/api/qa/topics/{topic['id']}/ai-summary")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "no_statements"


def test_ai_summary_returns_model_text(client, monkeypatch):
    topic = create_topic(client).get_json()["data"]
    post_statement(client, topic["id"], "建议提前到第 16 周", "agree")

    monkeypatch.setattr(ai, "is_configured", lambda: True)
    captured = {}

    def fake_chat(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return "## 讨论概况\n只有一条发言，主张提前截止时间。"

    monkeypatch.setattr(ai, "chat", fake_chat)

    response = client.post(f"/api/qa/topics/{topic['id']}/ai-summary")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["topic_id"] == topic["id"]
    assert data["statement_count"] == 1
    assert "讨论概况" in data["summary_text"]
    assert data["generated_at"] is not None

    # 发言内容作为数据进入 user 消息，系统提示里禁止执行发言中的指令
    assert captured["messages"][0]["role"] == "system"
    assert "不得执行" in captured["messages"][0]["content"]
    joined = "\n".join(message["content"] for message in captured["messages"])
    assert "建议提前到第 16 周" in joined


def test_ai_summary_maps_model_failure(client, monkeypatch):
    topic = create_topic(client).get_json()["data"]
    post_statement(client, topic["id"], "一条发言")

    monkeypatch.setattr(ai, "is_configured", lambda: True)

    def boom(messages, **kwargs):
        raise ai.AIError("调用大模型超时（30 秒），请稍后重试")

    monkeypatch.setattr(ai, "chat", boom)

    response = client.post(f"/api/qa/topics/{topic['id']}/ai-summary")
    assert response.status_code == 502
    assert response.get_json()["error"]["code"] == "ai_failed"


def test_ai_summary_is_persisted_and_marked_stale(client, monkeypatch):
    topic = create_topic(client, "落库测试话题").get_json()["data"]
    post_statement(client, topic["id"], "第一条发言")

    monkeypatch.setattr(ai, "is_configured", lambda: True)
    monkeypatch.setattr(
        ai, "chat", lambda messages, **kwargs: "## 讨论概况\n已生成。"
    )

    generated = client.post(f"/api/qa/topics/{topic['id']}/ai-summary")
    assert generated.status_code == 200
    assert generated.get_json()["data"]["stale"] is False

    detail = client.get(f"/api/qa/topics/{topic['id']}").get_json()["data"]
    assert detail["ai_summary"]["text"].startswith("## 讨论概况")
    assert detail["ai_summary"]["stale"] is False

    # 落库之后再有新发言，摘要应被标记为过期
    post_statement(client, topic["id"], "第二条发言")
    detail = client.get(f"/api/qa/topics/{topic['id']}").get_json()["data"]
    assert detail["ai_summary"]["stale"] is True


def test_export_topic_markdown(client):
    topic = create_topic(client, "导出测试话题").get_json()["data"]
    post_statement(client, topic["id"], "建议提前到第 16 周", "agree")

    response = client.get(f"/api/qa/topics/{topic['id']}/export")
    assert response.status_code == 200
    assert "text/markdown" in response.headers["Content-Type"]
    assert "attachment" in response.headers["Content-Disposition"]

    body = response.get_data(as_text=True)
    assert "# 导出测试话题" in body
    assert "## 意见汇总（规则）" in body
    assert "## AI 决策摘要" in body
    assert "（未生成）" in body
    assert "## 讨论时间线" in body
    assert "建议提前到第 16 周" in body


def test_export_topic_requires_login_and_existing_topic(client):
    assert client.get("/api/qa/topics/1/export").status_code == 401
    login(client)
    assert client.get("/api/qa/topics/999/export").status_code == 404


def test_record_conclusion_permission_and_validation(client):
    topic = create_topic(client).get_json()["data"]

    empty = client.post(
        f"/api/qa/topics/{topic['id']}/conclusion", json={"text": "  "}
    )
    assert empty.status_code == 400
    assert empty.get_json()["error"]["code"] == "invalid_conclusion"

    no_doc = client.post(
        f"/api/qa/topics/{topic['id']}/conclusion",
        json={"text": "结论", "share_to_document": True},
    )
    assert no_doc.status_code == 400
    assert no_doc.get_json()["error"]["code"] == "no_linked_document"

    client.post("/api/auth/logout")
    login(client, "other", "other123")
    forbidden = client.post(
        f"/api/qa/topics/{topic['id']}/conclusion", json={"text": "别人补录"}
    )
    assert forbidden.status_code == 403

    client.post("/api/auth/logout")
    login(client, "admin", "admin123")
    allowed = client.post(
        f"/api/qa/topics/{topic['id']}/conclusion",
        json={"text": "管理员补录的结论"},
    )
    assert allowed.status_code == 200
    assert allowed.get_json()["data"]["conclusion"]["text"] == "管理员补录的结论"


def test_conclusion_is_stored_and_can_be_overwritten(client):
    doc = create_document(client, "结论文档")
    login(client, "teacher", "teacher123")
    topic = client.post(
        "/api/qa/topics", json={"title": "结论话题", "document_id": doc["id"]}
    ).get_json()["data"]

    first = client.post(
        f"/api/qa/topics/{topic['id']}/conclusion",
        json={"text": "初版结论", "share_to_document": True},
    )
    assert first.status_code == 200
    assert first.get_json()["data"]["conclusion"]["shared"] is True

    detail = client.get(f"/api/qa/topics/{topic['id']}").get_json()["data"]
    assert detail["conclusion"]["text"] == "初版结论"
    assert detail["conclusion"]["shared"] is True
    assert detail["conclusion"]["by"]["username"] == "teacher"
    assert detail["conclusion"]["at"] is not None

    # 重新补录会覆盖旧结论，并保留最新一次的作者与时间
    second = client.post(
        f"/api/qa/topics/{topic['id']}/conclusion",
        json={"text": "修订后的结论", "share_to_document": False},
    )
    assert second.status_code == 200
    assert second.get_json()["data"]["conclusion"]["shared"] is False

    detail = client.get(f"/api/qa/topics/{topic['id']}").get_json()["data"]
    assert detail["conclusion"]["text"] == "修订后的结论"
    assert detail["conclusion"]["shared"] is False


def test_document_decisions_endpoint(client):
    doc = create_document(client, "决议文档")
    login(client, "teacher", "teacher123")

    shared = client.post(
        "/api/qa/topics", json={"title": "已回写话题", "document_id": doc["id"]}
    ).get_json()["data"]
    private = client.post(
        "/api/qa/topics", json={"title": "仅话题内结论", "document_id": doc["id"]}
    ).get_json()["data"]
    unlinked = create_topic(client, "未关联话题").get_json()["data"]

    client.post(
        f"/api/qa/topics/{shared['id']}/conclusion",
        json={"text": "同意提前到第 16 周", "share_to_document": True},
    )
    client.post(
        f"/api/qa/topics/{private['id']}/conclusion",
        json={"text": "只在话题里保留"},
    )
    client.post(
        f"/api/qa/topics/{unlinked['id']}/conclusion", json={"text": "没有文档"}
    )

    response = client.get(f"/api/qa/decisions?document_id={doc['id']}")
    assert response.status_code == 200
    decisions = response.get_json()["data"]
    assert [item["topic_id"] for item in decisions] == [shared["id"]]
    assert decisions[0]["topic_title"] == "已回写话题"
    assert decisions[0]["conclusion"] == "同意提前到第 16 周"
    assert decisions[0]["by"]["username"] == "teacher"
    assert decisions[0]["at"] is not None

    # 导出里也要带上最终结论，形成完整的决策记录
    exported = client.get(f"/api/qa/topics/{shared['id']}/export")
    body = exported.get_data(as_text=True)
    assert "## 最终结论" in body
    assert "同意提前到第 16 周" in body
    assert "已回写关联文档" in body


def test_decisions_endpoint_requires_login_and_document(client):
    assert client.get("/api/qa/decisions?document_id=1").status_code == 401
    login(client)
    assert client.get("/api/qa/decisions").status_code == 400


def test_list_topics_pagination(client):
    for index in range(5):
        create_topic(client, f"分页话题{index}")

    first_page = client.get("/api/qa/topics?page=1&page_size=2").get_json()["data"]
    assert first_page["total"] == 5
    assert first_page["page"] == 1
    assert first_page["page_size"] == 2
    assert first_page["total_pages"] == 3
    assert len(first_page["items"]) == 2

    third_page = client.get("/api/qa/topics?page=3&page_size=2").get_json()["data"]
    assert len(third_page["items"]) == 1

    # page 非法回落到第 1 页，page_size 超上限收敛到最大值
    clamped = client.get("/api/qa/topics?page=0&page_size=999").get_json()["data"]
    assert clamped["page"] == 1
    assert clamped["page_size"] == 100


def test_list_topics_rejects_unknown_status(client):
    login(client)
    response = client.get("/api/qa/topics?status=bogus")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_status"


def test_list_topics_status_filter(client):
    topic = create_topic(client, "待结束话题").get_json()["data"]
    client.patch(f"/api/qa/topics/{topic['id']}", json={"status": "closed"})

    open_items = client.get("/api/qa/topics?status=open").get_json()["data"]["items"]
    assert topic["id"] not in [item["id"] for item in open_items]

    closed_items = client.get("/api/qa/topics?status=closed").get_json()["data"]["items"]
    assert [item["id"] for item in closed_items] == [topic["id"]]


def test_list_topics_status_filter_treats_expired_as_closed(app, client):
    topic = create_topic(client, "过期话题").get_json()["data"]
    with app.app_context():
        db_topic = db.session.get(QaTopic, topic["id"])
        db_topic.ends_at = utcnow() - timedelta(seconds=1)
        db.session.commit()

    open_items = client.get("/api/qa/topics?status=open").get_json()["data"]["items"]
    assert topic["id"] not in [item["id"] for item in open_items]

    closed_items = client.get("/api/qa/topics?status=closed").get_json()["data"]["items"]
    assert topic["id"] in [item["id"] for item in closed_items]


def test_hide_statement_requires_admin(client):
    topic = create_topic(client).get_json()["data"]
    statement = post_statement(client, topic["id"], "会被隐藏的发言").get_json()["data"]
    path = f"/api/qa/topics/{topic['id']}/statements/{statement['id']}"

    # 发起人自己也不行，只有管理员可以
    forbidden = client.patch(path, json={"hidden": True})
    assert forbidden.status_code == 403
    assert forbidden.get_json()["error"]["code"] == "permission_denied"

    client.post("/api/auth/logout")
    login(client, "other", "other123")
    assert client.patch(path, json={"hidden": True}).status_code == 403

    client.post("/api/auth/logout")
    login(client, "admin", "admin123")
    hidden = client.patch(path, json={"hidden": True, "reason": "跑题"})
    assert hidden.status_code == 200
    data = hidden.get_json()["data"]
    assert data["hidden"] is True
    assert data["hidden_by"]["username"] == "admin"
    assert data["hidden_reason"] == "跑题"


def test_hidden_statement_excluded_from_timeline_and_summary(client):
    topic = create_topic(client).get_json()["data"]
    keep = post_statement(client, topic["id"], "保留的观点", "agree").get_json()["data"]
    drop = post_statement(client, topic["id"], "要被隐藏的观点", "disagree").get_json()[
        "data"
    ]

    client.post("/api/auth/logout")
    login(client, "admin", "admin123")
    client.patch(
        f"/api/qa/topics/{topic['id']}/statements/{drop['id']}",
        json={"hidden": True, "reason": "违规"},
    )

    # 管理员仍然看得到被隐藏的发言（带标记），但统计只算可见的
    detail = client.get(f"/api/qa/topics/{topic['id']}").get_json()["data"]
    assert [item["id"] for item in detail["statements"]] == [keep["id"], drop["id"]]
    assert detail["statements"][1]["hidden"] is True
    assert detail["statement_count"] == 1
    assert detail["hidden_statement_count"] == 1
    assert detail["summary"]["positions"] == {"agree": 1, "disagree": 0, "neutral": 0}

    # 普通用户在时间线里完全看不到
    client.post("/api/auth/logout")
    login(client, "teacher", "teacher123")
    detail = client.get(f"/api/qa/topics/{topic['id']}").get_json()["data"]
    assert [item["id"] for item in detail["statements"]] == [keep["id"]]
    assert detail["statement_count"] == 1
    assert detail["hidden_statement_count"] == 1


def test_restore_hidden_statement(client):
    topic = create_topic(client).get_json()["data"]
    statement = post_statement(client, topic["id"], "先隐藏再恢复").get_json()["data"]

    client.post("/api/auth/logout")
    login(client, "admin", "admin123")
    client.patch(
        f"/api/qa/topics/{topic['id']}/statements/{statement['id']}",
        json={"hidden": True},
    )

    restored = client.patch(
        f"/api/qa/topics/{topic['id']}/statements/{statement['id']}",
        json={"hidden": False},
    )
    assert restored.status_code == 200
    data = restored.get_json()["data"]
    assert data["hidden"] is False
    assert data["hidden_by"] is None
    assert data["hidden_at"] is None

    detail = client.get(f"/api/qa/topics/{topic['id']}").get_json()["data"]
    assert detail["statement_count"] == 1
    assert detail["hidden_statement_count"] == 0


def test_statement_moderation_validation(client):
    topic = create_topic(client).get_json()["data"]
    statement = post_statement(client, topic["id"], "校验用发言").get_json()["data"]
    path = f"/api/qa/topics/{topic['id']}/statements/{statement['id']}"

    client.post("/api/auth/logout")
    login(client, "admin", "admin123")

    missing = client.patch(path, json={"reason": "没给 hidden"})
    assert missing.status_code == 400
    assert missing.get_json()["error"]["code"] == "invalid_hidden"

    too_long = client.patch(path, json={"hidden": True, "reason": "长" * 201})
    assert too_long.status_code == 400
    assert too_long.get_json()["error"]["code"] == "invalid_reason"

    not_hidden = client.patch(path, json={"hidden": False})
    assert not_hidden.status_code == 409
    assert not_hidden.get_json()["error"]["code"] == "not_hidden"

    assert client.patch(path, json={"hidden": True}).status_code == 200
    again = client.patch(path, json={"hidden": True})
    assert again.status_code == 409
    assert again.get_json()["error"]["code"] == "already_hidden"

    assert (
        client.patch(
            f"/api/qa/topics/999/statements/{statement['id']}", json={"hidden": True}
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/qa/topics/{topic['id']}/statements/999", json={"hidden": True}
        ).status_code
        == 404
    )

    # 发言不属于该话题时也不能操作
    other_topic = create_topic(client, "另一个话题").get_json()["data"]
    other_statement = post_statement(client, other_topic["id"], "另一个话题的发言").get_json()[
        "data"
    ]
    client.post("/api/auth/logout")
    login(client, "admin", "admin123")
    mismatch = client.patch(
        f"/api/qa/topics/{topic['id']}/statements/{other_statement['id']}",
        json={"hidden": True},
    )
    assert mismatch.status_code == 404


def test_export_excludes_hidden_statements(client):
    topic = create_topic(client, "导出隐藏测试").get_json()["data"]
    post_statement(client, topic["id"], "会保留的发言", "agree")
    drop = post_statement(client, topic["id"], "会被隐藏的发言", "disagree").get_json()[
        "data"
    ]

    client.post("/api/auth/logout")
    login(client, "admin", "admin123")
    client.patch(
        f"/api/qa/topics/{topic['id']}/statements/{drop['id']}",
        json={"hidden": True, "reason": "违规"},
    )

    body = client.get(f"/api/qa/topics/{topic['id']}/export").get_data(as_text=True)
    assert "会保留的发言" in body
    assert "会被隐藏的发言" not in body


def test_create_report_validation(client):
    topic = create_topic(client).get_json()["data"]
    own = post_statement(client, topic["id"], "我自己的发言").get_json()["data"]

    own_report = client.post(
        f"/api/qa/topics/{topic['id']}/statements/{own['id']}/reports",
        json={"reason": "自举报"},
    )
    assert own_report.status_code == 400
    assert own_report.get_json()["error"]["code"] == "cannot_report_own"

    client.post("/api/auth/logout")
    login(client, "other", "other123")
    path = f"/api/qa/topics/{topic['id']}/statements/{own['id']}/reports"

    empty = client.post(path, json={"reason": "  "})
    assert empty.status_code == 400
    assert empty.get_json()["error"]["code"] == "invalid_reason"

    too_long = client.post(path, json={"reason": "长" * 501})
    assert too_long.status_code == 400
    assert too_long.get_json()["error"]["code"] == "invalid_reason"

    assert (
        client.post(
            f"/api/qa/topics/999/statements/{own['id']}/reports",
            json={"reason": "话题不存在"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/qa/topics/{topic['id']}/statements/999/reports",
            json={"reason": "发言不存在"},
        ).status_code
        == 404
    )

    created = client.post(path, json={"reason": "人身攻击"})
    assert created.status_code == 201
    assert created.get_json()["data"]["status"] == "pending"
    assert created.get_json()["data"]["reporter"]["username"] == "other"

    again = client.post(path, json={"reason": "再举报一次"})
    assert again.status_code == 409
    assert again.get_json()["error"]["code"] == "already_reported"


def test_report_notifies_admins_and_appears_in_queue(client):
    topic = create_topic(client, "举报话题").get_json()["data"]
    statement = post_statement(client, topic["id"], "有问题的发言").get_json()["data"]

    client.post("/api/auth/logout")
    login(client, "other", "other123")
    created = client.post(
        f"/api/qa/topics/{topic['id']}/statements/{statement['id']}/reports",
        json={"reason": "人身攻击"},
    )
    assert created.status_code == 201

    # 举报人不会收到“有新举报”的通知，也看不了举报队列
    viewer_notifications = client.get("/api/qa/notifications").get_json()["data"]
    assert viewer_notifications["items"] == []
    assert viewer_notifications["unread"] == 0
    assert client.get("/api/qa/reports").status_code == 403

    client.post("/api/auth/logout")
    login(client, "admin", "admin123")
    counts = client.get("/api/qa/notifications/unread-count").get_json()["data"]
    assert counts["unread"] >= 1
    assert counts["pending_reports"] == 1

    queue = client.get("/api/qa/reports").get_json()["data"]
    assert queue["pending"] == 1
    assert len(queue["items"]) == 1
    item = queue["items"][0]
    assert item["reason"] == "人身攻击"
    assert item["topic_title"] == "举报话题"
    assert item["statement"]["content"] == "有问题的发言"
    assert item["statement"]["author"]["username"] == "teacher"
    assert item["reporter"]["username"] == "other"


def test_handle_report_hide_hides_statement_and_notifies(client):
    topic = create_topic(client, "处理举报话题").get_json()["data"]
    statement = post_statement(client, topic["id"], "要被处理的发言").get_json()["data"]

    client.post("/api/auth/logout")
    login(client, "other", "other123")
    client.post(
        f"/api/qa/topics/{topic['id']}/statements/{statement['id']}/reports",
        json={"reason": "人身攻击"},
    )

    client.post("/api/auth/logout")
    login(client, "admin", "admin123")
    report_id = client.get("/api/qa/reports").get_json()["data"]["items"][0]["id"]

    handled = client.patch(
        f"/api/qa/reports/{report_id}",
        json={"action": "hide", "reason": "包含人身攻击"},
    )
    assert handled.status_code == 200
    assert handled.get_json()["data"]["status"] == "resolved"
    assert handled.get_json()["data"]["handled_by"]["username"] == "admin"

    detail = client.get(f"/api/qa/topics/{topic['id']}").get_json()["data"]
    assert detail["statements"][0]["hidden"] is True
    assert detail["statements"][0]["hidden_reason"] == "包含人身攻击"
    assert client.get("/api/qa/reports").get_json()["data"]["pending"] == 0

    client.post("/api/auth/logout")
    login(client, "other", "other123")
    viewer_notes = client.get("/api/qa/notifications").get_json()["data"]["items"]
    assert any(note["kind"] == "report_resolved" for note in viewer_notes)

    client.post("/api/auth/logout")
    login(client, "teacher", "teacher123")
    author_notes = client.get("/api/qa/notifications").get_json()["data"]["items"]
    assert any(note["kind"] == "statement_hidden" for note in author_notes)


def test_handle_report_dismiss(client):
    topic = create_topic(client, "驳回举报话题").get_json()["data"]
    statement = post_statement(client, topic["id"], "其实没问题的发言").get_json()["data"]

    client.post("/api/auth/logout")
    login(client, "other", "other123")
    client.post(
        f"/api/qa/topics/{topic['id']}/statements/{statement['id']}/reports",
        json={"reason": "看不惯"},
    )

    client.post("/api/auth/logout")
    login(client, "admin", "admin123")
    report_id = client.get("/api/qa/reports").get_json()["data"]["items"][0]["id"]

    dismissed = client.patch(
        f"/api/qa/reports/{report_id}", json={"action": "dismiss"}
    )
    assert dismissed.status_code == 200
    assert dismissed.get_json()["data"]["status"] == "dismissed"

    detail = client.get(f"/api/qa/topics/{topic['id']}").get_json()["data"]
    assert detail["statements"][0]["hidden"] is False

    client.post("/api/auth/logout")
    login(client, "other", "other123")
    notes = client.get("/api/qa/notifications").get_json()["data"]["items"]
    assert any(note["kind"] == "report_dismissed" for note in notes)


def test_handle_report_validation(client):
    topic = create_topic(client, "举报校验话题").get_json()["data"]
    statement = post_statement(client, topic["id"], "校验发言").get_json()["data"]

    client.post("/api/auth/logout")
    login(client, "other", "other123")
    client.post(
        f"/api/qa/topics/{topic['id']}/statements/{statement['id']}/reports",
        json={"reason": "理由"},
    )
    assert (
        client.patch("/api/qa/reports/1", json={"action": "hide"}).status_code == 403
    )

    client.post("/api/auth/logout")
    login(client, "admin", "admin123")
    report_id = client.get("/api/qa/reports").get_json()["data"]["items"][0]["id"]

    assert (
        client.patch("/api/qa/reports/999", json={"action": "hide"}).status_code == 404
    )

    bad = client.patch(f"/api/qa/reports/{report_id}", json={"action": "delete"})
    assert bad.status_code == 400
    assert bad.get_json()["error"]["code"] == "invalid_action"

    assert (
        client.patch(
            f"/api/qa/reports/{report_id}", json={"action": "hide"}
        ).status_code
        == 200
    )
    again = client.patch(f"/api/qa/reports/{report_id}", json={"action": "hide"})
    assert again.status_code == 409
    assert again.get_json()["error"]["code"] == "report_handled"


def test_hiding_statement_resolves_pending_reports(client):
    topic = create_topic(client, "直接隐藏话题").get_json()["data"]
    statement = post_statement(client, topic["id"], "被直接隐藏的发言").get_json()["data"]

    client.post("/api/auth/logout")
    login(client, "other", "other123")
    client.post(
        f"/api/qa/topics/{topic['id']}/statements/{statement['id']}/reports",
        json={"reason": "违规"},
    )

    client.post("/api/auth/logout")
    login(client, "admin", "admin123")
    # 管理员不走举报队列，直接在时间线里隐藏
    hidden = client.patch(
        f"/api/qa/topics/{topic['id']}/statements/{statement['id']}",
        json={"hidden": True, "reason": "违规"},
    )
    assert hidden.status_code == 200

    queue = client.get("/api/qa/reports").get_json()["data"]
    assert queue["pending"] == 0
    resolved = client.get("/api/qa/reports?status=resolved").get_json()["data"]["items"]
    assert [item["status"] for item in resolved] == ["resolved"]

    client.post("/api/auth/logout")
    login(client, "other", "other123")
    notes = client.get("/api/qa/notifications").get_json()["data"]["items"]
    assert any(note["kind"] == "report_resolved" for note in notes)

    # 已隐藏的发言不能再被举报
    blocked = client.post(
        f"/api/qa/topics/{topic['id']}/statements/{statement['id']}/reports",
        json={"reason": "再举报"},
    )
    assert blocked.status_code == 400
    assert blocked.get_json()["error"]["code"] == "statement_hidden"


def test_notifications_list_and_mark_read(client):
    topic = create_topic(client, "通知话题").get_json()["data"]
    statement = post_statement(client, topic["id"], "通知用发言").get_json()["data"]

    client.post("/api/auth/logout")
    login(client, "other", "other123")
    client.post(
        f"/api/qa/topics/{topic['id']}/statements/{statement['id']}/reports",
        json={"reason": "理由"},
    )

    client.post("/api/auth/logout")
    login(client, "admin", "admin123")
    listed = client.get("/api/qa/notifications").get_json()["data"]
    assert listed["unread"] >= 1
    assert listed["items"][0]["read"] is False
    assert listed["items"][0]["topic_id"] == topic["id"]

    marked = client.post("/api/qa/notifications/read")
    assert marked.status_code == 200
    assert marked.get_json()["data"]["updated"] >= 1
    assert client.get("/api/qa/notifications").get_json()["data"]["unread"] == 0

    client.post("/api/auth/logout")
    assert client.get("/api/qa/notifications").status_code == 401
