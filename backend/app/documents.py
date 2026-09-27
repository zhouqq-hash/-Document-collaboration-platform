import io
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, request, send_file
from flask_login import current_user, login_required

from . import db
from .models import Document, DocumentCategory, DocumentVersion, User
from .utils import api_error, api_success


bp = Blueprint("documents", __name__, url_prefix="/api")

DOCUMENT_STATUSES = {"active", "archived", "deprecated"}

#四个辅助函数
def _get_category_or_404(category_id):
    return db.session.get(DocumentCategory, category_id)


def _get_document_or_404(document_id):
    return db.session.get(Document, document_id)


def _allowed_file(filename):
    if "." not in filename:
        return False
    extension = filename.rsplit(".", 1)[1].lower()
    return extension in current_app.config["ALLOWED_EXTENSIONS"]


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _save_file(file_storage, document_id, version_number):
    original_name = file_storage.filename or "upload"
    extension = Path(original_name).suffix.lower()
    stored_name = (
        f"doc_{document_id}_v{version_number}_"
        f"{int(time.time() * 1000)}{extension}"
    )
    current_app.extensions["storage"].save(file_storage, stored_name)
    return original_name, stored_name

#版本管理
def _create_version(document, file_storage, changelog):
    if file_storage is None or not file_storage.filename:
        raise ValueError("必须选择文件")
    if not _allowed_file(file_storage.filename):
        raise ValueError("不支持的文件类型")

    next_number = max(
        (version.version_number for version in document.versions), default=0
    ) + 1
    original_name, stored_name = _save_file(
        file_storage, document.id, next_number
    )
    version = DocumentVersion(
        document=document,
        version_number=next_number,
        filename=original_name,
        file_path=stored_name,
        changelog=(changelog or "").strip(),
        uploader=current_user,
    )
    db.session.add(version)
    document.updated_at = datetime.now(timezone.utc)
    return version

#分类接口
@bp.get("/categories")
@login_required
def list_categories():
    categories = DocumentCategory.query.order_by(
        DocumentCategory.sort_order, DocumentCategory.id
    ).all()
    return api_success([category.to_dict() for category in categories])


@bp.post("/categories")
@login_required
def create_category():
    if not current_user.is_admin:
        return api_error("没有权限执行此操作", "permission_denied", 403)

    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return api_error("分类名称不能为空", "invalid_name", 400)

    if DocumentCategory.query.filter_by(name=name).first() is not None:
        return api_error("分类名称已存在", "name_exists", 409)

    sort_order = payload.get("sort_order", 0)
    try:
        sort_order = int(sort_order)
    except (TypeError, ValueError):
        sort_order = 0

    category = DocumentCategory(name=name, sort_order=sort_order)
    db.session.add(category)
    db.session.commit()
    return api_success(category.to_dict(), status=201)


@bp.patch("/categories/<int:category_id>")
@login_required
def update_category(category_id):
    if not current_user.is_admin:
        return api_error("没有权限执行此操作", "permission_denied", 403)

    category = _get_category_or_404(category_id)
    if category is None:
        return api_error("分类不存在", "category_not_found", 404)

    payload = request.get_json(silent=True) or {}

    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            return api_error("分类名称不能为空", "invalid_name", 400)

        duplicate = DocumentCategory.query.filter(
            DocumentCategory.name == name,
            DocumentCategory.id != category.id,
        ).first()
        if duplicate is not None:
            return api_error("分类名称已存在", "name_exists", 409)
        category.name = name

    if "sort_order" in payload:
        try:
            category.sort_order = int(payload.get("sort_order"))
        except (TypeError, ValueError):
            category.sort_order = 0

    db.session.commit()
    return api_success(category.to_dict())


@bp.delete("/categories/<int:category_id>")
@login_required
def delete_category(category_id):
    if not current_user.is_admin:
        return api_error("没有权限执行此操作", "permission_denied", 403)

    category = _get_category_or_404(category_id)
    if category is None:
        return api_error("分类不存在", "category_not_found", 404)

    if category.documents:
        return api_error("该分类下还有文档，不能删除", "category_has_documents", 409)

    db.session.delete(category)
    db.session.commit()
    return "", 204


# 用户列表接口，供管理员在新建文档时选择负责人
@bp.get("/users")
@login_required
def list_users():
    if not current_user.is_admin:
        return api_error("没有权限执行此操作", "permission_denied", 403)

    users = User.query.order_by(User.role, User.name).all()
    return api_success([user.to_dict() for user in users])


