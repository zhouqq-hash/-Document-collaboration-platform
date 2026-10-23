"""文档 AI 预审任务服务。

预审既可以由用户在详情页手动发起，也可以在上传新版本后自动排队。
两者共用这里的一套读取正文、对照规范、调用模型和落库逻辑。
"""
import json
import re
import threading

from flask import current_app

from . import ai, db, review_templates
from .extract import ExtractError, extract_text
from .models import Document, DocumentAiReview, DocumentVersion, utcnow
from .storage import StorageError


REVIEW_STATUSES = {"pending", "running", "done", "failed", "skipped"}
HUMAN_DECISIONS = {"pending", "pass", "return"}
REVIEW_VERDICTS = {"pass", "risk", "unknown"}
CHECK_STATUSES = {"pass", "fail", "unknown"}
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


def normalize_category_template_key(raw_key):
    try:
        return review_templates.validate_template_key(raw_key)
    except ValueError as exc:
        raise ReviewError(str(exc), 400) from exc


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
    document,
    version,
    text,
    previous,
    previous_text,
    specs,
    previous_review=None,
    template=None,
    checklist=None,
):
    template = template or review_templates.get_template(None)
    checklist = checklist or template["rules"]
    system = (
        "你是严格的文档规范预审助手。你必须逐项执行用户提供的检查清单，"
        "不能增加、删除、合并或改写规则。只依据给出的文档正文、上一版正文、"
        "参考规范和上次退回记录判断；材料不足时必须返回 unknown，"
        "不得编造规范、原文或数字。严重程度和是否必检由系统规则决定，"
        "你不要自行修改。每个规则必须返回且只返回一条 check_results。"
        "只有失败项才写入 issues，issues 必须关联 rule_id。"
        "若有上次退回问题，再逐条输出 previous_issue_checks。"
        "必须只输出一个 JSON 对象，不要输出 Markdown 代码块或额外说明。"
        "JSON 结构："
        '{"summary":"一句话结论",'
        '"check_results":[{"rule_id":"规则ID",'
        '"status":"pass|fail|unknown",'
        '"location":"原文位置",'
        '"evidence":"支撑判断的原文或规范短句",'
        '"explanation":"判断说明",'
        '"suggestion":"可执行修改建议，通过时可为空"}],'
        '"issues":[{"rule_id":"规则ID",'
        '"severity":"high|medium|low","category":"矛盾|合规|缺失|其他",'
        '"location":"原文位置","evidence":"原文或规范依据",'
        '"description":"问题是什么","suggestion":"怎么改"}],'
        '"spec_checks":[{"spec":"规范名称","compliant":true,'
        '"note":"判断依据"}],'
        '"changes":[{"type":"新增|修改|删除|无变化",'
        '"description":"与上一版相比的变化"}],'
        '"previous_issue_checks":[{"issue":"上次退回的问题",'
        '"status":"resolved|unresolved|unclear","note":"本次核对依据"}]}'
    )

    parts = [
        f"文档标题：{document.title}",
        f"预审版本：v{version.version_number}（{version.filename}）",
        f"变更说明：{version.changelog or '未填写'}",
        (
            f"【审核模板】{template['name']}"
            f"（{template['key']} / v{template['version']}）"
        ),
        "【检查清单】",
        json.dumps(checklist, ensure_ascii=False),
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

    if previous_review is not None:
        previous_issues = _review_issues(previous_review)
        parts.extend(
            [
                "",
                (
                    "【上次人工退回】"
                    f"退回版本 v{previous_review.version.version_number}"
                    f"；退回意见：{previous_review.human_note or '未填写'}"
                ),
                "【上次问题清单】",
                json.dumps(previous_issues, ensure_ascii=False),
                (
                    "请为上述每个问题输出一条 previous_issue_checks，"
                    "并结合本次正文和上一次版本判断是否已解决。"
                ),
            ]
        )

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


def _decode_review_payload(raw):
    """Decode plain or JSON-string-wrapped model output.

    Some OpenAI-compatible providers return a JSON object as a JSON string,
    so the first ``json.loads`` yields text rather than a dictionary. Unwrap a
    few layers without changing the original fallback shown to reviewers.
    """
    text = (raw or "").strip()
    for _ in range(3):
        if not text:
            return None
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            data = None
        if isinstance(data, dict):
            return data
        if isinstance(data, str):
            text = data.strip()
            continue

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except (TypeError, ValueError):
                data = None
            if isinstance(data, dict):
                return data
        return None
    return None


def parse_review_result(raw):
    """模型可能包 ```json，尽量取出 JSON；失败时保留原文供人工看。"""
    data = _decode_review_payload(raw)

    if not isinstance(data, dict):
        text = (raw or "").strip()
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
    for key in (
        "issues",
        "spec_checks",
        "changes",
        "previous_issue_checks",
        "check_results",
    ):
        if not isinstance(data.get(key), list):
            data[key] = []
    return data


def apply_checklist_result(result, checklist):
    """Normalize model output against the immutable checklist snapshot."""
    raw_checks = result.get("check_results")
    if not isinstance(raw_checks, list) or not raw_checks:
        # Backward compatibility for historical model responses. The UI still
        # shows the legacy issue list and warns that no checklist was returned.
        result["check_results"] = []
        result["checklist_summary"] = {
            "total": len(checklist),
            "pass": 0,
            "fail": 0,
            "unknown": 0,
            "available": False,
        }
        return result

    by_rule = {}
    for item in raw_checks:
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("rule_id") or "").strip()
        if rule_id and rule_id not in by_rule:
            by_rule[rule_id] = item

    normalized = []
    for rule in checklist:
        item = by_rule.get(rule["id"], {})
        status = str(item.get("status") or "unknown").strip().lower()
        if status not in CHECK_STATUSES:
            status = "unknown"
        normalized.append(
            {
                **rule,
                "rule_id": rule["id"],
                "status": status,
                "location": str(item.get("location") or ""),
                "evidence": str(item.get("evidence") or ""),
                "explanation": str(item.get("explanation") or ""),
                "suggestion": str(item.get("suggestion") or ""),
            }
        )

    result["check_results"] = normalized
    counts = {
        value: sum(
            1 for item in normalized if item["status"] == value
        )
        for value in ("pass", "fail", "unknown")
    }
    result["checklist_summary"] = {
        "total": len(normalized),
        **counts,
        "available": True,
    }

    failures = [item for item in normalized if item["status"] == "fail"]
    required_unknown = [
        item
        for item in normalized
        if item["required"] and item["status"] == "unknown"
    ]
    if failures:
        result["verdict"] = "risk"
    elif required_unknown:
        result["verdict"] = "unknown"
    else:
        result["verdict"] = "pass"

    result["issues"] = [
        {
            "rule_id": item["id"],
            "severity": item["severity"],
            "category": item["title"],
            "location": item["location"],
            "evidence": item["evidence"],
            "description": item["explanation"] or item["title"],
            "suggestion": item["suggestion"],
        }
        for item in failures
    ]
    return result


