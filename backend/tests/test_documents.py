import io

from conftest import create_document, login

#十个测试用例
def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_unauthorized_returns_401(client):
    response = client.get("/api/documents")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthorized"


def test_login_and_me(client):
    response = login(client, "admin", "admin123")
    assert response.status_code == 200
    assert response.get_json()["data"]["role"] == "admin"

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["data"]["username"] == "admin"


def test_teacher_can_list_categories(client):
    login(client)
    response = client.get("/api/categories")
    items = response.get_json()["data"]
    assert response.status_code == 200
    assert items[0]["name"] == "专业培养计划"
    assert "created_at" in items[0]
    assert [item["name"] for item in response.get_json()["data"]] == [
        "专业培养计划",
        "教学大纲",
    ]


def test_create_document_and_version_increment(client):
    response = create_document(client)
    assert response.status_code == 201
    document = response.get_json()["data"]
    assert document["current_version"]["version_number"] == 1
    assert document["description"] == "这是一个专业培养计划"

    second = client.post(
        f"/api/documents/{document['id']}/versions",
        data={
            "changelog": "第二次修订",
            "file": (io.BytesIO(b"second version"), "plan_v2.txt"),
        },
        content_type="multipart/form-data",
    )
    assert second.status_code == 201
    assert second.get_json()["data"]["version_number"] == 2
    assert second.get_json()["data"]["uploader"]["username"] == "admin"

    detail = client.get(f"/api/documents/{document['id']}")
    assert detail.get_json()["data"]["current_version"]["version_number"] == 2


def test_teacher_cannot_upload_if_not_owner(client):
    document = create_document(client).get_json()["data"]
    client.post("/api/auth/logout")
    login(client, "other", "other123")

    response = client.post(
        f"/api/documents/{document['id']}/versions",
        data={
            "changelog": "越权上传",
            "file": (io.BytesIO(b"bad"), "bad.txt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "permission_denied"


def test_owner_can_upload_new_version(client):
    document = create_document(client).get_json()["data"]
    client.post("/api/auth/logout")
    login(client, "teacher", "teacher123")

    response = client.post(
        f"/api/documents/{document['id']}/versions",
        data={
            "changelog": "负责人修订",
            "file": (io.BytesIO(b"owner version"), "owner.txt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    assert response.get_json()["data"]["version_number"] == 2
    assert response.get_json()["data"]["uploader"]["username"] == "teacher"


def test_download_version(client):
    document = create_document(client).get_json()["data"]
    version_id = document["current_version"]["id"]
    client.post("/api/auth/logout")
    login(client, "other", "other123")

    response = client.get(
        f"/api/documents/{document['id']}/versions/{version_id}/download"
    )
    assert response.status_code == 200
    assert response.data == b"first version"


def test_teacher_cannot_create_category(client):
    login(client)
    response = client.post(
        "/api/categories", json={"name": "越权分类", "sort_order": 10}
    )
    assert response.status_code == 403


def test_admin_can_create_category(client):
    login(client, "admin", "admin123")
    response = client.post(
        "/api/categories", json={"name": "新分类", "sort_order": 10}
    )
    assert response.status_code == 201
    assert response.get_json()["data"]["name"] == "新分类"
