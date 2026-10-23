from pathlib import Path

from flask import Blueprint, request
from flask_login import current_user, login_required

from . import db
from .formula_engine import FormulaError, FormulaSyntaxError, UnsupportedFormulaError
from .models import Table, TableChange, TableVersion, utcnow
from .table_sheets import (
    TableImportError,
    calculate_grid,
    cell_meta_key,
    parse_import_file,
    remap_formula_references,
)
from .utils import api_error, api_success


bp = Blueprint("tables", __name__, url_prefix="/api")

MAX_CELL_LENGTH = 5000


def _get_table_or_404(table_id):
    return db.session.get(Table, table_id)


def _as_str(value):
    if value is None:
        return ""
    return str(value)


def _column_letters(index):
    number = index + 1
    letters = ""
    while number > 0:
        remainder = (number - 1) % 26
        letters = chr(65 + remainder) + letters
        number = (number - 1) // 26
    return letters


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
        snapshot={
            "columns": table.columns or [],
            "rows": table.rows or [],
            "cell_meta": table.cell_meta or {},
        },
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


def _import_error_response(exc):
    status = 413 if exc.code == "file_too_large" else 422
    if exc.code in {"invalid_file_type", "missing_file"}:
        status = 400
    if exc.code.endswith("_unavailable"):
        status = 500
    return api_error(str(exc), exc.code, status)


def _parse_columns(payload):
    raw_columns = payload.get("columns")
    if not isinstance(raw_columns, list) or not raw_columns:
        raise ValueError("至少需要一列")
    if len(raw_columns) > 30:
        raise ValueError("最多支持 30 列")

    columns = []
    seen_names = set()
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
        if name.casefold() in seen_names:
            raise ValueError("列名不能重复")
        seen_names.add(name.casefold())
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
        cell_meta={},
        row_seq=0,
        version_number=0,
    )
    db.session.add(table)
    db.session.flush()
    _create_version(table, "创建表格")
    db.session.commit()
    return api_success(table.to_dict(include_grid=True), status=201)


@bp.post("/tables/import")
@login_required
def create_table_from_import():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return api_error("请选择要导入的文件", "missing_file", 400)

    name = (request.form.get("name") or "").strip()
    if not name:
        name = Path(upload.filename).stem.strip() or "导入表格"
    if len(name) > 120:
        return api_error("表格名称不能超过 120 个字符", "invalid_name", 400)
    description = _as_str(request.form.get("description")).strip()
    if len(description) > 500:
        return api_error("表格说明不能超过 500 个字符", "invalid_description", 400)

    try:
        parsed = parse_import_file(upload.filename, upload.read())
    except TableImportError as exc:
        return _import_error_response(exc)

    table = Table(
        name=name,
        description=description,
        owner=current_user,
        columns=parsed["columns"],
        rows=parsed["rows"],
        cell_meta=parsed["cell_meta"],
        row_seq=len(parsed["rows"]),
        version_number=0,
    )
    db.session.add(table)
    db.session.flush()
    report = parsed["report"]
    version = _create_version(
        table,
        f"从 {upload.filename} 导入创建表格（{parsed['sheet_name']}）",
    )
    _record_change(
        table,
        "import",
        detail={
            "filename": upload.filename,
            "extension": parsed["extension"],
            "sheet_name": parsed["sheet_name"],
            "row_count": len(table.rows),
            "column_count": len(table.columns),
            "formula_count": report["formula_count"],
            "locked_formula_count": len(report["locked_formulas"]),
            "created_from_import": True,
        },
    )
    db.session.commit()

    data = table.to_dict(include_grid=True)
    data["can_manage"] = True
    return api_success(
        {
            "table": data,
            "version": version.to_dict(),
            "summary": {
                "filename": upload.filename,
                "sheet_name": parsed["sheet_name"],
                "extension": parsed["extension"],
                "row_count": len(table.rows),
                "column_count": len(table.columns),
                "formula_count": report["formula_count"],
                "locked_formulas": report["locked_formulas"],
                "formula_errors": report["formula_errors"],
            },
        },
        status=201,
    )


@bp.get("/tables/<int:table_id>")
@login_required
def get_table(table_id):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)
    data = table.to_dict(include_grid=True)
    data["can_manage"] = _can_manage(table)
    return api_success(data)


