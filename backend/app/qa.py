from datetime import datetime, timezone

from flask import Blueprint, request
from flask_login import current_user, login_required

from . import db
from .models import QaStatement, QaTopic, iso_utc, utcnow
from .utils import api_error, api_success


bp = Blueprint("qa", __name__, url_prefix="/api/qa")

QA_POSITIONS = {"agree", "disagree", "neutral"}
POSITION_LABELS = {"agree": "赞成", "disagree": "反对", "neutral": "中立"}
TOPIC_STATUSES = {"open", "closed"}

# 「初步统一意见」的判定规则（MVP 采用规则汇总，不依赖外部模型）：
# 发言数 >= 2，且得票最多的立场占比 >= 2/3 时，判定「初步达成一致」。
CONSENSUS_MIN_STATEMENTS = 2


def _get_topic_or_404(topic_id):
    return db.session.get(QaTopic, topic_id)


def _parse_ends_at(value):
    """把 ISO 8601 字符串解析成 UTC 时间，空值返回 None，格式错误抛 ValueError。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError("invalid_ends_at")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ends_at_or_error(value):
    """解析结束时间；非法格式返回 (None, error_response)，否则返回 (ends_at, None)。"""
    try:
        ends_at = _parse_ends_at(value)
    except ValueError:
        return None, api_error(
            "结束时间格式不正确，请使用 ISO 8601 格式", "invalid_ends_at", 400
        )
    if ends_at is not None and ends_at <= utcnow():
        return None, api_error("结束时间必须是未来的时间", "invalid_ends_at", 400)
    return ends_at, None


def summarize_topic(topic):
    """按时间线聚合话题下所有发言，生成可验收的「初步统一意见」汇总。"""
    statements = topic.statements
    total = len(statements)
    counts = {"agree": 0, "disagree": 0, "neutral": 0}
    for statement in statements:
        counts[statement.position] = counts.get(statement.position, 0) + 1

    dominant = max(
        ("agree", "disagree", "neutral"),
        key=lambda position: (counts[position], -len(position)),
    )
    dominant_count = counts[dominant]

    consensus_reached = (
        total >= CONSENSUS_MIN_STATEMENTS
        and dominant_count > 0
        and dominant_count * 3 >= total * 2
    )

    if total == 0:
        summary_text = "暂无发言，尚未形成统一意见"
    elif consensus_reached:
        summary_text = (
            f"初步统一意见：{POSITION_LABELS[dominant]}"
            f"（{dominant_count}/{total}）"
        )
    else:
        summary_text = (
            f"意见尚未统一，多数倾向：{POSITION_LABELS[dominant]}"
            f"（{dominant_count}/{total}）"
        )

    return {
        "topic_id": topic.id,
        "statement_count": total,
        "speaker_count": len({s.author_id for s in statements}),
        "positions": counts,
        "dominant_position": dominant if total else None,
        "dominant_count": dominant_count,
        "consensus_reached": consensus_reached,
        "consensus_position": dominant if consensus_reached else None,
        "summary_text": summary_text,
        "latest_statement_at": (
            iso_utc(statements[-1].created_at) if statements else None
        ),
    }


@bp.get("/topics")
@login_required
def list_topics():
    topics = QaTopic.query.order_by(
        QaTopic.updated_at.desc(), QaTopic.id.desc()
    ).all()
    status = request.args.get("status")
    if status:
        topics = [topic for topic in topics if topic.effective_status == status]
    return api_success([topic.to_dict() for topic in topics])


@bp.post("/topics")
@login_required
def create_topic():
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    if not title:
        return api_error("话题标题不能为空", "invalid_title", 400)
    if len(title) > 200:
        return api_error("话题标题不能超过 200 字", "invalid_title", 400)

    description = (payload.get("description") or "").strip()
    if len(description) > 500:
        return api_error("话题说明不能超过 500 字", "invalid_description", 400)

    ends_at, error = _ends_at_or_error(payload.get("ends_at"))
    if error is not None:
        return error

    topic = QaTopic(
        title=title,
        description=description,
        creator=current_user,
        status="open",
        ends_at=ends_at,
    )
    db.session.add(topic)
    db.session.commit()
    return api_success(topic.to_dict(include_statements=True, summary=summarize_topic(topic)), status=201)


@bp.get("/topics/<int:topic_id>")
@login_required
def get_topic(topic_id):
    topic = _get_topic_or_404(topic_id)
    if topic is None:
        return api_error("话题不存在", "topic_not_found", 404)
    return api_success(
        topic.to_dict(include_statements=True, summary=summarize_topic(topic))
    )


@bp.get("/topics/<int:topic_id>/summary")
@login_required
def get_topic_summary(topic_id):
    topic = _get_topic_or_404(topic_id)
    if topic is None:
        return api_error("话题不存在", "topic_not_found", 404)
    return api_success(summarize_topic(topic))


@bp.post("/topics/<int:topic_id>/statements")
@login_required
def post_statement(topic_id):
    topic = _get_topic_or_404(topic_id)
    if topic is None:
        return api_error("话题不存在", "topic_not_found", 404)

    if topic.status == "closed":
        return api_error("该话题已结束，不能再发言", "topic_closed", 409)
    if topic.is_expired:
        return api_error("该话题已到设定的结束时间，不能再发言", "topic_closed", 409)

    payload = request.get_json(silent=True) or {}
    content = (payload.get("content") or "").strip()
    if not content:
        return api_error("发言内容不能为空", "invalid_content", 400)
    if len(content) > 2000:
        return api_error("发言内容不能超过 2000 字", "invalid_content", 400)

    position = (payload.get("position") or "neutral").strip()
    if position not in QA_POSITIONS:
        return api_error("不支持的立场，可选：agree / disagree / neutral", "invalid_position", 400)

    statement = QaStatement(
        topic=topic,
        author=current_user,
        position=position,
        content=content,
    )
    db.session.add(statement)
    topic.updated_at = utcnow()
    db.session.commit()
    return api_success(statement.to_dict(), status=201)


@bp.patch("/topics/<int:topic_id>")
@login_required
def update_topic(topic_id):
    topic = _get_topic_or_404(topic_id)
    if topic is None:
        return api_error("话题不存在", "topic_not_found", 404)

    if not (current_user.is_admin or topic.creator_id == current_user.id):
        return api_error("只有管理员或话题发起人可以结束话题", "permission_denied", 403)

    payload = request.get_json(silent=True) or {}

    if "status" in payload:
        status = (payload.get("status") or "").strip()
        if status not in TOPIC_STATUSES:
            return api_error("不支持的话题状态", "invalid_status", 400)
        topic.status = status

    if "ends_at" in payload:
        ends_at, error = _ends_at_or_error(payload.get("ends_at"))
        if error is not None:
            return error
        topic.ends_at = ends_at

    topic.updated_at = utcnow()
    db.session.commit()
    return api_success(topic.to_dict())
