import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv():
    """从 backend/.env 读取本地密钥（该文件已被 .gitignore 忽略，不会提交）。"""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def env_int(name, default):
    """读整数环境变量，写错时回落到默认值而不是启动失败。"""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return int(default)


def env_bool(name, default):
    """读布尔环境变量；没设置时使用传入的默认值。"""
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return value.strip().lower() not in {"0", "false", "no", "off"}


class Config:
    # 生产环境（Render 等）用环境变量覆盖；没设时保留开发用的默认值
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
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
    # 硅基流动 SiliconFlow（OpenAI 兼容接口）：AI 问答和自动预审都走这里
    COSMOS_API_BASE = os.environ.get(
        "COSMOS_API_BASE", "https://api.siliconflow.cn/v1"
    ).rstrip("/")
    COSMOS_API_KEY = os.environ.get("COSMOS_API_KEY", "")
    COSMOS_MODEL = os.environ.get("COSMOS_MODEL", "deepseek-ai/DeepSeek-V4-Flash")
    # 问答要等模型写完答案，预审要读多份文档，所以超时分开设
    COSMOS_QA_TIMEOUT = env_int("COSMOS_QA_TIMEOUT", 120)
    COSMOS_REVIEW_TIMEOUT = env_int("COSMOS_REVIEW_TIMEOUT", 180)
    # 一次最多把多少正文交给模型，防止超长文件把上下文塞满
    AI_MAX_DOCUMENT_CHARS = env_int("AI_MAX_DOCUMENT_CHARS", 60000)
    AI_MAX_REVIEW_CHARS = env_int("AI_MAX_REVIEW_CHARS", 80000)
    # 上传新版本后是否自动创建预审任务；AI_AUTO_REVIEW_SYNC 仅测试时打开
    AI_AUTO_REVIEW_ENABLED = env_bool("AI_AUTO_REVIEW_ENABLED", True)
    AI_AUTO_REVIEW_SYNC = env_bool("AI_AUTO_REVIEW_SYNC", False)
    # AI 摘要走页面交互，等待时间要明显短于问答，避免用户干等
    COSMOS_SUMMARY_TIMEOUT = env_int("COSMOS_SUMMARY_TIMEOUT", 30)
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