@bp.post("/tables/<int:table_id>/import")
@login_required
def import_table(table_id):
    table = _get_table_or_404(table_id)
    if table is None:
        return api_error("表格不存在", "table_not_found", 404)
    if not _can_manage(table):
        return api_error(
            "只有管理员或表格创建人可以导入文件",
            "permission_denied",
            403,
        )

    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return api_error("请选择要导入的文件", "missing_file", 400)
    try:
        parsed = parse_import_file(upload.filename, upload.read())
    except TableImportError as exc:
        return _import_error_response(exc)

    before_count = len(table.rows or [])
    before_columns = len(table.columns or [])
    before_version = _create_version(
        table,
        f"导入 {upload.filename} 前自动快照",
    )

    table.columns = parsed["columns"]
    table.rows = parsed["rows"]
    table.cell_meta = parsed["cell_meta"]
    table.row_seq = len(parsed["rows"])
    _touch(table)
    imported_version = _create_version(
        table,
        f"导入 {upload.filename}（{parsed['sheet_name']}）",
    )
    report = parsed["report"]
    change = _record_change(
        table,
        "import",
        detail={
            "filename": upload.filename,
            "extension": parsed["extension"],
            "sheet_name": parsed["sheet_name"],
            "before_rows": before_count,
            "before_columns": before_columns,
            "row_count": len(table.rows),
            "column_count": len(table.columns),
            "formula_count": report["formula_count"],
            "locked_formula_count": len(report["locked_formulas"]),
        },
    )
    db.session.commit()

    data = table.to_dict(include_grid=True)
    data["can_manage"] = True
    return api_success(
        {
            "table": data,
            "version": imported_version.to_dict(),
            "rollback_version": before_version.to_dict(),
            "summary": {
                "filename": upload.filename,
                "sheet_name": parsed["sheet_name"],
                "extension": parsed["extension"],
                "row_count": len(table.rows),
                "column_count": len(table.columns),
                "formula_count": report["formula_count"],
                "locked_formulas": report["locked_formulas"],
                "formula_errors": report["formula_errors"],
            },
            "change": change.to_dict(),
        }
    )


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

    meta_key = cell_meta_key(row_key, column_key)
    old_meta = dict((table.cell_meta or {}).get(meta_key) or {})
    if old_meta.get("locked"):
        return api_error(
            f"该单元格的公式已锁定：{old_meta.get('warning') or '暂不支持此公式'}",
            "cell_locked",
            409,
        )

    old_value = row.get("cells", {}).get(column_key, "")
    rows = [dict(item) for item in (table.rows or [])]
    target = next(item for item in rows if item["row_key"] == row_key)
    cells = dict(target.get("cells") or {})
    cells[column_key] = value
    target["cells"] = cells

    meta = {key: dict(item) for key, item in (table.cell_meta or {}).items()}
    if value.startswith("="):
        meta[meta_key] = {"formula": value, "locked": False}
    else:
        meta.pop(meta_key, None)

    try:
        columns, recalculated_rows, recalculated_meta, report = calculate_grid(
            table.columns or [], rows, meta
        )
    except (UnsupportedFormulaError, FormulaSyntaxError, FormulaError) as exc:
        return api_error(f"公式无法使用：{exc}", "invalid_formula", 400)

    if report["formula_errors"]:
        column_index = (table.columns or []).index(column)
        row_number = next(
            index
            for index, item in enumerate(recalculated_rows, start=2)
            if item["row_key"] == row_key
        )
        target_address = f"{_column_letters(column_index)}{row_number}"
        target_error = next(
            (
                item
                for item in report["formula_errors"]
                if item.get("cell") == target_address
            ),
            None,
        )
        if target_error:
            return api_error(
                f"公式无法使用：{target_error.get('error')}",
                "invalid_formula",
                400,
            )

    target = next(item for item in recalculated_rows if item["row_key"] == row_key)
    new_value = (target.get("cells") or {}).get(column_key, "")
    new_meta = recalculated_meta.get(meta_key) or {}
    if old_value == new_value and old_meta.get("formula") == new_meta.get("formula"):
        table.rows = recalculated_rows
        table.cell_meta = recalculated_meta
        return api_success(
            {"table": table.to_dict(include_grid=True), "change": None, "row": target}
        )

    table.rows = recalculated_rows
    table.cell_meta = recalculated_meta
    _touch(table)
    change = _record_change(
        table,
        "cell_update",
        row_key=row_key,
        column_key=column_key,
        column_name=column.get("name"),
        old_value=old_value,
        new_value=new_value,
        detail={
            "input_value": value,
            "formula": new_meta.get("formula"),
        },
    )
    db.session.commit()
    return api_success(
        {
            "table": table.to_dict(include_grid=True),
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

    next_row_seq = (table.row_seq or 0) + 1
    row = {"row_key": f"r{next_row_seq}", "cells": cells}
    rows = [dict(item) for item in (table.rows or [])]
    rows.append(row)
    meta = {key: dict(item) for key, item in (table.cell_meta or {}).items()}
    for key, value in cells.items():
        if value.startswith("="):
            meta[cell_meta_key(row["row_key"], key)] = {
                "formula": value,
                "locked": False,
            }
    try:
        columns, rows, meta, report = calculate_grid(table.columns or [], rows, meta)
    except (UnsupportedFormulaError, FormulaSyntaxError, FormulaError) as exc:
        return api_error(f"公式无法使用：{exc}", "invalid_formula", 400)
    if report["formula_errors"]:
        new_row_number = len(rows) + 1
        new_row_error = next(
            (
                item
                for item in report["formula_errors"]
                if item.get("cell", "").endswith(str(new_row_number))
            ),
            None,
        )
        if new_row_error:
            return api_error(
                f"公式无法使用：{new_row_error.get('error')}",
                "invalid_formula",
                400,
            )

    table.row_seq = next_row_seq
    table.rows = rows
    table.cell_meta = meta
    row = next(item for item in rows if item["row_key"] == row["row_key"])
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
            "table": table.to_dict(include_grid=True),
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
    deleted_row_number = next(
        index
        for index, item in enumerate(table.rows or [], start=2)
        if item["row_key"] == row_key
    )
    rows = [dict(item) for item in (table.rows or []) if item["row_key"] != row_key]
    meta = {}
    for key, item in (table.cell_meta or {}).items():
        if key.startswith(f"{row_key}:"):
            continue
        updated = dict(item)
        if updated.get("formula"):
            updated["formula"] = remap_formula_references(
                updated["formula"], deleted_rows={deleted_row_number}
            )
        meta[key] = updated
    try:
        columns, rows, meta, _report = calculate_grid(table.columns or [], rows, meta)
    except FormulaError as exc:
        return api_error(f"删除后公式无法计算：{exc}", "invalid_formula", 400)
    table.rows = rows
    table.cell_meta = meta
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
            "table": table.to_dict(include_grid=True),
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
    deleted_row_numbers = {
        index
        for index, item in enumerate(table.rows or [], start=2)
        if item["row_key"] in keys
    }
    rows = [
        dict(item) for item in (table.rows or []) if item["row_key"] not in keys
    ]
    meta = {}
    for key, item in (table.cell_meta or {}).items():
        if key.split(":", 1)[0] in keys:
            continue
        updated = dict(item)
        if updated.get("formula"):
            updated["formula"] = remap_formula_references(
                updated["formula"], deleted_rows=deleted_row_numbers
            )
        meta[key] = updated
    try:
        columns, rows, meta, _report = calculate_grid(table.columns or [], rows, meta)
    except FormulaError as exc:
        return api_error(f"删除后公式无法计算：{exc}", "invalid_formula", 400)
    table.rows = rows
    table.cell_meta = meta
    _touch(table)
    change = _record_change(
        table,
        "rows_delete",
        detail={"row_keys": row_keys, "rows": selected, "deleted_count": len(row_keys)},
    )
    db.session.commit()
    return api_success(
        {
            "table": table.to_dict(include_grid=True),
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
    try:
        columns, rows, meta, _report = calculate_grid(
            columns, table.rows or [], table.cell_meta or {}
        )
    except FormulaError as exc:
        return api_error(f"新增列后公式无法计算：{exc}", "invalid_formula", 400)
    table.columns = columns
    table.rows = rows
    table.cell_meta = meta
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
            "table": table.to_dict(include_grid=True),
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
    try:
        columns, rows, meta, _report = calculate_grid(
            columns, table.rows or [], table.cell_meta or {}
        )
    except FormulaError as exc:
        return api_error(f"调整列后公式无法计算：{exc}", "invalid_formula", 400)
    table.columns = columns
    table.rows = rows
    table.cell_meta = meta
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
    deleted_column_number = (table.columns or []).index(column) + 1
    meta = {}
    for key, item in (table.cell_meta or {}).items():
        if key.endswith(f":{column_key}"):
            continue
        updated = dict(item)
        if updated.get("formula"):
            updated["formula"] = remap_formula_references(
                updated["formula"], deleted_columns={deleted_column_number}
            )
        meta[key] = updated
    try:
        columns, rows, meta, _report = calculate_grid(columns, rows, meta)
    except FormulaError as exc:
        return api_error(f"删除列后公式无法计算：{exc}", "invalid_formula", 400)
    table.columns = columns
    table.rows = rows
    table.cell_meta = meta
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
            "table": table.to_dict(include_grid=True),
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
    deleted_column_numbers = {
        index
        for index, item in enumerate(table.columns or [], start=1)
        if item.get("key") in keys
    }
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
    meta = {}
    for key, item in (table.cell_meta or {}).items():
        if key.rsplit(":", 1)[-1] in keys:
            continue
        updated = dict(item)
        if updated.get("formula"):
            updated["formula"] = remap_formula_references(
                updated["formula"], deleted_columns=deleted_column_numbers
            )
        meta[key] = updated
    try:
        columns, rows, meta, _report = calculate_grid(columns, rows, meta)
    except FormulaError as exc:
        return api_error(f"删除列后公式无法计算：{exc}", "invalid_formula", 400)
    table.columns = columns
    table.rows = rows
    table.cell_meta = meta
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
            "table": table.to_dict(include_grid=True),
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
    table.cell_meta = snapshot.get("cell_meta") or {}
    try:
        columns, rows, meta, _report = calculate_grid(
            table.columns, table.rows, table.cell_meta
        )
    except FormulaError as exc:
        return api_error(f"版本中的公式无法计算：{exc}", "invalid_formula", 400)
    table.columns = columns
    table.rows = rows
    table.cell_meta = meta
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
