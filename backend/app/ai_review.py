"""文档 AI 预审任务服务。

预审既可以由用户在详情页手动发起，也可以在上传新版本后自动排队。
两者共用这里的一套读取正文、对照规范、调用模型和落库逻辑。
"""
import json
import re
import threading

from flask import current_app

from . import ai, db
from .extract import ExtractError, extract_text
from .models import Document, DocumentAiReview, utcnow
from .storage import StorageError


REVIEW_STATUSES = {"pending", "running", "done", "failed", "skipped"}
HUMAN_DECISIONS = {"pending", "pass", "return"}
REVIEW_VERDICTS = {"pass", "risk", "unknown"}
MAX_SPECS = 3


class ReviewError(Exception):
    """预审业务错误，status 对应返回给前端的 HTTP 状态码。"""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def read_version_text(version):
    data = current_app.extensions["storage"].read(version.file_path)
    return extract_text(version.filename, data)


def clip_text(text, limit):
    """截断超长正文，并告诉调用方是否发生了截断。"""
    try:
        limit = max(int(limit), 1000)
    except (TypeError, ValueError):
        limit = 60000
    if len(text) <= limit:
        return text, False
    return text[:limit] + "\n\n[正文过长，后面的内容已截断]", True


def normalize_spec_ids(document, raw_ids):
    """整理显式选择或分类默认的规范文档，最多 3 个。"""
    has_explicit = isinstance(raw_ids, list) and len(raw_ids) > 0
    candidates = (
        raw_ids
        if has_explicit
        else (document.category.default_spec_document_ids or [])
    )

    spec_ids = []
    for value in candidates:
        try:
            document_id = int(value)
        except (TypeError, ValueError):
            continue
        if document_id == document.id or document_id in spec_ids:
            continue
        if db.session.get(Document, document_id) is None:
            if has_explicit:
                raise ReviewError("参考规范文档不存在", 404)
            continue
        spec_ids.append(document_id)
        if len(spec_ids) >= MAX_SPECS:
            break

    if has_explicit and not spec_ids:
        raise ReviewError("参考规范参数不合法", 400)
    return spec_ids


def normalize_category_spec_ids(raw_ids):
    """校验分类配置的默认规范列表。"""
    if raw_ids in (None, ""):
        return []
    if not isinstance(raw_ids, list):
        raise ReviewError("default_spec_document_ids 必须是数组", 400)

    spec_ids = []
    for value in raw_ids:
        try:
            document_id = int(value)
        except (TypeError, ValueError):
            continue
        if document_id in spec_ids:
            continue
        if db.session.get(Document, document_id) is None:
            raise ReviewError("参考规范文档不存在", 404)
        spec_ids.append(document_id)
        if len(spec_ids) >= MAX_SPECS:
            break
    return spec_ids


def _load_specs(document, spec_ids):
    specs = []
    for document_id in spec_ids or []:
        if int(document_id) == document.id:
            continue
        spec = db.session.get(Document, int(document_id))
        if spec is None:
            raise ReviewError(
                f"参考规范文档不存在（ID {document_id}）", 404
            )
        if spec.current_version is None:
            raise ReviewError(
                f"参考规范《{spec.title}》还没有上传版本", 400
            )
        specs.append((spec, read_version_text(spec.current_version)))
    return specs


def _build_review_messages(
    document, version, text, previous, previous_text, specs
):
    system = (
        "你是教学文档的预审助手。请对给定的新版本做预审，检查："
        "1) 内容是否自相矛盾；2) 是否符合提供的规范/要求；"
        "3) 与上一版本相比改了什么、是否有关键内容缺失；"
        "4) 给出可执行的修改建议。只依据提供的材料判断，材料不足时 "
        "verdict 用 unknown，不要编造规范。必须只输出一个 JSON 对象，"
        "不要输出 Markdown 代码块或额外说明。JSON 结构："
        '{"verdict":"pass|risk|unknown","summary":"一句话结论",'
        '"issues":[{"severity":"high|medium|low",'
        '"category":"矛盾|合规|缺失|其他","location":"在文档中的位置",'
        '"description":"问题是什么","suggestion":"怎么改"}],'
        '"spec_checks":[{"spec":"规范名称","compliant":true,'
        '"note":"判断依据"}],'
        '"changes":[{"type":"新增|修改|删除|无变化",'
        '"description":"与上一版相比的变化"}]}'
    )

    parts = [
        f"文档标题：{document.title}",
        f"预审版本：v{version.version_number}（{version.filename}）",
        f"变更说明：{version.changelog or '未填写'}",
        "",
        "【新版本正文】",
        text,
    ]
    if previous is not None and previous_text:
        parts.extend(
            [
                "",
                f"【上一版本 v{previous.version_number} 正文】",
                previous_text,
            ]
        )
    else:
        parts.extend(["", "【上一版本】无（这是第一版）"])

    if specs:
        for spec, spec_text in specs:
            parts.extend(["", f"【参考规范：{spec.title}】", spec_text])
    else:
        parts.extend(
            ["", "【参考规范】未提供，只做内部一致性和版本变化检查"]
        )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(parts)},
    ]


