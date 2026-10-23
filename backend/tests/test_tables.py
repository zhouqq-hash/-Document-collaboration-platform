from conftest import login


def create_table(client, name="毕业设计进度表", columns=None, username="admin"):
    login(client, username, "admin123" if username == "admin" else "teacher123")
    return client.post(
        "/api/tables",
        json={
            "name": name,
            "description": "演示表格",
            "columns": columns or ["组号", "题目", "进度"],
        },
    )


def test_tables_require_login(client):
    response = client.get("/api/tables")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthorized"


def test_create_table(client):
    response = create_table(client)
    assert response.status_code == 201
    table = response.get_json()["data"]
    assert table["name"] == "毕业设计进度表"
    assert table["column_count"] == 3
    assert table["row_count"] == 0
    assert table["version_number"] == 1
    assert [item["key"] for item in table["columns"]] == ["col1", "col2", "col3"]
    assert table["owner"]["username"] == "admin"

    versions = client.get(f"/api/tables/{table['id']}/versions")
    assert versions.status_code == 200
    assert len(versions.get_json()["data"]) == 1


def test_create_table_requires_columns(client):
    login(client)
    response = client.post(
        "/api/tables", json={"name": "空表格", "columns": []}
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_columns"


def test_create_table_rejects_duplicate_or_too_many_columns(client):
    login(client)
    duplicate = client.post(
        "/api/tables",
        json={"name": "重复列", "columns": ["姓名", "姓名"]},
    )
    assert duplicate.status_code == 400
    assert duplicate.get_json()["error"]["code"] == "invalid_columns"

    too_many = client.post(
        "/api/tables",
        json={"name": "太多列", "columns": [f"列{index}" for index in range(31)]},
    )
    assert too_many.status_code == 400
    assert too_many.get_json()["error"]["code"] == "invalid_columns"


def test_any_teacher_can_create_table(client):
    response = create_table(client, username="teacher")
    assert response.status_code == 201
    assert response.get_json()["data"]["owner"]["username"] == "teacher"


def test_add_row_and_list(client):
    table = create_table(client).get_json()["data"]

    response = client.post(
        f"/api/tables/{table['id']}/rows",
        json={"cells": {"col1": "1", "col2": "在线协作平台", "col3": "进行中"}},
    )
    assert response.status_code == 201
    row = response.get_json()["data"]["row"]
    assert row["row_key"] == "r1"
    assert row["cells"]["col2"] == "在线协作平台"

    detail = client.get(f"/api/tables/{table['id']}")
    assert detail.get_json()["data"]["row_count"] == 1


def test_update_cell_records_change(client):
    table = create_table(client).get_json()["data"]
    client.post(
        f"/api/tables/{table['id']}/rows",
        json={"cells": {"col1": "1", "col2": "旧值", "col3": "进行中"}},
    )

    response = client.patch(
        f"/api/tables/{table['id']}/cells",
        json={"row_key": "r1", "column_key": "col2", "value": "新值"},
    )
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["row"]["cells"]["col2"] == "新值"
    assert payload["change"]["kind"] == "cell_update"
    assert payload["change"]["old_value"] == "旧值"
    assert payload["change"]["new_value"] == "新值"
    assert payload["change"]["editor"]["username"] == "admin"

    changes = client.get(f"/api/tables/{table['id']}/changes")
    kinds = [item["kind"] for item in changes.get_json()["data"]]
    assert kinds[0] == "cell_update"
    assert "row_add" in kinds


def test_update_cell_noop_does_not_record_change(client):
    table = create_table(client).get_json()["data"]
    client.post(
        f"/api/tables/{table['id']}/rows",
        json={"cells": {"col1": "1"}},
    )

    response = client.patch(
        f"/api/tables/{table['id']}/cells",
        json={"row_key": "r1", "column_key": "col1", "value": "1"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["change"] is None

    changes = client.get(f"/api/tables/{table['id']}/changes")
    assert [item["kind"] for item in changes.get_json()["data"]] == ["row_add"]


def test_update_cell_rejects_missing_row_or_column(client):
    table = create_table(client).get_json()["data"]

    missing_row = client.patch(
        f"/api/tables/{table['id']}/cells",
        json={"row_key": "r99", "column_key": "col1", "value": "x"},
    )
    assert missing_row.status_code == 404
    assert missing_row.get_json()["error"]["code"] == "row_not_found"

    client.post(
        f"/api/tables/{table['id']}/rows",
        json={"cells": {"col1": "1"}},
    )
    missing_column = client.patch(
        f"/api/tables/{table['id']}/cells",
        json={"row_key": "r1", "column_key": "col99", "value": "x"},
    )
    assert missing_column.status_code == 404
    assert missing_column.get_json()["error"]["code"] == "column_not_found"


def test_collaborator_can_edit_cell(client):
    table = create_table(client).get_json()["data"]
    client.post(
        f"/api/tables/{table['id']}/rows",
        json={"cells": {"col1": "1"}},
    )
    client.post("/api/auth/logout")
    login(client, "teacher", "teacher123")

    response = client.patch(
        f"/api/tables/{table['id']}/cells",
        json={"row_key": "r1", "column_key": "col1", "value": "老师改过"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["change"]["editor"]["username"] == "teacher"


def test_add_column_creates_new_version(client):
    table = create_table(client).get_json()["data"]

    response = client.post(
        f"/api/tables/{table['id']}/columns", json={"name": "备注"}
    )
    assert response.status_code == 201
    assert response.get_json()["data"]["column"]["key"] == "col4"

    detail = client.get(f"/api/tables/{table['id']}")
    assert detail.get_json()["data"]["column_count"] == 4
    assert detail.get_json()["data"]["version_number"] == 2


def test_add_column_rejects_duplicate_name(client):
    table = create_table(client).get_json()["data"]
    response = client.post(
        f"/api/tables/{table['id']}/columns", json={"name": "组号"}
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "column_exists"


def test_delete_row(client):
    table = create_table(client).get_json()["data"]
    client.post(
        f"/api/tables/{table['id']}/rows",
        json={"cells": {"col1": "1"}},
    )

    response = client.delete(f"/api/tables/{table['id']}/rows/r1")
    assert response.status_code == 200
    assert response.get_json()["data"]["change"]["kind"] == "row_delete"

    detail = client.get(f"/api/tables/{table['id']}")
    assert detail.get_json()["data"]["row_count"] == 0


def test_non_owner_cannot_rollback(client):
    table = create_table(client).get_json()["data"]
    version_id = client.get(f"/api/tables/{table['id']}/versions").get_json()["data"][0]["id"]

    client.post("/api/auth/logout")
    login(client, "teacher", "teacher123")
    response = client.post(
        f"/api/tables/{table['id']}/versions/{version_id}/rollback"
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "permission_denied"


def test_snapshot_and_rollback_restore_grid(client):
    table = create_table(client).get_json()["data"]
    client.post(
        f"/api/tables/{table['id']}/rows",
        json={"cells": {"col1": "1", "col2": "原始题目"}},
    )
    snapshot = client.post(
        f"/api/tables/{table['id']}/versions",
        json={"changelog": "需求确认"},
    )
    assert snapshot.status_code == 201
    assert snapshot.get_json()["data"]["version_number"] == 2

    client.patch(
        f"/api/tables/{table['id']}/cells",
        json={"row_key": "r1", "column_key": "col2", "value": "被改坏的题目"},
    )

    rollback = client.post(
        f"/api/tables/{table['id']}/versions/{snapshot.get_json()['data']['id']}/rollback"
    )
    assert rollback.status_code == 200
    payload = rollback.get_json()["data"]
    assert payload["table"]["rows"][0]["cells"]["col2"] == "原始题目"
    assert payload["version"]["version_number"] == 3

    changes = client.get(f"/api/tables/{table['id']}/changes")
    kinds = [item["kind"] for item in changes.get_json()["data"]]
    assert kinds[0] == "rollback"
    assert "cell_update" in kinds


def test_non_owner_cannot_snapshot(client):
    table = create_table(client).get_json()["data"]
    client.post("/api/auth/logout")
    login(client, "teacher", "teacher123")

    response = client.post(
        f"/api/tables/{table['id']}/versions", json={"changelog": "越权"}
    )
    assert response.status_code == 403


def test_owner_can_rename_table(client):
    table = create_table(client).get_json()["data"]
    response = client.patch(
        f"/api/tables/{table['id']}",
        json={"name": "改后的名字", "description": "新说明"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["name"] == "改后的名字"

    changes = client.get(f"/api/tables/{table['id']}/changes")
    assert changes.get_json()["data"][0]["kind"] == "rename"


def test_non_owner_cannot_rename(client):
    table = create_table(client).get_json()["data"]
    client.post("/api/auth/logout")
    login(client, "teacher", "teacher123")

    response = client.patch(
        f"/api/tables/{table['id']}", json={"name": "越权改名"}
    )
    assert response.status_code == 403


def test_non_owner_cannot_delete_table(client):
    table = create_table(client).get_json()["data"]
    client.post("/api/auth/logout")
    login(client, "teacher", "teacher123")

    response = client.delete(f"/api/tables/{table['id']}")
    assert response.status_code == 403


def test_owner_can_delete_table(client):
    table = create_table(client).get_json()["data"]
    response = client.delete(f"/api/tables/{table['id']}")
    assert response.status_code == 204

    detail = client.get(f"/api/tables/{table['id']}")
    assert detail.status_code == 404


def test_get_version_detail(client):
    table = create_table(client).get_json()["data"]
    version_id = client.get(f"/api/tables/{table['id']}/versions").get_json()["data"][0]["id"]

    response = client.get(f"/api/tables/{table['id']}/versions/{version_id}")
    assert response.status_code == 200
    assert response.get_json()["data"]["columns"][0]["name"] == "组号"


def test_list_tables_search(client):
    create_table(client, name="课程安排表")
    create_table(client, name="答辩安排表")

    response = client.get("/api/tables?q=答辩")
    assert response.status_code == 200
    items = response.get_json()["data"]
    assert [item["name"] for item in items] == ["答辩安排表"]


def test_list_changes_supports_limit(client):
    table = create_table(client).get_json()["data"]
    client.post(
        f"/api/tables/{table['id']}/rows",
        json={"cells": {"col1": "1"}},
    )
    client.patch(
        f"/api/tables/{table['id']}/cells",
        json={"row_key": "r1", "column_key": "col1", "value": "2"},
    )

    response = client.get(f"/api/tables/{table['id']}/changes?limit=1")
    assert response.status_code == 200
    assert len(response.get_json()["data"]) == 1
    assert response.get_json()["data"][0]["kind"] == "cell_update"


def test_owner_can_rename_column(client):
    table = create_table(client).get_json()["data"]
    response = client.patch(
        f"/api/tables/{table['id']}/columns/col1", json={"name": "学号"}
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["column"]["name"] == "学号"

    detail = client.get(f"/api/tables/{table['id']}")
    assert detail.get_json()["data"]["columns"][0]["name"] == "学号"


def test_non_owner_cannot_rename_column(client):
    table = create_table(client).get_json()["data"]
    client.post("/api/auth/logout")
    login(client, "teacher", "teacher123")

    response = client.patch(
        f"/api/tables/{table['id']}/columns/col1", json={"name": "越权"}
    )
    assert response.status_code == 403


def test_owner_can_update_column_width(client):
    table = create_table(client).get_json()["data"]
    response = client.patch(
        f"/api/tables/{table['id']}/columns/col1", json={"width": 300}
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["column"]["width"] == 300


def test_owner_can_delete_column_and_data(client):
    table = create_table(client).get_json()["data"]
    client.post(
        f"/api/tables/{table['id']}/rows",
        json={"cells": {"col1": "1", "col2": "题目"}},
    )

    response = client.delete(f"/api/tables/{table['id']}/columns/col1")
    assert response.status_code == 200
    assert response.get_json()["data"]["change"]["kind"] == "column_delete"

    detail = client.get(f"/api/tables/{table['id']}")
    data = detail.get_json()["data"]
    assert data["column_count"] == 2
    assert "col1" not in data["rows"][0]["cells"]
    assert data["rows"][0]["cells"]["col2"] == "题目"
    assert data["version_number"] == 2


def test_batch_delete_rows(client):
    table = create_table(client).get_json()["data"]
    client.post(f"/api/tables/{table['id']}/rows", json={"cells": {"col1": "1"}})
    client.post(f"/api/tables/{table['id']}/rows", json={"cells": {"col1": "2"}})

    response = client.post(
        f"/api/tables/{table['id']}/rows/delete",
        json={"row_keys": ["r1", "r2"]},
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["deleted_count"] == 2
    assert data["change"]["kind"] == "rows_delete"

    detail = client.get(f"/api/tables/{table['id']}")
    assert detail.get_json()["data"]["row_count"] == 0
    assert detail.get_json()["data"]["version_number"] == 2


def test_batch_delete_columns(client):
    table = create_table(client).get_json()["data"]
    client.post(
        f"/api/tables/{table['id']}/rows",
        json={"cells": {"col1": "1", "col2": "2", "col3": "3"}},
    )

    response = client.post(
        f"/api/tables/{table['id']}/columns/delete",
        json={"column_keys": ["col1", "col2"]},
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["deleted_count"] == 2
    assert data["change"]["kind"] == "columns_delete"

    detail = client.get(f"/api/tables/{table['id']}")
    table_data = detail.get_json()["data"]
    assert table_data["column_count"] == 1
    assert table_data["columns"][0]["key"] == "col3"
    assert list(table_data["rows"][0]["cells"].keys()) == ["col3"]


def test_cannot_delete_last_column(client):
    table = create_table(client, columns=["单列"]).get_json()["data"]
    response = client.delete(f"/api/tables/{table['id']}/columns/col1")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "cannot_delete_last_column"

    batch = client.post(
        f"/api/tables/{table['id']}/columns/delete",
        json={"column_keys": ["col1"]},
    )
    assert batch.status_code == 400
    assert batch.get_json()["error"]["code"] == "cannot_delete_last_column"
