import io
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, request, send_file
from flask_login import current_user, login_required

from . import ai, ai_review, db, review_templates
from .extract import ExtractError
from .models import (
    Document,
    DocumentAiReview,
    DocumentCategory,
    DocumentVersion,
    User,
    utcnow,
)
from .storage import StorageError
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


@bp.get("/review-templates")
@login_required
def list_review_templates():
    if not current_user.is_admin:
        return api_error("没有权限执行此操作", "permission_denied", 403)

    return api_success(review_templates.list_templates())


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

    try:
        default_spec_ids = ai_review.normalize_category_spec_ids(
            payload.get("default_spec_document_ids")
        )
    except ai_review.ReviewError as exc:
        return api_error(str(exc), "invalid_spec", exc.status)

    try:
        template_key = ai_review.normalize_category_template_key(
            payload.get(
                "review_template_key", "generic_document_v1"
            )
        )
    except ai_review.ReviewError as exc:
        return api_error(str(exc), "invalid_template", exc.status)

    category = DocumentCategory(
        name=name,
        sort_order=sort_order,
        default_spec_document_ids=default_spec_ids,
        review_template_key=template_key,
    )
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

    if "default_spec_document_ids" in payload:
        try:
            category.default_spec_document_ids = (
                ai_review.normalize_category_spec_ids(
                    payload.get("default_spec_document_ids")
                )
            )
        except ai_review.ReviewError as exc:
            return api_error(str(exc), "invalid_spec", exc.status)

    if "review_template_key" in payload:
        try:
            category.review_template_key = (
                ai_review.normalize_category_template_key(
                    payload.get("review_template_key")
                )
            )
        except ai_review.ReviewError as exc:
            return api_error(str(exc), "invalid_template", exc.status)

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
    if len(title) > 200:
        return api_error("文档标题不能超过 200 个字符", "invalid_title", 400)

    description = (request.form.get("description") or "").strip()
    if len(description) > 500:
        return api_error("文档说明不能超过 500 个字符", "invalid_description", 400)
    changelog = (request.form.get("changelog") or "").strip()
    if len(changelog) > 500:
        return api_error("版本说明不能超过 500 个字符", "invalid_changelog", 400)

    category = _get_category_or_404(request.form.get("category_id", type=int))
    if category is None:
        return api_error("分类不存在", "category_not_found", 404)

    owner = db.session.get(User, request.form.get("owner_id", type=int))
    if owner is None:
        return api_error("负责人不存在", "owner_not_found", 404)

    document = Document(title=title, category=category, owner=owner)
    db.session.add(document)
    db.session.flush()
    document.description = description

    try:
        version = _create_version(
            document, request.files.get("file"), changelog
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
    try:
        ai_review.create_auto_review(document, version, current_user)
    except Exception as exc:  # 预审排队失败不能影响版本上传本身
        current_app.logger.exception("创建自动预审任务失败: %s", exc)
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


#回滚版本：把历史版本复制成新的当前版本，版本号递增、历史不被覆盖
@bp.post("/documents/<int:document_id>/versions/<int:version_id>/rollback")
@login_required
def rollback_version(document_id, version_id):
    document = _get_document_or_404(document_id)
    if document is None:
        return api_error("文档不存在", "document_not_found", 404)

    if not (current_user.is_admin or document.owner_id == current_user.id):
        return api_error("只有管理员或文档负责人可以回滚版本", "permission_denied", 403)

    version = db.session.get(DocumentVersion, version_id)
    if version is None or version.document_id != document.id:
        return api_error("版本不存在", "version_not_found", 404)

    next_number = max(
        (item.version_number for item in document.versions), default=0
    ) + 1
    extension = Path(version.filename).suffix.lower()
    new_key = (
        f"doc_{document.id}_v{next_number}_{int(time.time() * 1000)}{extension}"
    )
    try:
        current_app.extensions["storage"].copy(version.file_path, new_key)
    except StorageError as exc:
        db.session.rollback()
        return api_error(str(exc), "storage_error", 500)

    new_version = DocumentVersion(
        document=document,
        version_number=next_number,
        filename=version.filename,
        file_path=new_key,
        changelog=f"回滚到版本 {version.version_number}",
        uploader=current_user,
    )
    db.session.add(new_version)
    document.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return api_success(new_version.to_dict(), status=201)


# ------------------------------------------------------------------ AI 辅助


def _resolve_ai_version(document, raw_version_id):
    """没传版本就用当前版本；传了就校验它确实属于这篇文档。"""
    if raw_version_id in (None, ""):
        return document.current_version, None

    version_id = _as_int(raw_version_id)
    if version_id is None:
        return None, api_error("版本参数不合法", "invalid_version", 400)

    version = db.session.get(DocumentVersion, version_id)
    if version is None or version.document_id != document.id:
        return None, api_error("版本不存在", "version_not_found", 404)
    return version, None


def _clean_history(raw_history):
    """只保留最近 8 轮、合法的 user/assistant 消息。"""
    history = []
    if not isinstance(raw_history, list):
        return history
    for item in raw_history[-8:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        content = content.strip()
        if content:
            history.append({"role": role, "content": content[:4000]})
    return history


def _build_qa_messages(document, version, text, question, history):
    system = (
        "你是教学文档协作平台的文档问答助手。"
        "只能依据下面提供的文档正文回答；正文里没有的信息必须明确说"
        "“文档中没有提到”，不要编造。回答使用中文，先给结论，再给依据；"
        "必要时引用原文关键句。"
    )
    context = (
        f"文档标题：{document.title}\n"
        f"当前版本：v{version.version_number}\n"
        f"文件名：{version.filename}\n\n"
        f"文档正文：\n{text}"
    )
    messages = [{"role": "system", "content": system + "\n\n" + context}]
    messages.extend(history)
    messages.append({"role": "user", "content": question})
    return messages


@bp.post("/documents/<int:document_id>/ai/qa")
@login_required
def document_ai_qa(document_id):
    document = _get_document_or_404(document_id)
    if document is None:
        return api_error("文档不存在", "document_not_found", 404)

    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return api_error("请输入问题", "invalid_question", 400)
    if len(question) > 2000:
        return api_error(
            "问题太长，请控制在 2000 字以内", "question_too_long", 400
        )

    version, error = _resolve_ai_version(
        document, payload.get("version_id")
    )
    if error is not None:
        return error
    if version is None:
        return api_error(
            "文档还没有上传版本，无法问答", "no_version", 400
        )

    if not ai.is_configured():
        return api_error(
            "当前环境没有配置 COSMOS_API_KEY，无法使用 AI 问答",
            "ai_not_configured",
            503,
        )

    try:
        text = ai_review.read_version_text(version)
    except (ExtractError, StorageError, OSError) as exc:
        return api_error(
            f"无法读取文档正文：{exc}", "extract_failed", 422
        )

    text, truncated = ai_review.clip_text(
        text, current_app.config.get("AI_MAX_DOCUMENT_CHARS", 60000)
    )
    history = _clean_history(payload.get("history"))
    messages = _build_qa_messages(
        document, version, text, question, history
    )

    try:
        answer = ai.chat(
            messages,
            temperature=0.2,
            max_tokens=1200,
            timeout=current_app.config.get("COSMOS_QA_TIMEOUT", 120),
        )
    except ai.AIError as exc:
        return api_error(str(exc), "ai_failed", 502)

    return api_success(
        {
            "document_id": document.id,
            "version_id": version.id,
            "version_number": version.version_number,
            "question": question,
            "answer": (answer or "").strip(),
            "model": current_app.config.get("COSMOS_MODEL", ""),
            "truncated": truncated,
        }
    )


@bp.post("/documents/<int:document_id>/ai/review")
@login_required
def document_ai_review(document_id):
    document = _get_document_or_404(document_id)
    if document is None:
        return api_error("文档不存在", "document_not_found", 404)
    if not (current_user.is_admin or document.owner_id == current_user.id):
        return api_error(
            "只有管理员或文档负责人可以发起 AI 预审",
            "permission_denied",
            403,
        )

    payload = request.get_json(silent=True) or {}
    version, error = _resolve_ai_version(
        document, payload.get("version_id")
    )
    if error is not None:
        return error
    if version is None:
        return api_error(
            "文档还没有上传版本，无法预审", "no_version", 400
        )

    if not ai.is_configured():
        return api_error(
            "当前环境没有配置 COSMOS_API_KEY，无法使用 AI 预审",
            "ai_not_configured",
            503,
        )

    try:
        spec_ids = ai_review.normalize_spec_ids(
            document, payload.get("spec_document_ids")
        )
    except ai_review.ReviewError as exc:
        return api_error(str(exc), "invalid_spec", exc.status)

    review = ai_review.create_review(
        document,
        version,
        current_user,
        source="manual",
        spec_ids=spec_ids,
    )
    review = ai_review.perform_review(review.id)
    if review is None:
        return api_error("预审任务不存在", "review_not_found", 404)
    if review.status != "done":
        return api_error(
            review.error_message or "预审失败", "ai_review_failed", 502
        )
    return api_success(review.to_dict(), status=201)


@bp.get("/documents/<int:document_id>/ai/reviews")
@login_required
def list_document_ai_reviews(document_id):
    document = _get_document_or_404(document_id)
    if document is None:
        return api_error("文档不存在", "document_not_found", 404)

    try:
        limit = int(request.args.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    limit = min(max(limit, 1), 30)

    reviews = (
        DocumentAiReview.query.filter_by(document_id=document.id)
        .order_by(
            DocumentAiReview.created_at.desc(),
            DocumentAiReview.id.desc(),
        )
        .limit(limit)
        .all()
    )
    return api_success([review.to_dict() for review in reviews])


@bp.patch(
    "/documents/<int:document_id>/ai/reviews/<int:review_id>/decision"
)
@login_required
def decide_document_ai_review(document_id, review_id):
    document = _get_document_or_404(document_id)
    if document is None:
        return api_error("文档不存在", "document_not_found", 404)
    if not (current_user.is_admin or document.owner_id == current_user.id):
        return api_error(
            "只有管理员或文档负责人可以确认预审结果",
            "permission_denied",
            403,
        )

    review = db.session.get(DocumentAiReview, review_id)
    if review is None or review.document_id != document.id:
        return api_error("预审记录不存在", "review_not_found", 404)
    if review.status != "done":
        return api_error(
            "只有已完成的预审才能人工确认",
            "review_not_done",
            409,
        )

    payload = request.get_json(silent=True) or {}
    decision = (payload.get("decision") or "").strip()
    if decision not in {"pass", "return"}:
        return api_error(
            "decision 只能是 pass 或 return",
            "invalid_decision",
            400,
        )

    note = (payload.get("note") or "").strip()[:2000]
    if decision == "return" and not note:
        return api_error(
            "退回修改时需要填写原因", "note_required", 400
        )

    review.human_decision = decision
    review.human_note = note
    review.human_reviewer = current_user
    review.human_reviewed_at = utcnow()
    db.session.commit()
    return api_success(review.to_dict())
