from flask import Blueprint, request
from flask_login import current_user, login_required

from . import db
from .models import Table, TableChange, TableVersion, utcnow
from .utils import api_error, api_success


bp = Blueprint("tables", __name__, url_prefix="/api")

MAX_CELL_LENGTH = 5000


def _get_table_or_404(table_id):
    return db.session.get(Table, table_id)


def _as_str(value):
    if value is None:
        return ""
    return str(value)


def _can_manage(table):
    return current_user.is_admin or table.owner_id == current_user.id


def _find_row(table, row_key):
    for row in table.rows or []:
        if row.get("row_key") == row_key:
            return row
    return None


def _find_column(table, column_key):
    for column in table.columns or []:
        if column.get("key") == column_key:
            return column
    return None


def _next_column_key(table):
    columns = table.columns or []
    max_number = 0
    for column in columns:
        key = column.get("key") or ""
        if key.startswith("col") and key[3:].isdigit():
            max_number = max(max_number, int(key[3:]))
    return f"col{max_number + 1}"


def _create_version(table, changelog=""):
    """为表格当前状态生成一个新版本快照，并推进 version_number。"""
    table.version_number = (table.version_number or 0) + 1
    version = TableVersion(
        table=table,
        version_number=table.version_number,
        snapshot={"columns": table.columns or [], "rows": table.rows or []},
        changelog=(changelog or "").strip(),
        editor=current_user,
    )
    db.session.add(version)
    return version


def _record_change(table, kind, **fields):
    change = TableChange(
        table=table,
        editor=current_user,
        kind=kind,
        row_key=fields.get("row_key"),
        column_key=fields.get("column_key"),
        column_name=fields.get("column_name"),
        old_value=fields.get("old_value", ""),
        new_value=fields.get("new_value", ""),
        detail=fields.get("detail"),
    )
    db.session.add(change)
    return change


def _touch(table):
    table.updated_at = utcnow()


def _parse_columns(payload):
    raw_columns = payload.get("columns")
    if not isinstance(raw_columns, list) or not raw_columns:
        raise ValueError("至少需要一列")

    columns = []
    for index, item in enumerate(raw_columns):
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = (item.get("name") or "").strip()
        else:
            name = ""
        if not name:
            raise ValueError("列名不能为空")
        if len(name) > 80:
            raise ValueError("列名过长")
        columns.append({"key": f"col{index + 1}", "name": name, "type": "text"})
    return columns


@bp.get("/tables")
@login_required
def list_tables():
    query = Table.query
    keyword = (request.args.get("q") or "").strip()
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            db.or_(Table.name.ilike(like), Table.description.ilike(like))
        )
    tables = query.order_by(Table.updated_at.desc(), Table.id.desc()).all()
    return api_success([table.to_dict() for table in tables])


@bp.post("/tables")
@login_required
def create_table():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return api_error("表格名称不能为空", "invalid_name", 400)
    if len(name) > 120:
        return api_error("表格名称过长", "invalid_name", 400)

    description = _as_str(payload.get("description")).strip()
    if len(description) > 500:
        return api_error("表格说明过长", "invalid_description", 400)

    try:
        columns = _parse_columns(payload)
    except ValueError as exc:
        return api_error(str(exc), "invalid_columns", 400)

    table = Table(
        name=name,
        description=description,
        owner=current_user,
        columns=columns,
        rows=[],
        row_seq=0,
        version_number=0,
    )
    db.session.add(table)
    db.session.flush()
    _create_version(table, "创建表格")
    db.session.commit()
    return api_success(table.to_dict(include_grid=True), status=201)


@bp.get("/tables/<int:table_id>")
@login_required
def get_table(table_id):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)
    data = table.to_dict(include_grid=True)
    data["can_manage"] = _can_manage(table)
    return api_success(data)


@bp.patch("/tables/<int:table_id>")
@login_required
def update_table(table_id):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)
    if not _can_manage(table):
        return api_error("只有管理员或表格创建人可以修改表格信息", "permission_denied", 403)

    payload = request.get_json(silent=True) or {}
    old_name = table.name
    old_description = table.description or ""

    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            return api_error("表格名称不能为空", "invalid_name", 400)
        if len(name) > 120:
            return api_error("表格名称过长", "invalid_name", 400)
        table.name = name

    if "description" in payload:
        description = _as_str(payload.get("description")).strip()
        if len(description) > 500:
            return api_error("表格说明过长", "invalid_description", 400)
        table.description = description

    if table.name != old_name or table.description != old_description:
        _record_change(
            table,
            "rename",
            old_value=old_name,
            new_value=table.name,
            detail={"old_description": old_description, "new_description": table.description},
        )
        _touch(table)

    db.session.commit()
    data = table.to_dict(include_grid=True)
    data["can_manage"] = True
    return api_success(data)