def parse_review_result(raw):
    """模型可能包 ```json，尽量取出 JSON；失败时保留原文供人工看。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    data = None
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except (TypeError, ValueError):
                data = None

    if not isinstance(data, dict):
        return {
            "verdict": "unknown",
            "summary": text or "模型没有返回内容",
            "issues": [],
            "spec_checks": [],
            "changes": [],
            "parse_error": True,
        }

    verdict = data.get("verdict")
    data["verdict"] = verdict if verdict in REVIEW_VERDICTS else "unknown"
    data["summary"] = str(data.get("summary") or "")
    for key in ("issues", "spec_checks", "changes"):
        if not isinstance(data.get(key), list):
            data[key] = []
    return data


def create_review(document, version, requester, source="manual", spec_ids=None):
    if spec_ids is None:
        spec_ids = normalize_spec_ids(document, None)
    review = DocumentAiReview(
        document=document,
        version=version,
        requester=requester,
        source=source,
        status="pending",
        spec_document_ids=spec_ids,
        model=current_app.config.get("COSMOS_MODEL", ""),
    )
    db.session.add(review)
    db.session.commit()
    return review


def create_auto_review(document, version, requester):
    """上传新版本后创建自动预审任务；没配 Key 时留下一条跳过记录。"""
    if not current_app.config.get("AI_AUTO_REVIEW_ENABLED", True):
        return None

    try:
        spec_ids = normalize_spec_ids(document, None)
    except ReviewError:
        spec_ids = []

    review = create_review(
        document,
        version,
        requester,
        source="auto",
        spec_ids=spec_ids,
    )
    if not ai.is_configured():
        review.status = "skipped"
        review.error_message = "未配置 COSMOS_API_KEY，自动预审已跳过"
        review.finished_at = utcnow()
        db.session.commit()
        return review

    enqueue_review(current_app._get_current_object(), review.id)
    return review


def perform_review(review_id):
    """执行一条待处理任务。必须在 Flask app context 内调用。"""
    review = db.session.get(DocumentAiReview, review_id)
    if review is None:
        return None

    claimed = (
        db.session.query(DocumentAiReview)
        .filter(
            DocumentAiReview.id == review_id,
            DocumentAiReview.status == "pending",
        )
        .update(
            {
                DocumentAiReview.status: "running",
                DocumentAiReview.started_at: utcnow(),
                DocumentAiReview.error_message: "",
            },
            synchronize_session=False,
        )
    )
    db.session.commit()
    db.session.expire_all()
    review = db.session.get(DocumentAiReview, review_id)
    if not claimed:
        return review

    try:
        text = read_version_text(review.version)
        previous = next(
            (
                item
                for item in review.document.versions
                if item.version_number < review.version.version_number
            ),
            None,
        )
        previous_text = ""
        if previous is not None:
            try:
                previous_text = read_version_text(previous)
            except (ExtractError, StorageError, OSError):
                previous = None

        specs = _load_specs(review.document, review.spec_document_ids)

        max_chars = current_app.config.get("AI_MAX_REVIEW_CHARS", 80000)
        try:
            max_chars = max(int(max_chars), 3000)
        except (TypeError, ValueError):
            max_chars = 80000

        if specs:
            document_budget = int(max_chars * 0.55)
            previous_budget = int(max_chars * 0.2)
            spec_budget = max(
                max_chars - document_budget - previous_budget, 3000
            )
            per_spec_budget = max(spec_budget // len(specs), 1000)
        else:
            document_budget = int(max_chars * 0.75)
            previous_budget = max_chars - document_budget
            per_spec_budget = 0

        text, truncated_current = clip_text(text, document_budget)
        truncated_previous = False
        if previous_text:
            previous_text, truncated_previous = clip_text(
                previous_text, previous_budget
            )

        clipped_specs = []
        for spec, spec_text in specs:
            clipped, _ = clip_text(spec_text, per_spec_budget)
            clipped_specs.append((spec, clipped))

        raw = ai.chat(
            _build_review_messages(
                review.document,
                review.version,
                text,
                previous,
                previous_text,
                clipped_specs,
            ),
            temperature=0.1,
            max_tokens=2000,
            timeout=current_app.config.get("COSMOS_REVIEW_TIMEOUT", 180),
        )

        result = parse_review_result(raw)
        result["context_truncated"] = (
            truncated_current or truncated_previous
        )
        result["checked_spec_ids"] = [
            spec.id for spec, _ in clipped_specs
        ]

        review.result_json = json.dumps(result, ensure_ascii=False)
        review.verdict = result.get("verdict", "unknown")
        review.status = "done"
        review.finished_at = utcnow()
        review.error_message = ""
        db.session.commit()
        return review
    except ReviewError as exc:
        review.status = "failed"
        review.error_message = str(exc)
        review.finished_at = utcnow()
        db.session.commit()
        return review
    except (ExtractError, StorageError, OSError) as exc:
        review.status = "failed"
        review.error_message = f"无法读取文档正文：{exc}"
        review.finished_at = utcnow()
        db.session.commit()
        return review
    except ai.AIError as exc:
        review.status = "failed"
        review.error_message = str(exc)
        review.finished_at = utcnow()
        db.session.commit()
        return review
    except Exception as exc:  # 后台任务不能把异常吞掉，必须落成失败记录
        db.session.rollback()
        review = db.session.get(DocumentAiReview, review_id)
        if review is not None:
            review.status = "failed"
            review.error_message = f"预审执行失败：{exc}"
            review.finished_at = utcnow()
            db.session.commit()
        return review


def run_review(app, review_id):
    """在独立 app context 中执行任务，供后台线程调用。"""
    with app.app_context():
        return perform_review(review_id)


def enqueue_review(app, review_id):
    """同步模式用于测试，生产默认开一个后台线程。"""
    if app.config.get("AI_AUTO_REVIEW_SYNC", False):
        return run_review(app, review_id)

    thread = threading.Thread(
        target=run_review,
        args=(app, review_id),
        daemon=True,
        name=f"document-ai-review-{review_id}",
    )
    thread.start()
    return None
