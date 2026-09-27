import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def env_int(name, default):
    """读整数环境变量，写错时回落到默认值而不是启动失败。"""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return int(default)


class Config:
    SECRET_KEY = "dev-secret-change-me"
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(
        BASE_DIR / "instance" / "doc_collab.db"
    ).replace("\\", "/")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = BASE_DIR / "media"
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")
    COS_SECRET_ID = os.environ.get("COS_SECRET_ID")
    COS_SECRET_KEY = os.environ.get("COS_SECRET_KEY")
    COS_REGION = os.environ.get("COS_REGION")
    COS_BUCKET = os.environ.get("COS_BUCKET")
    # 微信登录：配好 APP_ID / APP_SECRET 走真实微信接口，没配就进演示模式
    WECHAT_APP_ID = os.environ.get("WECHAT_APP_ID", "")
    WECHAT_APP_SECRET = os.environ.get("WECHAT_APP_SECRET", "")
    WECHAT_REDIRECT_URI = os.environ.get("WECHAT_REDIRECT_URI", "")
    WECHAT_AUTHORIZE_MODE = os.environ.get("WECHAT_AUTHORIZE_MODE", "open")
    WECHAT_SCOPE = os.environ.get("WECHAT_SCOPE", "")
    WECHAT_DEFAULT_ROLE = os.environ.get("WECHAT_DEFAULT_ROLE", "teacher")
    WECHAT_RESULT_REDIRECT = os.environ.get(
        "WECHAT_RESULT_REDIRECT", "/documents/wechat-callback.html"
    )
    WECHAT_MOCK_ENABLED = os.environ.get("WECHAT_MOCK_ENABLED", "1").lower() not in {
        "0",
        "false",
        "no",
    }
    WECHAT_MOCK_OPENID = os.environ.get("WECHAT_MOCK_OPENID", "mock_openid_demo")
    WECHAT_MOCK_NICKNAME = os.environ.get("WECHAT_MOCK_NICKNAME", "微信演示用户")
    WECHAT_HTTP_TIMEOUT = env_int("WECHAT_HTTP_TIMEOUT", 5)
    # state 是签名令牌：有效期秒数，以及是否强制要求浏览器带回 session cookie
    WECHAT_STATE_MAX_AGE = env_int("WECHAT_STATE_MAX_AGE", 600)
    WECHAT_STATE_REQUIRE_SESSION = os.environ.get(
        "WECHAT_STATE_REQUIRE_SESSION", "0"
    ).lower() not in {"0", "false", "no"}
    # 内网穿透 / Nginx 会通过 X-Forwarded-* 告诉后端原始协议和域名
    TRUST_PROXY_HEADERS = os.environ.get("TRUST_PROXY_HEADERS", "1").lower() not in {
        "0",
        "false",
        "no",
    }
    ALLOWED_EXTENSIONS = {
        "pdf",
        "doc",
        "docx",
        "xls",
        "xlsx",
        "ppt",
        "pptx",
        "txt",
    }
