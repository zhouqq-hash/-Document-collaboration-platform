import io

from conftest import login
from openpyxl import Workbook
from app.table_sheets import _matrix_to_grid


def create_table(client, username="admin"):
    login(
        client,
        username,
        "admin123" if username == "admin" else "teacher123",
    )
    response = client.post(
        "/api/tables",
        json={
            "name": "课程成绩协作表",
            "description": "导入测试",
            "columns": ["原列"],
        },
    )
    return response.get_json()["data"]


def make_xlsx(rows, formulas=None, title="成绩表"):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = title
    for row in rows:
        worksheet.append(row)
    for address, formula in (formulas or {}).items():
        worksheet[address] = formula
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def upload(client, table_id, data, filename="scores.xlsx"):
    return client.post(
        f"/api/tables/{table_id}/import",
        data={"file": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


def test_create_table_from_import_in_one_step(client):
    login(client, "teacher", "teacher123")
    data = make_xlsx(
        [
            ["组别", "人数", "总分", "平均分"],
            ["A", 2, 80, None],
        ],
        {"D2": "=C2/B2"},
    )

    response = client.post(
        "/api/tables/import",
        data={
            "name": "导入创建的课程表",
            "description": "一步导入",
            "file": (io.BytesIO(data), "scores.xlsx"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    payload = response.get_json()["data"]
    table = payload["table"]
    assert table["name"] == "导入创建的课程表"
    assert table["owner"]["username"] == "teacher"
    assert table["version_number"] == 1
    assert table["row_count"] == 1
    assert table["rows"][0]["cells"]["col4"] == "40"
    assert payload["summary"]["formula_count"] == 1

    changes = client.get(f"/api/tables/{table['id']}/changes").get_json()["data"]
    assert changes[0]["kind"] == "import"
    assert changes[0]["detail"]["created_from_import"] is True


def test_create_table_from_invalid_import_leaves_no_table(client):
    login(client, "teacher", "teacher123")

    response = client.post(
        "/api/tables/import",
        data={"file": (io.BytesIO(b"not excel"), "scores.xlsx")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 422
    assert client.get("/api/tables").get_json()["data"] == []


def test_import_xlsx_recalculates_formulas_and_keeps_versions(client):
    table = create_table(client)
    data = make_xlsx(
        [
            ["组别", "人数", "总分", "平均分"],
            ["A", 2, 80, None],
            ["B", 4, 120, None],
        ],
        {
            "D2": "=C2/B2",
            "D3": "=C3/B3",
        },
    )

    response = upload(client, table["id"], data)

    assert response.status_code == 200
    payload = response.get_json()["data"]
    imported = payload["table"]
    assert [item["name"] for item in imported["columns"]] == [
        "组别",
        "人数",
        "总分",
        "平均分",
    ]
    assert imported["rows"][0]["cells"]["col4"] == "40"
    assert imported["rows"][1]["cells"]["col4"] == "30"
    assert imported["cell_meta"]["r1:col4"]["formula"] == "=C2/B2"
    assert imported["version_number"] == 3
    assert payload["rollback_version"]["version_number"] == 2
    assert payload["summary"]["formula_count"] == 2

    changed = client.patch(
        f"/api/tables/{table['id']}/cells",
        json={"row_key": "r1", "column_key": "col2", "value": "4"},
    )
    assert changed.status_code == 200
    changed_table = changed.get_json()["data"]["table"]
    assert changed_table["rows"][0]["cells"]["col4"] == "20"
    assert changed_table["cell_meta"]["r1:col4"]["formula"] == "=C2/B2"


def test_import_can_be_rolled_back_to_pre_import_snapshot(client):
    table = create_table(client)
    client.post(
        f"/api/tables/{table['id']}/rows",
        json={"cells": {"col1": "保留这一行"}},
    )
    data = make_xlsx([["姓名"], ["新数据"]])

    payload = upload(client, table["id"], data).get_json()["data"]
    rollback = client.post(
        f"/api/tables/{table['id']}/versions/{payload['rollback_version']['id']}/rollback"
    )

    assert rollback.status_code == 200
    restored = rollback.get_json()["data"]["table"]
    assert [item["name"] for item in restored["columns"]] == ["原列"]
    assert restored["rows"][0]["cells"]["col1"] == "保留这一行"


def test_import_rejects_unsupported_formula_without_cached_result(client):
    table = create_table(client)
    data = make_xlsx(
        [["姓名", "编码"], ["张三", None]],
        {"B2": "=VLOOKUP(A2, A2:B3, 2, FALSE)"},
    )

    response = upload(client, table["id"], data)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "missing_formula_result"
    detail = client.get(f"/api/tables/{table['id']}").get_json()["data"]
    assert detail["row_count"] == 0
    assert detail["version_number"] == 1


def test_unsupported_formula_uses_cached_result_and_is_locked():
    columns, rows, meta, report = _matrix_to_grid(
        [["姓名", "编码"], ["张三", ""]],
        formula_cells={(1, 1): "=VLOOKUP(A2, A2:B3, 2, FALSE)"},
        cached_cells={(1, 1): 42},
    )

    assert columns[1]["name"] == "编码"
    assert rows[0]["cells"]["col2"] == "42"
    assert meta["r1:col2"]["locked"] is True
    assert "VLOOKUP" in meta["r1:col2"]["warning"]
    assert len(report["locked_formulas"]) == 1


def test_non_owner_cannot_import(client):
    table = create_table(client)
    client.post("/api/auth/logout")
    login(client, "teacher", "teacher123")

    response = upload(client, table["id"], make_xlsx([["姓名"], ["张三"]]))

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "permission_denied"


def test_import_csv(client):
    table = create_table(client)
    csv_data = "姓名,人数,总分\n张三,2,80\n".encode("utf-8-sig")

    response = upload(client, table["id"], csv_data, filename="scores.csv")

    assert response.status_code == 200
    imported = response.get_json()["data"]["table"]
    assert imported["row_count"] == 1
    assert imported["rows"][0]["cells"]["col3"] == "80"


def test_import_rejects_unsupported_file_type(client):
    table = create_table(client)

    response = upload(client, table["id"], b"hello", filename="scores.txt")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_file_type"