@bp.delete("/tables/<int:table_id>")
@login_required
def delete_table(table_id):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)
    if not _can_manage(table):
        return api_error("只有管理员或表格创建人可以删除表格", "permission_denied", 403)

    db.session.delete(table)
    db.session.commit()
    return "", 204


@bp.patch("/tables/<int:table_id>/cells")
@login_required
def update_cell(table_id):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)

    payload = request.get_json(silent=True) or {}
    row_key = (payload.get("row_key") or "").strip()
    column_key = (payload.get("column_key") or "").strip()
    value = _as_str(payload.get("value"))

    row = _find_row(table, row_key)
    if row is None:
        return api_error("行不存在", "row_not_found", 404)
    column = _find_column(table, column_key)
    if column is None:
        return api_error("列不存在", "column_not_found", 404)
    if len(value) > MAX_CELL_LENGTH:
        return api_error("单元格内容过长", "invalid_value", 400)

    old_value = row.get("cells", {}).get(column_key, "")
    if old_value == value:
        return api_success(
            {"table": table.to_dict(), "change": None, "row": row}
        )

    rows = [dict(item) for item in (table.rows or [])]
    target = next(item for item in rows if item["row_key"] == row_key)
    cells = dict(target.get("cells") or {})
    cells[column_key] = value
    target["cells"] = cells
    table.rows = rows
    _touch(table)
    change = _record_change(
        table,
        "cell_update",
        row_key=row_key,
        column_key=column_key,
        column_name=column.get("name"),
        old_value=old_value,
        new_value=value,
    )
    db.session.commit()
    return api_success(
        {
            "table": table.to_dict(),
            "change": change.to_dict(),
            "row": target,
        }
    )


@bp.post("/tables/<int:table_id>/rows")
@login_required
def add_row(table_id):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)

    payload = request.get_json(silent=True) or {}
    raw_cells = payload.get("cells")
    if raw_cells is None:
        raw_cells = {}
    if not isinstance(raw_cells, dict):
        return api_error("行数据格式不正确", "invalid_row", 400)

    column_keys = set(table.column_keys)
    cells = {}
    for key, value in raw_cells.items():
        if key not in column_keys:
            continue
        text = _as_str(value)
        if len(text) > MAX_CELL_LENGTH:
            return api_error("单元格内容过长", "invalid_value", 400)
        cells[key] = text

    table.row_seq = (table.row_seq or 0) + 1
    row = {"row_key": f"r{table.row_seq}", "cells": cells}
    rows = [dict(item) for item in (table.rows or [])]
    rows.append(row)
    table.rows = rows
    _touch(table)
    change = _record_change(
        table,
        "row_add",
        row_key=row["row_key"],
        detail={"row": row},
    )
    db.session.commit()
    return api_success(
        {
            "table": table.to_dict(),
            "change": change.to_dict(),
            "row": row,
        },
        status=201,
    )


@bp.delete("/tables/<int:table_id>/rows/<row_key>")
@login_required
def delete_row(table_id, row_key):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)

    row = _find_row(table, row_key)
    if row is None:
        return api_error("行不存在", "row_not_found", 404)

    # 删除前先快照，保证删错后能通过版本回滚恢复
    version = _create_version(table, "删除行前自动快照")
    rows = [dict(item) for item in (table.rows or []) if item["row_key"] != row_key]
    table.rows = rows
    _touch(table)
    change = _record_change(
        table,
        "row_delete",
        row_key=row_key,
        detail={"row": row},
    )
    db.session.commit()
    return api_success(
        {
            "table": table.to_dict(),
            "change": change.to_dict(),
            "version_id": version.id,
        }
    )