def _review_issues(review):
    try:
        result = json.loads(review.result_json or "{}")
    except (TypeError, ValueError):
        result = {}
    issues = result.get("issues")
    return issues if isinstance(issues, list) else []


def _find_previous_returned_review(document, version):
    """找同一文档上一版本最近一次人工退回记录。"""
    return (
        db.session.query(DocumentAiReview)
        .join(
            DocumentVersion,
            DocumentAiReview.version_id == DocumentVersion.id,
        )
        .filter(
            DocumentAiReview.document_id == document.id,
            DocumentAiReview.status == "done",
            DocumentAiReview.human_decision == "return",
            DocumentVersion.version_number < version.version_number,
        )
        .order_by(
            DocumentVersion.version_number.desc(),
            DocumentAiReview.created_at.desc(),
            DocumentAiReview.id.desc(),
        )
        .first()
    )


def create_review(document, version, requester, source="manual", spec_ids=None):
    if spec_ids is None:
        spec_ids = normalize_spec_ids(document, None)
    previous_review = _find_previous_returned_review(document, version)
    template = review_templates.resolve_template(document.category)
    review = DocumentAiReview(
        document=document,
        version=version,
        requester=requester,
        source=source,
        status="pending",
        previous_review=previous_review,
        spec_document_ids=spec_ids,
        review_template_key=template["key"],
        review_template_version=template["version"],
        checklist_json=template["rules"],
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
                review.previous_review,
                template=review_templates.get_template(
                    review.review_template_key
                ),
                checklist=(
                    review.checklist_json
                    or review_templates.resolve_template(
                        review.document.category
                    )["rules"]
                ),
            ),
            temperature=0.1,
            max_tokens=5000,
            timeout=current_app.config.get("COSMOS_REVIEW_TIMEOUT", 180),
        )

        result = parse_review_result(raw)
        result = apply_checklist_result(
            result,
            review.checklist_json
            or review_templates.resolve_template(
                review.document.category
            )["rules"],
        )
        result["template_key"] = review.review_template_key
        result["template_version"] = review.review_template_version
        result["context_truncated"] = (
            truncated_current or truncated_previous
        )
        result["checked_spec_ids"] = [
            spec.id for spec, _ in clipped_specs
        ]
        if review.previous_review is not None:
            checks = result.get("previous_issue_checks")
            if not checks:
                checks = [
                    {
                        "issue": issue.get("description")
                        or issue.get("category")
                        or "上次退回问题",
                        "status": "unclear",
                        "note": "模型未返回逐项核对结果，请人工确认。",
                    }
                    for issue in _review_issues(review.previous_review)
                ]
            result["previous_issue_checks"] = checks

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
