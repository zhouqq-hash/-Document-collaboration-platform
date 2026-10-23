import re
import sqlite3
import uuid
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import BASE_DIR, Config
from .storage import get_storage
from .utils import api_error, format_size_limit


db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_PROTOTYPE_MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
}


@event.listens_for(Engine, "connect")
def _configure_sqlite_connection(dbapi_connection, connection_record):
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA journal_mode=WAL")
    finally:
        cursor.close()


def _request_id():
    candidate = (request.headers.get("X-Request-ID") or "").strip()
    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def _api_error_response(message, code, status):
    response, status_code = api_error(message, code, status)
    response.headers["Cache-Control"] = "no-store"
    return response, status_code


def create_app(config=None):
    app = Flask(__name__)
    # 加载配置
    # 先加载默认配置，再用传入的字典覆盖，保证任何配置项都有兜底值
    app.config.from_object(Config)
    if isinstance(config, dict):
        app.config.from_mapping(config)
    else:
        app.config.from_object(config or Config)
    Path(BASE_DIR / "instance").mkdir(parents=True, exist_ok=True)

    app.logger.setLevel(app.config.get("LOG_LEVEL", "INFO"))
    app.json.ensure_ascii = False

    # 穿透/反向代理会把原始协议放在 X-Forwarded-Proto，不处理的话生成的回调地址会变成 http
    if app.config.get("TRUST_PROXY_HEADERS", True):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # 准备上传目录和其他路径
    upload_folder = Path(app.config.get("UPLOAD_FOLDER", Config.UPLOAD_FOLDER))
    upload_folder.mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = str(upload_folder)
    app.extensions["storage"] = get_storage(app)
    migrations_dir = str(Path(__file__).resolve().parent.parent / "db_migrations")
    prototype_dir = Path(__file__).resolve().parent.parent.parent / "prototype"

    # 绑定 Flask 扩展
    db.init_app(app)
    migrate.init_app(app, db, directory=migrations_dir)
    login_manager.init_app(app)

    @app.before_request
    def attach_request_id():
        g.request_id = _request_id()

    @app.after_request
    def finalize_response(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if (
            request.is_secure
            and app.config.get("APP_ENV") == "production"
        ):
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response

    # 登录用户加载函数
    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # 未登录时的统一响应
    @login_manager.unauthorized_handler
    def unauthorized():
        return (
            jsonify(
                {
                    "error": {
                        "code": "unauthorized",
                        "message": "请先登录",
                    }
                }
            ),
            401,
        )

    # 注册业务模块
    from . import auth, cli, documents, qa, tables, wechat

    app.register_blueprint(auth.bp)
    app.register_blueprint(documents.bp)
    app.register_blueprint(qa.bp)
    app.register_blueprint(tables.bp)
    app.register_blueprint(wechat.bp)
    cli.register_commands(app)

    # 存活检查不访问外部依赖，方便平台区分“进程活着”和“暂时不能接流量”。
    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/ready")
    def ready():
        checks = {}
        try:
            db.session.execute(text("SELECT 1 FROM users LIMIT 1"))
            checks["database"] = {"status": "ok"}
        except Exception as exc:
            db.session.rollback()
            app.logger.error(
                "readiness database check failed request_id=%s: %s",
                getattr(g, "request_id", ""),
                exc,
            )
            checks["database"] = {"status": "error"}
        finally:
            db.session.remove()

        try:
            app.extensions["storage"].probe()
            checks["storage"] = {"status": "ok"}
        except Exception as exc:
            app.logger.error(
                "readiness storage check failed request_id=%s: %s",
                getattr(g, "request_id", ""),
                exc,
            )
            checks["storage"] = {"status": "error"}

        is_ready = all(
            item.get("status") == "ok" for item in checks.values()
        )
        return (
            jsonify(
                {
                    "status": "ready" if is_ready else "not_ready",
                    "checks": checks,
                }
            ),
            200 if is_ready else 503,
        )

    @app.get("/favicon.ico")
    def favicon():
        # 浏览器默认会请求它，返回空响应，别让日志里全是 404
        return "", 204

    # 上传超过大小上限时，Flask 默认返回 HTML 错误页，前端读不到 JSON，
    # 只能显示「请求失败（413）」。这里统一成和其它接口一致的错误结构。
    @app.errorhandler(413)
    def payload_too_large(error):
        size = format_size_limit(app.config.get("MAX_CONTENT_LENGTH"))
        message = (
            f"上传文件超过 {size} 上限，请压缩后再上传"
            if size
            else "上传文件超过大小上限，请压缩后再上传"
        )
        return _api_error_response(message, "file_too_large", 413)

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return _api_error_response(
                "接口不存在", "route_not_found", 404
            )
        return "页面不存在", 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        if request.path.startswith("/api/"):
            return _api_error_response(
                "该接口不支持此请求方法", "method_not_allowed", 405
            )
        return "请求方法不允许", 405

    @app.errorhandler(IntegrityError)
    def integrity_error(error):
        db.session.rollback()
        app.logger.warning(
            "database conflict request_id=%s path=%s: %s",
            getattr(g, "request_id", ""),
            request.path,
            error,
        )
        if request.path.startswith("/api/"):
            return _api_error_response(
                "数据已发生变化或存在冲突，请刷新后重试",
                "data_conflict",
                409,
            )
        return "数据冲突", 409

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        db.session.rollback()
        app.logger.exception(
            "database operation failed request_id=%s path=%s",
            getattr(g, "request_id", ""),
            request.path,
        )
        if request.path.startswith("/api/"):
            return _api_error_response(
                "数据库暂时不可用，请稍后重试",
                "database_unavailable",
                503,
            )
        return "数据库暂时不可用", 503

    @app.errorhandler(500)
    def server_error(error):
        app.logger.exception(
            "unhandled error request_id=%s path=%s",
            getattr(g, "request_id", ""),
            request.path,
            exc_info=getattr(error, "original_exception", error),
        )
        if request.path.startswith("/api/"):
            return _api_error_response(
                "服务出现异常，请记录响应中的 request id 后联系管理员",
                "internal_error",
                500,
            )
        return "服务出现异常", 500

    # 托管前端原型（静态文件）
    @app.get("/")
    def prototype_index():
        return send_from_directory(prototype_dir, "index.html")

    @app.get("/<path:filename>")
    def prototype_static(filename):
        mimetype = _PROTOTYPE_MIME_TYPES.get(
            Path(filename).suffix.lower()
        )
        return send_from_directory(
            prototype_dir, filename, mimetype=mimetype
        )

    return app