@bp.post("/tables/<int:table_id>/rows/delete")
@login_required
def delete_rows(table_id):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)
    if not _can_manage(table):
        return api_error("只有管理员或表格创建人可以删除行", "permission_denied", 403)

    payload = request.get_json(silent=True) or {}
    row_keys = payload.get("row_keys")
    if not isinstance(row_keys, list) or not row_keys:
        return api_error("请选择要删除的行", "invalid_row", 400)

    row_keys = [str(key) for key in row_keys]
    selected = []
    for key in row_keys:
        row = _find_row(table, key)
        if row is None:
            return api_error("行不存在", "row_not_found", 404)
        selected.append(row)

    version = _create_version(table, f"删除 {len(row_keys)} 行前自动快照")
    keys = set(row_keys)
    rows = [
        dict(item) for item in (table.rows or []) if item["row_key"] not in keys
    ]
    table.rows = rows
    _touch(table)
    change = _record_change(
        table,
        "rows_delete",
        detail={"row_keys": row_keys, "rows": selected, "deleted_count": len(row_keys)},
    )
    db.session.commit()
    return api_success(
        {
            "table": table.to_dict(),
            "change": change.to_dict(),
            "deleted_count": len(row_keys),
            "version_id": version.id,
        }
    )


@bp.post("/tables/<int:table_id>/columns")
@login_required
def add_column(table_id):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)

    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return api_error("列名不能为空", "invalid_name", 400)
    if len(name) > 80:
        return api_error("列名过长", "invalid_name", 400)
    if any(item.get("name") == name for item in (table.columns or [])):
        return api_error("列名已存在", "column_exists", 409)

    column = {"key": _next_column_key(table), "name": name, "type": "text"}
    columns = [dict(item) for item in (table.columns or [])]
    columns.append(column)
    table.columns = columns
    _touch(table)
    _record_change(
        table,
        "column_add",
        column_key=column["key"],
        column_name=name,
        detail={"column": column},
    )
    # 结构调整自动生成新版本，保证回滚到旧版本时列定义一致
    _create_version(table, f"新增列「{name}」")
    db.session.commit()
    return api_success(
        {
            "table": table.to_dict(),
            "column": column,
        },
        status=201,
    )


@bp.patch("/tables/<int:table_id>/columns/<column_key>")
@login_required
def update_column(table_id, column_key):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)
    if not _can_manage(table):
        return api_error("只有管理员或表格创建人可以调整列", "permission_denied", 403)

    column = _find_column(table, column_key)
    if column is None:
        return api_error("列不存在", "column_not_found", 404)

    payload = request.get_json(silent=True) or {}
    name_from = column.get("name")
    width_from = column.get("width")
    name_to = name_from
    width_to = width_from

    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            return api_error("列名不能为空", "invalid_name", 400)
        if len(name) > 80:
            return api_error("列名过长", "invalid_name", 400)
        if name != name_from and any(
            item.get("name") == name and item.get("key") != column_key
            for item in (table.columns or [])
        ):
            return api_error("列名已存在", "column_exists", 409)
        name_to = name

    if "width" in payload:
        try:
            width = int(round(float(payload.get("width"))))
        except (TypeError, ValueError):
            return api_error("列宽格式不正确", "invalid_width", 400)
        width = max(40, min(600, width))
        width_to = width

    if name_to == name_from and width_to == width_from:
        return api_success({"table": table.to_dict(), "column": column})

    column = dict(column)
    column["name"] = name_to
    column["width"] = width_to
    columns = [dict(item) for item in (table.columns or [])]
    for index, item in enumerate(columns):
        if item["key"] == column_key:
            columns[index] = column
            break
    table.columns = columns
    _touch(table)
    _record_change(
        table,
        "column_update",
        column_key=column_key,
        column_name=name_to,
        detail={
            "name_from": name_from,
            "name_to": name_to,
            "width_from": width_from,
            "width_to": width_to,
        },
    )
    db.session.commit()
    return api_success({"table": table.to_dict(), "column": column})


@bp.delete("/tables/<int:table_id>/columns/<column_key>")
@login_required
def delete_column(table_id, column_key):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)
    if not _can_manage(table):
        return api_error("只有管理员或表格创建人可以删除列", "permission_denied", 403)

    column = _find_column(table, column_key)
    if column is None:
        return api_error("列不存在", "column_not_found", 404)
    if len(table.columns or []) <= 1:
        return api_error("至少保留一列", "cannot_delete_last_column", 400)

    # 删除前先快照，保证删错后能通过版本回滚恢复
    version = _create_version(table, f"删除列「{column.get('name')}」前自动快照")
    columns = [
        dict(item)
        for item in (table.columns or [])
        if item.get("key") != column_key
    ]
    rows = [
        {
            "row_key": row.get("row_key"),
            "cells": {
                key: value
                for key, value in (row.get("cells") or {}).items()
                if key != column_key
            },
        }
        for row in (table.rows or [])
    ]
    table.columns = columns
    table.rows = rows
    _touch(table)
    change = _record_change(
        table,
        "column_delete",
        column_key=column_key,
        column_name=column.get("name"),
        detail={"column": column},
    )
    db.session.commit()
    return api_success(
        {
            "table": table.to_dict(),
            "change": change.to_dict(),
            "version_id": version.id,
        }
    )