# 文档接口
@bp.get("/documents")
@login_required
def list_documents():
    query = Document.query
    category_id = request.args.get("category_id", type=int)
    if category_id:
        query = query.filter_by(category_id=category_id)
    status = request.args.get("status")
    if status:
        query = query.filter_by(status=status)
    documents = query.order_by(Document.updated_at.desc()).all()
    return api_success([document.to_dict() for document in documents])


@bp.post("/documents")
@login_required
def create_document():
    if not current_user.is_admin:
        return api_error("没有权限执行此操作", "permission_denied", 403)

    title = (request.form.get("title") or "").strip()
    if not title:
        return api_error("文档标题不能为空", "invalid_title", 400)

    category = _get_category_or_404(request.form.get("category_id", type=int))
    if category is None:
        return api_error("分类不存在", "category_not_found", 404)

    owner = db.session.get(User, request.form.get("owner_id", type=int))
    if owner is None:
        return api_error("负责人不存在", "owner_not_found", 404)

    document = Document(title=title, category=category, owner=owner)
    db.session.add(document)
    db.session.flush()
    document.description = request.form.get("description", "")

    try:
        version = _create_version(
            document, request.files.get("file"), request.form.get("changelog")
        )
    except ValueError as exc:
        db.session.rollback()
        return api_error(str(exc), "invalid_file", 400)

    db.session.commit()
    return api_success(document.to_dict(include_versions=True), status=201)


@bp.get("/documents/<int:document_id>")
@login_required
def get_document(document_id):
    document = _get_document_or_404(document_id)
    if document is None:
        return api_error("文档不存在", "document_not_found", 404)
    return api_success(document.to_dict())


# 修改文档信息或负责人
@bp.patch("/documents/<int:document_id>")
@login_required
def update_document(document_id):
    if not current_user.is_admin:
        return api_error("没有权限执行此操作", "permission_denied", 403)

    document = _get_document_or_404(document_id)
    if document is None:
        return api_error("文档不存在", "document_not_found", 404)

    payload = request.get_json(silent=True) or {}

    if "title" in payload:
        title = (payload.get("title") or "").strip()
        if not title:
            return api_error("文档标题不能为空", "invalid_title", 400)
        document.title = title

    if "category_id" in payload:
        category_id = _as_int(payload.get("category_id"))
        category = _get_category_or_404(category_id)
        if category is None:
            return api_error("分类不存在", "category_not_found", 404)
        document.category = category

    if "owner_id" in payload:
        owner_id = _as_int(payload.get("owner_id"))
        owner = db.session.get(User, owner_id)
        if owner is None:
            return api_error("负责人不存在", "owner_not_found", 404)
        document.owner = owner

    if "description" in payload:
        document.description = (payload.get("description") or "").strip()

    if "status" in payload:
        status = (payload.get("status") or "").strip()
        if status not in DOCUMENT_STATUSES:
            return api_error("不支持的文档状态", "invalid_status", 400)
        document.status = status

    db.session.commit()
    return api_success(document.to_dict())


@bp.get("/documents/<int:document_id>/versions")
@login_required
def list_versions(document_id):
    document = _get_document_or_404(document_id)
    if document is None:
        return api_error("文档不存在", "document_not_found", 404)
    return api_success([version.to_dict() for version in document.versions])

#上传新版本
@bp.post("/documents/<int:document_id>/versions")
@login_required
def upload_version(document_id):
    document = _get_document_or_404(document_id)
    if document is None:
        return api_error("文档不存在", "document_not_found", 404)

    if not (current_user.is_admin or document.owner_id == current_user.id):
        return api_error("只有管理员或文档负责人可以上传新版本", "permission_denied", 403)

    try:
        version = _create_version(
            document, request.files.get("file"), request.form.get("changelog")
        )
    except ValueError as exc:
        db.session.rollback()
        return api_error(str(exc), "invalid_file", 400)

    db.session.commit()
    return api_success(version.to_dict(), status=201)

#下载版本
@bp.get(
    "/documents/<int:document_id>/versions/<int:version_id>/download"
)
@login_required
def download_version(document_id, version_id):
    document = _get_document_or_404(document_id)
    if document is None:
        return api_error("文档不存在", "document_not_found", 404)

    version = db.session.get(DocumentVersion, version_id)
    if version is None or version.document_id != document.id:
        return api_error("版本不存在", "version_not_found", 404)

    data = current_app.extensions["storage"].read(version.file_path)
    return send_file(
        io.BytesIO(data),
        as_attachment=True,
        download_name=version.filename,
    )
