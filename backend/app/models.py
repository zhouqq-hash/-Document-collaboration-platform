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

    documents = db.relationship("Document", back_populates="category")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "sort_order": self.sort_order,
            "document_count": len(self.documents),
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