@bp.post("/tables/<int:table_id>/columns/delete")
@login_required
def delete_columns(table_id):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)
    if not _can_manage(table):
        return api_error("只有管理员或表格创建人可以删除列", "permission_denied", 403)

    payload = request.get_json(silent=True) or {}
    column_keys = payload.get("column_keys")
    if not isinstance(column_keys, list) or not column_keys:
        return api_error("请选择要删除的列", "invalid_column", 400)

    column_keys = [str(key) for key in column_keys]
    selected = []
    for key in column_keys:
        column = _find_column(table, key)
        if column is None:
            return api_error("列不存在", "column_not_found", 404)
        selected.append(column)
    if len(column_keys) >= len(table.columns or []):
        return api_error("至少保留一列", "cannot_delete_last_column", 400)

    version = _create_version(table, f"删除 {len(column_keys)} 列前自动快照")
    keys = set(column_keys)
    columns = [
        dict(item) for item in (table.columns or []) if item.get("key") not in keys
    ]
    rows = [
        {
            "row_key": row.get("row_key"),
            "cells": {
                key: value
                for key, value in (row.get("cells") or {}).items()
                if key not in keys
            },
        }
        for row in (table.rows or [])
    ]
    table.columns = columns
    table.rows = rows
    _touch(table)
    change = _record_change(
        table,
        "columns_delete",
        detail={
            "column_keys": column_keys,
            "columns": selected,
            "deleted_count": len(column_keys),
        },
    )
    db.session.commit()
    return api_success(
        {
            "table": table.to_dict(),
            "change": change.to_dict(),
            "deleted_count": len(column_keys),
            "version_id": version.id,
        }
    )


@bp.get("/tables/<int:table_id>/changes")
@login_required
def list_changes(table_id):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)

    query = TableChange.query.filter_by(table_id=table.id)
    kind = (request.args.get("kind") or "").strip()
    if kind:
        query = query.filter_by(kind=kind)
    query = query.order_by(
        TableChange.created_at.desc(), TableChange.id.desc()
    )
    limit = request.args.get("limit", type=int)
    if limit and limit > 0:
        query = query.limit(min(limit, 500))
    changes = query.all()
    return api_success([change.to_dict() for change in changes])


@bp.get("/tables/<int:table_id>/versions")
@login_required
def list_versions(table_id):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)
    return api_success([version.to_dict() for version in table.versions])


@bp.post("/tables/<int:table_id>/versions")
@login_required
def create_version(table_id):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)
    if not _can_manage(table):
        return api_error("只有管理员或表格创建人可以保存快照", "permission_denied", 403)

    payload = request.get_json(silent=True) or {}
    changelog = _as_str(payload.get("changelog")).strip() or "手动保存快照"
    version = _create_version(table, changelog)
    _touch(table)
    db.session.commit()
    return api_success(version.to_dict(include_snapshot=True), status=201)


@bp.get("/tables/<int:table_id>/versions/<int:version_id>")
@login_required
def get_version(table_id, version_id):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)

    version = db.session.get(TableVersion, version_id)
    if version is None or version.table_id != table.id:
        return api_error("版本不存在", "version_not_found", 404)
    return api_success(version.to_dict(include_snapshot=True))


@bp.post("/tables/<int:table_id>/versions/<int:version_id>/rollback")
@login_required
def rollback_version(table_id, version_id):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)
    if not _can_manage(table):
        return api_error("只有管理员或表格创建人可以回滚版本", "permission_denied", 403)

    version = db.session.get(TableVersion, version_id)
    if version is None or version.table_id != table.id:
        return api_error("版本不存在", "version_not_found", 404)

    from_version = table.version_number
    snapshot = version.snapshot or {}
    table.columns = snapshot.get("columns") or []
    table.rows = snapshot.get("rows") or []
    _touch(table)
    new_version = _create_version(table, f"回滚到版本 {version.version_number}")
    _record_change(
        table,
        "rollback",
        old_value=str(from_version),
        new_value=str(version.version_number),
        detail={
            "from_version": from_version,
            "to_version": version.version_number,
            "new_version": new_version.version_number,
        },
    )
    db.session.commit()
    data = table.to_dict(include_grid=True)
    data["can_manage"] = True
    return api_success(
        {
            "table": data,
            "version": new_version.to_dict(include_snapshot=True),
        }
    )
