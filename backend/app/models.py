import json
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db

USER_ROLES = {"admin", "teacher"}


def utcnow():
    return datetime.now(timezone.utc)


def iso_utc(dt):
    """把数据库里的 naive 时间当作 UTC 序列化，避免前端按本地时间误读。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# 用户表
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    # 微信建号没有密码，password_hash 允许为空，此时只能用微信登录
    password_hash = db.Column(db.String(255), nullable=True)
    role = db.Column(db.String(16), nullable=False, default="teacher")
    # 微信登录标识
    wechat_openid = db.Column(
        db.String(64), unique=True, nullable=True, index=True
    )
    wechat_unionid = db.Column(db.String(64), nullable=True)
    avatar_url = db.Column(db.String(255), nullable=True)
# 用户与文档的关系
    owned_documents = db.relationship("Document", back_populates="owner")
    uploaded_versions = db.relationship(
        "DocumentVersion", back_populates="uploader"
    )
    # 用户与问答模块的关系
    # qa_topics 里同时有 creator_id 和 conclusion_by_id 指向 users，这里指定 creator_id
    qa_topics = db.relationship(
        "QaTopic", back_populates="creator", foreign_keys="QaTopic.creator_id"
    )
    # qa_statements 里同时有 author_id 和 hidden_by_id 指向 users，这里指定 author_id
    qa_statements = db.relationship(
        "QaStatement", back_populates="author", foreign_keys="QaStatement.author_id"
    )
    # 用户与表格协作模块的关系
    tables = db.relationship("Table", back_populates="owner")
    table_changes = db.relationship(
        "TableChange", back_populates="editor", foreign_keys="TableChange.editor_id"
    )
    table_versions = db.relationship(
        "TableVersion", back_populates="editor", foreign_keys="TableVersion.editor_id"
    )
# 密码加密
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not password or not self.password_hash:
            # 微信建号没有密码，不参与工号密码登录
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def wechat_bound(self):
        return bool(self.wechat_openid)

    @property
    def password_login_enabled(self):
        return bool(self.password_hash)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "name": self.name,
            "role": self.role,
            "wechat_bound": self.wechat_bound,
            "password_login": self.password_login_enabled,
            "avatar_url": self.avatar_url or "",
        }

#DocumentCategory 分类表
class DocumentCategory(db.Model):
    __tablename__ = "document_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=True)
    # 该分类默认参考的规范文档 ID 列表（最多 3 个，由预审服务限制）
    default_spec_document_ids = db.Column(db.JSON, nullable=True, default=list)

    documents = db.relationship("Document", back_populates="category")

    def to_dict(self):
        spec_ids = []
        for value in self.default_spec_document_ids or []:
            try:
                spec_ids.append(int(value))
            except (TypeError, ValueError):
                continue
        spec_documents = []
        for document_id in spec_ids:
            document = db.session.get(Document, document_id)
            if document is not None:
                spec_documents.append(
                    {"id": document.id, "title": document.title}
                )
        return {
            "id": self.id,
            "name": self.name,
            "sort_order": self.sort_order,
            "document_count": len(self.documents),
            "default_spec_document_ids": spec_ids,
            "default_spec_documents": spec_documents,
            "created_at": iso_utc(self.created_at),
        }

#Document 文档表
class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("document_categories.id"), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    category = db.relationship("DocumentCategory", back_populates="documents")
    owner = db.relationship("User", back_populates="owned_documents")
    versions = db.relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number.desc()",
    )
    # 与问答模块打通：该文档下关联的话题
    qa_topics = db.relationship("QaTopic", back_populates="document")
    # AI 预审历史
    ai_reviews = db.relationship(
        "DocumentAiReview",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentAiReview.created_at.desc()",
    )
    description = db.Column(db.String(500), default="")
    status = db.Column(
        db.String(16), nullable=False, default="active", server_default="active"
    )
    
    #获取最新版本
    @property
    def current_version(self):
        return self.versions[0] if self.versions else None

    def to_dict(self, include_versions=False):
        data = {
            "id": self.id,
            "title": self.title,
            "category": self.category.to_dict(),
            "owner": self.owner.to_dict(),
            "current_version": (
                self.current_version.to_dict() if self.current_version else None
            ),
            "updated_at": iso_utc(self.updated_at),
            "description": self.description,
            "status": self.status,
        }
        if include_versions:
            data["versions"] = [v.to_dict() for v in self.versions]
        return data

#DocumentVersion 版本表
class DocumentVersion(db.Model):
    __tablename__ = "document_versions"
    __table_args__ = (
        db.UniqueConstraint(
            "document_id", "version_number", name="uq_document_version"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id"), nullable=False
    )
    version_number = db.Column(db.Integer, nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    changelog = db.Column(db.String(500), default="")
    uploader_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    document = db.relationship("Document", back_populates="versions")
    uploader = db.relationship("User", back_populates="uploaded_versions")
    ai_reviews = db.relationship("DocumentAiReview", back_populates="version")

    def to_dict(self):
        return {
            "id": self.id,
            "document_id": self.document_id,
            "version_number": self.version_number,
            "filename": self.filename,
            "changelog": self.changelog,
            "uploader": self.uploader.to_dict(),
            "created_at": iso_utc(self.created_at),
        }


# AI 预审结果表
class DocumentAiReview(db.Model):
    __tablename__ = "document_ai_reviews"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id"), nullable=False, index=True
    )
    version_id = db.Column(
        db.Integer,
        db.ForeignKey("document_versions.id"),
        nullable=False,
        index=True,
    )
    requester_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    status = db.Column(
        db.String(16), nullable=False, default="pending", index=True
    )
    source = db.Column(db.String(16), nullable=False, default="manual")
    spec_document_ids = db.Column(db.JSON, nullable=True, default=list)
    model = db.Column(db.String(120), default="")
    verdict = db.Column(db.String(16), nullable=False, default="unknown")
    result_json = db.Column(db.Text, nullable=False, default="{}")
    error_message = db.Column(db.Text, default="")
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    human_decision = db.Column(
        db.String(16), nullable=False, default="pending"
    )
    human_note = db.Column(db.Text, default="")
    human_reviewer_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )
    human_reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime, default=utcnow, nullable=False, index=True
    )

    document = db.relationship("Document", back_populates="ai_reviews")
    version = db.relationship("DocumentVersion", back_populates="ai_reviews")
    requester = db.relationship("User", foreign_keys=[requester_id])
    human_reviewer = db.relationship(
        "User", foreign_keys=[human_reviewer_id]
    )

    def to_dict(self):
        try:
            result = json.loads(self.result_json or "{}")
        except (TypeError, ValueError):
            result = {}
        spec_ids = []
        for value in self.spec_document_ids or []:
            try:
                spec_ids.append(int(value))
            except (TypeError, ValueError):
                continue
        return {
            "id": self.id,
            "document_id": self.document_id,
            "version_id": self.version_id,
            "version_number": (
                self.version.version_number if self.version else None
            ),
            "requester": self.requester.to_dict() if self.requester else None,
            "status": self.status or "pending",
            "source": self.source or "manual",
            "spec_document_ids": spec_ids,
            "model": self.model or "",
            "verdict": self.verdict or "unknown",
            "result": result,
            "error": self.error_message or "",
            "started_at": iso_utc(self.started_at),
            "finished_at": iso_utc(self.finished_at),
            "human_decision": self.human_decision or "pending",
            "human_note": self.human_note or "",
            "human_reviewer": (
                self.human_reviewer.to_dict()
                if self.human_reviewer
                else None
            ),
            "human_reviewed_at": iso_utc(self.human_reviewed_at),
            "created_at": iso_utc(self.created_at),
        }


# 问答模块：话题分类表
class QaTopicCategory(db.Model):
    __tablename__ = "qa_topic_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=True)

    topics = db.relationship("QaTopic", back_populates="category")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "sort_order": self.sort_order,
            "topic_count": len(self.topics),
            "created_at": iso_utc(self.created_at),
        }


# 问答模块：话题表
class QaTopic(db.Model):
    __tablename__ = "qa_topics"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), default="")
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(
        db.Integer, db.ForeignKey("qa_topic_categories.id"), nullable=True, index=True
    )
    # 与文档模块打通：可选关联到某个文档，甚至某个具体版本
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id"), nullable=True, index=True
    )
    version_id = db.Column(
        db.Integer, db.ForeignKey("document_versions.id"), nullable=True, index=True
    )
    # open：讨论中，closed：已结束，结束后不能再发言
    status = db.Column(
        db.String(16), nullable=False, default="open", server_default="open"
    )
    # 定时结束：到点后即使 status 仍是 open，也按已结束处理
    ends_at = db.Column(db.DateTime, nullable=True)
    # AI 决策摘要：按需生成后落库，下次打开直接展示；有新发言后由 ai_summary_stale 标记过期
    ai_summary = db.Column(db.Text, nullable=True)
    ai_summary_at = db.Column(db.DateTime, nullable=True)
    # 最终结论/决议：补录后可选回写到关联文档，形成「讨论 → 决议 → 文档」闭环
    conclusion = db.Column(db.Text, nullable=True)
    conclusion_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    conclusion_at = db.Column(db.DateTime, nullable=True)
    conclusion_shared = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0"
    )
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # qa_topics 有两个指向 users 的外键，这里显式指明创建人用的是 creator_id
    creator = db.relationship(
        "User", back_populates="qa_topics", foreign_keys=[creator_id]
    )
    category = db.relationship("QaTopicCategory", back_populates="topics")
    document = db.relationship("Document", back_populates="qa_topics")
    version = db.relationship("DocumentVersion")
    conclusion_author = db.relationship("User", foreign_keys=[conclusion_by_id])
    statements = db.relationship(
        "QaStatement",
        back_populates="topic",
        cascade="all, delete-orphan",
        order_by="QaStatement.created_at.asc(), QaStatement.id.asc()",
    )

    @property
    def is_expired(self):
        if self.ends_at is None:
            return False
        ends = self.ends_at
        if ends.tzinfo is None:
            ends = ends.replace(tzinfo=timezone.utc)
        return ends <= utcnow()

    @property
    def effective_status(self):
        if self.status == "closed" or self.is_expired:
            return "closed"
        return "open"

    @property
    def ai_summary_stale(self):
        """AI 摘要生成之后又有新发言，说明它已经过期。"""
        if self.ai_summary_at is None:
            return False
        generated = self.ai_summary_at
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        if not self.statements:
            return False
        latest = self.statements[-1].created_at
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        return latest > generated

    def to_dict(self, include_statements=False, summary=None, include_hidden=False):
        all_statements = self.statements
        # 被隐藏的发言不参与统计，也不出现在普通用户的时间线里
        visible = [item for item in all_statements if not item.hidden]
        data = {
            "id": self.id,
            "title": self.title,
            "description": self.description or "",
            "status": self.effective_status,
            "ends_at": iso_utc(self.ends_at),
            "expired": self.is_expired,
            "creator": self.creator.to_dict(),
            "category": self.category.to_dict() if self.category else None,
            "document": (
                {
                    "id": self.document.id,
                    "title": self.document.title,
                    "status": self.document.status,
                }
                if self.document
                else None
            ),
            "version": (
                {
                    "id": self.version.id,
                    "version_number": self.version.version_number,
                    "filename": self.version.filename,
                }
                if self.version
                else None
            ),
            "created_at": iso_utc(self.created_at),
            "updated_at": iso_utc(self.updated_at),
            "statement_count": len(visible),
            "speaker_count": len({item.author_id for item in visible}),
            "hidden_statement_count": len(all_statements) - len(visible),
            "latest_statement_at": (
                iso_utc(visible[-1].created_at) if visible else None
            ),
        }
        if include_statements:
            shown = all_statements if include_hidden else visible
            data["statements"] = [item.to_dict() for item in shown]
            data["summary"] = summary or {}
            # AI 摘要只在详情里返回，列表项不必背着这段长文本
            data["ai_summary"] = (
                {
                    "text": self.ai_summary,
                    "generated_at": iso_utc(self.ai_summary_at),
                    "stale": self.ai_summary_stale,
                }
                if self.ai_summary
                else None
            )
            data["conclusion"] = (
                {
                    "text": self.conclusion,
                    "by": (
                        self.conclusion_author.to_dict()
                        if self.conclusion_author
                        else None
                    ),
                    "at": iso_utc(self.conclusion_at),
                    "shared": bool(self.conclusion_shared),
                }
                if self.conclusion
                else None
            )
        return data


# 问答模块：发言表（只增不改不删，保留发言人和时间记录）
class QaStatement(db.Model):
    __tablename__ = "qa_statements"

    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(
        db.Integer, db.ForeignKey("qa_topics.id"), nullable=False, index=True
    )
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # 立场：agree 赞成 / disagree 反对 / neutral 中立
    position = db.Column(
        db.String(16), nullable=False, default="neutral", server_default="neutral"
    )
    content = db.Column(db.String(2000), nullable=False)
    # 管理员隐藏（软删除）：原文与发言记录都保留，便于追溯和恢复
    hidden = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    hidden_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    hidden_at = db.Column(db.DateTime, nullable=True)
    hidden_reason = db.Column(db.String(200), default="")
    # 回复/引用：parent_id 指向被回复的发言，quote_statement_id 指向被引用的发言
    parent_id = db.Column(
        db.Integer, db.ForeignKey("qa_statements.id"), nullable=True, index=True
    )
    quote_statement_id = db.Column(
        db.Integer, db.ForeignKey("qa_statements.id"), nullable=True, index=True
    )
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    topic = db.relationship("QaTopic", back_populates="statements")
    # qa_statements 有两个指向 users 的外键，这里显式指明作者用的是 author_id
    author = db.relationship(
        "User", back_populates="qa_statements", foreign_keys=[author_id]
    )
    hidden_by = db.relationship("User", foreign_keys=[hidden_by_id])
    parent = db.relationship(
        "QaStatement",
        remote_side=[id],
        foreign_keys=[parent_id],
        backref=db.backref(
            "replies",
            order_by="QaStatement.created_at.asc(), QaStatement.id.asc()",
        ),
    )
    quoted_statement = db.relationship(
        "QaStatement",
        remote_side=[id],
        foreign_keys=[quote_statement_id],
    )

    @staticmethod
    def _reference_dict(statement):
        if statement is None:
            return None
        return {
            "id": statement.id,
            "author": statement.author.to_dict(),
            "content": statement.content,
            "created_at": iso_utc(statement.created_at),
        }

    def to_dict(self):
        return {
            "id": self.id,
            "topic_id": self.topic_id,
            "content": self.content,
            "position": self.position,
            "author": self.author.to_dict(),
            "created_at": iso_utc(self.created_at),
            "hidden": bool(self.hidden),
            "hidden_by": self.hidden_by.to_dict() if self.hidden_by else None,
            "hidden_at": iso_utc(self.hidden_at),
            "hidden_reason": self.hidden_reason or "",
            "parent_id": self.parent_id,
            "quote_statement_id": self.quote_statement_id,
            "parent": self._reference_dict(self.parent),
            "quoted": self._reference_dict(self.quoted_statement),
        }


# 问答模块：举报表（教师举报发言，管理员处理）
class QaReport(db.Model):
    __tablename__ = "qa_reports"

    id = db.Column(db.Integer, primary_key=True)
    statement_id = db.Column(
        db.Integer, db.ForeignKey("qa_statements.id"), nullable=False, index=True
    )
    topic_id = db.Column(
        db.Integer, db.ForeignKey("qa_topics.id"), nullable=False, index=True
    )
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    # pending：待处理；resolved：已处理（发言被隐藏）；dismissed：已驳回
    status = db.Column(
        db.String(16), nullable=False, default="pending", server_default="pending"
    )
    handled_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    handled_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    statement = db.relationship("QaStatement")
    topic = db.relationship("QaTopic")
    reporter = db.relationship("User", foreign_keys=[reporter_id])
    handled_by = db.relationship("User", foreign_keys=[handled_by_id])

    def to_dict(self):
        return {
            "id": self.id,
            "statement_id": self.statement_id,
            "topic_id": self.topic_id,
            "reason": self.reason,
            "status": self.status,
            "reporter": self.reporter.to_dict() if self.reporter else None,
            "handled_by": self.handled_by.to_dict() if self.handled_by else None,
            "handled_at": iso_utc(self.handled_at),
            "created_at": iso_utc(self.created_at),
        }


# 问答模块：站内通知
class QaNotification(db.Model):
    __tablename__ = "qa_notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    topic_id = db.Column(db.Integer, db.ForeignKey("qa_topics.id"), nullable=True)
    # report_created / statement_hidden / report_resolved / report_dismissed
    kind = db.Column(db.String(32), nullable=False, default="info")
    message = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "topic_id": self.topic_id,
            "kind": self.kind,
            "message": self.message,
            "read": bool(self.is_read),
            "created_at": iso_utc(self.created_at),
        }


# 表格协作模块：表格表
class Table(db.Model):
    __tablename__ = "tables"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(500), default="")
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # columns: [{"key": "col1", "name": "姓名", "type": "text"}, ...]
    columns = db.Column(db.JSON, nullable=False, default=list)
    # rows: [{"row_key": "r1", "cells": {"col1": "张三", ...}}, ...]
    rows = db.Column(db.JSON, nullable=False, default=list)
    # cell_meta: {"r1:col3": {"formula": "=B2*C2", "locked": false, ...}}
    cell_meta = db.Column(db.JSON, nullable=True, default=dict)
    # 行号自增计数器，保证删除行后新行的 row_key 也不会重复
    row_seq = db.Column(db.Integer, nullable=False, default=0)
    version_number = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    owner = db.relationship("User", back_populates="tables")
    versions = db.relationship(
        "TableVersion",
        back_populates="table",
        cascade="all, delete-orphan",
        order_by="TableVersion.version_number.desc()",
    )
    changes = db.relationship(
        "TableChange",
        back_populates="table",
        cascade="all, delete-orphan",
        order_by="TableChange.created_at.desc(), TableChange.id.desc()",
    )

    @property
    def column_keys(self):
        return [item["key"] for item in (self.columns or [])]

    def _summary(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "owner": self.owner.to_dict(),
            "column_count": len(self.columns or []),
            "row_count": len(self.rows or []),
            "version_number": self.version_number,
            "created_at": iso_utc(self.created_at),
            "updated_at": iso_utc(self.updated_at),
        }

    def to_dict(self, include_grid=False):
        data = self._summary()
        if include_grid:
            data["columns"] = self.columns or []
            data["rows"] = self.rows or []
            data["cell_meta"] = self.cell_meta or {}
        return data


# 表格协作模块：版本快照表（整表回滚的最小粒度）
class TableVersion(db.Model):
    __tablename__ = "table_versions"
    __table_args__ = (
        db.UniqueConstraint("table_id", "version_number", name="uq_table_version"),
    )

    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(
        db.Integer, db.ForeignKey("tables.id"), nullable=False, index=True
    )
    version_number = db.Column(db.Integer, nullable=False)
    # snapshot: {"columns": [...], "rows": [...]}，即该版本时的完整表格状态
    snapshot = db.Column(db.JSON, nullable=False)
    changelog = db.Column(db.String(500), default="")
    editor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    table = db.relationship("Table", back_populates="versions")
    editor = db.relationship(
        "User", back_populates="table_versions", foreign_keys=[editor_id]
    )

    def to_dict(self, include_snapshot=False):
        data = {
            "id": self.id,
            "table_id": self.table_id,
            "version_number": self.version_number,
            "changelog": self.changelog or "",
            "editor": self.editor.to_dict(),
            "created_at": iso_utc(self.created_at),
            "column_count": len((self.snapshot or {}).get("columns") or []),
            "row_count": len((self.snapshot or {}).get("rows") or []),
        }
        if include_snapshot:
            data["columns"] = (self.snapshot or {}).get("columns") or []
            data["rows"] = (self.snapshot or {}).get("rows") or []
            data["cell_meta"] = (self.snapshot or {}).get("cell_meta") or {}
        return data


# 表格协作模块：修改记录表（行内编辑、增删行列、回滚等操作的审计日志）
class TableChange(db.Model):
    __tablename__ = "table_changes"

    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(
        db.Integer, db.ForeignKey("tables.id"), nullable=False, index=True
    )
    editor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # cell_update / row_add / row_delete / column_add / rename / rollback
    kind = db.Column(db.String(32), nullable=False, default="cell_update")
    row_key = db.Column(db.String(64), nullable=True)
    column_key = db.Column(db.String(64), nullable=True)
    column_name = db.Column(db.String(80), nullable=True)
    old_value = db.Column(db.Text, default="")
    new_value = db.Column(db.Text, default="")
    # 结构化补充信息，例如被删除的行、被回滚的版本号等
    detail = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    table = db.relationship("Table", back_populates="changes")
    editor = db.relationship(
        "User", back_populates="table_changes", foreign_keys=[editor_id]
    )

    def to_dict(self):
        return {
            "id": self.id,
            "table_id": self.table_id,
            "kind": self.kind,
            "editor": self.editor.to_dict(),
            "row_key": self.row_key,
            "column_key": self.column_key,
            "column_name": self.column_name or "",
            "old_value": self.old_value or "",
            "new_value": self.new_value or "",
            "detail": self.detail or {},
            "created_at": iso_utc(self.created_at),
        }
