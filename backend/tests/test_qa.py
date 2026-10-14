from datetime import timedelta

from conftest import login

from app import db
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

    topics = client.get("/api/qa/topics").get_json()["data"]
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
