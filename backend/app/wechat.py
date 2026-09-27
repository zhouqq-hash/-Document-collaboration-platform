"""微信登录：开放平台「网站应用扫码登录」和公众号「网页授权」。

两种运行模式：

- ``live``：配置了 ``WECHAT_APP_ID`` / ``WECHAT_APP_SECRET``，走真实的微信 OAuth 接口。
- ``mock``：没配置时默认进入演示模式，用本地模拟登录跑通页面和测试，离线也能演示。

接口前缀是 ``/api/auth/wechat``。配置说明见 ``docs/wechat-login-guide.md``。
"""

import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit

from flask import Blueprint, current_app, redirect, request, session, url_for
from flask_login import current_user, login_required, login_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import db
from .models import USER_ROLES, User
from .utils import api_error, api_success

bp = Blueprint("wechat", __name__, url_prefix="/api/auth/wechat")

# 微信官方接口地址
OPEN_AUTHORIZE_URL = "https://open.weixin.qq.com/connect/qrconnect"
MP_AUTHORIZE_URL = "https://open.weixin.qq.com/connect/oauth2/authorize"
ACCESS_TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"
USERINFO_URL = "https://api.weixin.qq.com/sns/userinfo"
# 用 client_credential 换 access_token，用来验证 AppID / AppSecret 是否配对
CREDENTIAL_URL = "https://api.weixin.qq.com/cgi-bin/token"

OPEN_SCOPE = "snsapi_login"
MP_SCOPE = "snsapi_userinfo"

# 每个模式允许的 scope：配错了微信会直接回「Scope 参数错误或没有 Scope 权限」
OPEN_SCOPES = {"snsapi_login"}
MP_SCOPES = {"snsapi_base", "snsapi_userinfo"}

STATE_SESSION_KEY = "wechat_oauth_state"
BIND_SESSION_KEY = "wechat_bind_user_id"
STATE_SALT = "wechat-oauth-state"

# ngrok / cpolar 的本地 API：默认都监听 4040，可以用来查当前公网地址
TUNNEL_API_PORTS = (4040, 4041)
TUNNEL_API_PATH = "/api/tunnels"

DEFAULT_MOCK_OPENID = "mock_openid_demo"
DEFAULT_MOCK_NICKNAME = "微信演示用户"

# 事件日志文件名：放在上传目录同级的 instance/ 下
LOG_FILENAME = "wechat-log.txt"

# 文档里用的示例域名：联调时如果还留着它，说明参数没换成自己的
PLACEHOLDER_HOSTS = {"abcd-1234.ngrok-free.app", "doc.example.edu.cn"}

# 微信绑定失败时的提示文案
BIND_ERROR_MESSAGES = {
    "wechat_already_bound": "该微信已经绑定了其他账号，请先在原账号解绑",
    "account_already_bound": "当前账号已经绑定过其他微信，请先解绑",
    "wechat_missing_openid": "微信没有返回 openid，请重新扫码",
}


class WeChatAPIError(RuntimeError):
    """调用微信接口失败。"""


def is_configured():
    """是否配置了真实的微信应用信息。"""
    return bool(current_app.config.get("WECHAT_APP_ID")) and bool(
        current_app.config.get("WECHAT_APP_SECRET")
    )


def mock_enabled():
    """演示模式开关：配了真实应用信息就不再提供模拟登录。"""
    if is_configured():
        return False
    return bool(current_app.config.get("WECHAT_MOCK_ENABLED"))


def current_mode():
    if is_configured():
        return "live"
    return "mock" if mock_enabled() else "disabled"


def event_log_path():
    """事件日志路径：上传目录同级的 instance/ 下。

    运行时是 backend/instance/wechat-log.txt，测试时落在各自的临时目录里。
    """
    media_dir = Path(current_app.config.get("UPLOAD_FOLDER") or ".")
    target = media_dir.parent / "instance"
    target.mkdir(parents=True, exist_ok=True)
    return target / LOG_FILENAME


def mask_id(value):
    """日志里只留标识的头尾，避免把完整 openid / state / token 写进文件。"""
    text = str(value or "")
    if len(text) <= 8:
        return text or "-"
    return f"{text[:6]}***{text[-4:]}"


def log_event(event, **fields):
    """记录微信登录的关键动作：控制台 + 事件日志，出问题时可以回看。"""
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    parts = " ".join(
        f"{key}={value}" for key, value in fields.items() if value not in (None, "")
    )
    line = f"[{stamp}] {event}" + (f" | {parts}" if parts else "")

    try:
        current_app.logger.info("wechat: %s", line)
    except Exception:  # pragma: no cover - 记日志失败不影响登录
        pass

    try:
        with event_log_path().open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError as exc:  # pragma: no cover - 磁盘问题也不该挡住登录
        current_app.logger.warning("wechat 事件日志写入失败：%s", exc)


def config_report():
    """配置自检：不联网，只回答「参数本身配对了吗」。

    返回 problems（需要处理）和 notes（只是提示），给 CLI 和排错用。
    """
    app_id = (current_app.config.get("WECHAT_APP_ID") or "").strip()
    secret = (current_app.config.get("WECHAT_APP_SECRET") or "").strip()
    mode = current_mode()
    mode_name = authorize_mode()
    _, scope = _authorize_base_and_scope() if is_configured() else ("", "")
    redirect_uri = _redirect_uri() if is_configured() else ""

    problems = []
    notes = []

    raw_scope = configured_scope()
    if raw_scope and is_configured() and raw_scope != scope:
        problems.append(
            f"WECHAT_SCOPE={raw_scope} 和当前的 {mode_name} 模式不匹配，"
            f"已自动回落成 {scope}：这种组合微信会报「Scope 参数错误或没有 Scope 权限」。"
        )

    if app_id and not secret:
        problems.append("只配了 WECHAT_APP_ID，没配 WECHAT_APP_SECRET，会被当成演示模式。")
    if secret and not app_id:
        problems.append("只配了 WECHAT_APP_SECRET，没配 WECHAT_APP_ID，会被当成演示模式。")

    if mode == "live":
        parsed = urlsplit(redirect_uri)
        host = (parsed.hostname or "").lower()
        path = parsed.path or ""

        if not host:
            problems.append(
                "回调地址解析不出域名：请显式设置 WECHAT_REDIRECT_URI，"
                "并和微信后台白名单里的域名保持一致。"
            )
        else:
            if parsed.scheme != "https":
                problems.append(f"回调地址用的是 {parsed.scheme or '空'}，建议改成 https。")
            if host in PLACEHOLDER_HOSTS:
                problems.append(
                    "回调地址还是文档里的示例域名，必须换成你自己的穿透 / 公网域名，"
                    "并同步填进微信后台的授权回调域名。"
                )
            if host in {"127.0.0.1", "localhost"} or host.startswith(
                ("192.168.", "10.", "172.16.")
            ):
                problems.append(
                    "回调地址是本机 / 内网地址，微信服务器访问不到，"
                    "需要内网穿透（ngrok 等）或部署到公网。"
                )
        if path and path != "/api/auth/wechat/callback":
            problems.append(
                f"回调路径是 {path}，建议用 /api/auth/wechat/callback，"
                "免得和微信后台白名单对不上。"
            )
    elif mode == "mock":
        notes.append("当前是演示模式：登录页显示「模拟微信扫码登录」，不联网也能跑通流程。")
    else:
        notes.append(
            "微信登录已关闭：既没配 AppID / AppSecret，又把 WECHAT_MOCK_ENABLED 设成了 0。"
        )

    if is_configured() and not (
        current_app.config.get("WECHAT_REDIRECT_URI") or ""
    ).strip():
        notes.append(
            "没有显式设置 WECHAT_REDIRECT_URI：浏览器访问时按当前域名推断"
            "（穿透场景已按 X-Forwarded-Proto 推断成 https）；"
            "仍建议显式设置成 https://你的域名/api/auth/wechat/callback，免得和微信白名单对不上。"
        )

    if mode == "live":
        # 这条报错最常见的原因就是 AppID 类型跟授权地址对不上
        if mode_name == "mp":
            notes.append(
                "mp 模式必须用公众号 / 测试号的 AppID。"
                "如果这个 AppID 来自开放平台网站应用，微信会报「Scope 参数错误或没有 Scope 权限」，"
                "要改成 WECHAT_AUTHORIZE_MODE=open。"
            )
        else:
            notes.append(
                "open 模式必须用开放平台网站应用的 AppID。"
                "如果这个 AppID 是公众号 / 测试号的，微信会报「Scope 参数错误或没有 Scope 权限」，"
                "要改成 WECHAT_AUTHORIZE_MODE=mp。"
            )

    if mode_name == "mp":
        notes.append("mp 是公众号网页授权，页面必须在微信内置浏览器里打开才能完成授权。")

    masked_id = app_id
    if len(app_id) > 10:
        masked_id = f"{app_id[:6]}****{app_id[-4:]}"

    # mp 模式必须在微信里打开，所以自检顺手给出「该发到微信里的那个地址」
    entry_url = ""
    if redirect_uri:
        parsed_redirect = urlsplit(redirect_uri)
        if parsed_redirect.scheme and parsed_redirect.netloc:
            entry_url = (
                f"{parsed_redirect.scheme}://{parsed_redirect.netloc}"
                "/documents/index.html"
            )

    return {
        "mode": mode,
        "app_id": masked_id,
        "app_secret_configured": bool(secret),
        "authorize_mode": mode_name,
        "scope": scope,
        "redirect_uri": redirect_uri,
        "entry_url": entry_url,
        "mock_enabled": mock_enabled(),
        "authorize_url": (
            build_authorize_url("SELF-CHECK-STATE") if is_configured() else ""
        ),
        "problems": problems,
        "notes": notes,
    }


def detect_local_tunnel(timeout=0.8):
    """读本机 ngrok / cpolar 的本地 API，找出当前的 https 公网地址。

    只在这台开发机上有效（这些工具的本地 API 默认 4040）。
    没装或没启动时返回 None，调用方自己决定怎么提示。
    """
    import json
    import urllib.request

    for port in TUNNEL_API_PORTS:
        url = f"http://127.0.0.1:{port}{TUNNEL_API_PATH}"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            continue

        tunnels = payload.get("tunnels") or []
        https_tunnels = [
            item
            for item in tunnels
            if str(item.get("public_url") or "").startswith("https://")
        ]
        if not https_tunnels:
            continue

        # 同一台机器可能开了多个隧道，优先挑转发到本项目端口的那个
        preferred = [
            item
            for item in https_tunnels
            if ":5000" in str((item.get("config") or {}).get("addr") or "")
        ]
        chosen = (preferred or https_tunnels)[0]
        return {
            "source_port": port,
            "public_url": str(chosen["public_url"]).rstrip("/"),
            "addr": str((chosen.get("config") or {}).get("addr") or ""),
            "proto": str(chosen.get("proto") or ""),
        }
    return None


def _redirect_uri():
    configured = (current_app.config.get("WECHAT_REDIRECT_URI") or "").strip()
    if configured:
        return configured
    try:
        # 浏览器里访问时用当前域名兜底；命令行自检没有请求上下文，返回空串
        return url_for("wechat.callback", _external=True)
    except RuntimeError:
        return ""


def new_state(bind_user_id=None):
    """生成签名过的 state：微信 webview 不带 cookie 时也能校验。

    payload 里带绑定账号 id（0 表示普通登录），并附时间戳，默认 10 分钟有效。
    """
    serializer = URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"], salt=STATE_SALT
    )
    return serializer.dumps({"b": int(bind_user_id or 0)})


def read_state(value):
    """校验 state 的签名和时效；通过返回 {bind_user_id}，否则返回 None。"""
    if not value:
        return None
    serializer = URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"], salt=STATE_SALT
    )
    try:
        payload = serializer.loads(
            value,
            max_age=current_app.config.get("WECHAT_STATE_MAX_AGE", 600),
        )
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict):
        return None
    return {"bind_user_id": payload.get("b") or None}


def authorize_mode():
    return (current_app.config.get("WECHAT_AUTHORIZE_MODE") or "open").strip().lower()


def configured_scope():
    return (current_app.config.get("WECHAT_SCOPE") or "").strip()


def _authorize_base_and_scope():
    """按模式返回授权地址和 scope。

    scope 配错时不能硬用（微信会回「Scope 参数错误或没有 Scope 权限」），
    所以这里只接受该模式允许的取值，其它一律回落到该模式的默认 scope。
    """
    mode = authorize_mode()
    scope = configured_scope()
    if mode == "mp":
        return MP_AUTHORIZE_URL, (scope if scope in MP_SCOPES else MP_SCOPE)
    return OPEN_AUTHORIZE_URL, (scope if scope in OPEN_SCOPES else OPEN_SCOPE)


def build_authorize_url(state):
    base, scope = _authorize_base_and_scope()
    params = {
        "appid": current_app.config.get("WECHAT_APP_ID"),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": scope,
        "state": state,
    }
    if base == MP_AUTHORIZE_URL:
        # 公众号网页授权：微信建议带上 connect_redirect=1，
        # 避免 code 失效时在微信客户端里反复跳授权页
        params["connect_redirect"] = "1"
    return f"{base}?{urlencode(params)}#wechat_redirect"


def _wechat_get_json(url, params, timeout):
    """请求微信接口，把网络错误和 errcode 都转成 WeChatAPIError。"""
    try:
        import requests
    except ImportError as exc:  # pragma: no cover - requirements.txt 里已经有 requests
        raise WeChatAPIError("服务端缺少 requests 依赖，无法调用微信接口") from exc

    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # requests 的网络异常和 JSON 解析异常
        raise WeChatAPIError(f"微信接口调用失败：{exc}") from exc

    if isinstance(data, dict) and data.get("errcode"):
        raise WeChatAPIError(
            f"微信接口返回错误 {data.get('errcode')}：{data.get('errmsg')}"
        )
    return data


def fetch_wechat_profile(code):
    """用授权码换 openid 和用户资料。

    先调 access_token 拿 openid，再调 userinfo 拿昵称和头像；
    静默授权（snsapi_base）拿不到资料时只用 openid 登录。
    """
    timeout = current_app.config.get("WECHAT_HTTP_TIMEOUT", 5)

    token = _wechat_get_json(
        ACCESS_TOKEN_URL,
        {
            "appid": current_app.config.get("WECHAT_APP_ID"),
            "secret": current_app.config.get("WECHAT_APP_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout,
    )
    openid = (token.get("openid") or "").strip()
    if not openid:
        raise WeChatAPIError("微信没有返回 openid")

    profile = {
        "openid": openid,
        "unionid": token.get("unionid"),
        "nickname": "",
        "avatar_url": "",
    }

    try:
        info = _wechat_get_json(
            USERINFO_URL,
            {
                "access_token": token.get("access_token"),
                "openid": openid,
                "lang": "zh_CN",
            },
            timeout,
        )
    except WeChatAPIError:
        info = {}

    profile["nickname"] = (info.get("nickname") or "").strip()
    profile["avatar_url"] = info.get("headimgurl") or ""
    if not profile["unionid"]:
        profile["unionid"] = info.get("unionid")
    return profile


def check_credentials():
    """向微信换一次 access_token，验证 AppID / AppSecret 是否配对。

    这一步和登录流程无关，只用来区分「凭据配错了」和「流程/会话问题」。
    返回 ok / reason，失败原因直接给用户看。
    """
    if not is_configured():
        return {"ok": False, "reason": "没有配置 WECHAT_APP_ID / WECHAT_APP_SECRET"}

    try:
        data = _wechat_get_json(
            CREDENTIAL_URL,
            {
                "grant_type": "client_credential",
                "appid": current_app.config.get("WECHAT_APP_ID"),
                "secret": current_app.config.get("WECHAT_APP_SECRET"),
            },
            current_app.config.get("WECHAT_HTTP_TIMEOUT", 5),
        )
    except WeChatAPIError as exc:
        return {"ok": False, "reason": str(exc)}

    token = str(data.get("access_token") or "")
    return {
        "ok": bool(token),
        "token": mask_id(token),
        "expires_in": data.get("expires_in"),
    }


def _wechat_username(openid):
    """微信建号时用工号 wx_ + openid 摘要，不暴露原始 openid。"""
    digest = hashlib.sha256(openid.encode("utf-8")).hexdigest()[:10]
    base = f"wx_{digest}"
    candidate = base
    index = 1
    while User.query.filter_by(username=candidate).first() is not None:
        index += 1
        candidate = f"{base}_{index}"
    return candidate


def _default_role():
    role = (current_app.config.get("WECHAT_DEFAULT_ROLE") or "teacher").strip()
    return role if role in USER_ROLES else "teacher"


def login_or_create_user(profile, bind_user=None):
    """按 openid 找账号：找不到就新建，或者绑定到 bind_user。

    返回 (user, error_code)，失败时 user 为 None。
    """
    openid = (profile.get("openid") or "").strip()
    if not openid:
        return None, "wechat_missing_openid"

    user = User.query.filter_by(wechat_openid=openid).first()
    nickname = (profile.get("nickname") or "").strip()

    if user is not None:
        # 这个微信已经绑过账号：本人可以继续登录，别人不能顶掉
        if bind_user is not None and user.id != bind_user.id:
            return None, "wechat_already_bound"
    elif bind_user is not None:
        if bind_user.wechat_openid and bind_user.wechat_openid != openid:
            return None, "account_already_bound"
        user = bind_user
    else:
        user = User(
            username=_wechat_username(openid),
            name=nickname or DEFAULT_MOCK_NICKNAME,
            role=_default_role(),
        )
        # 微信登录的账号没有密码，password_hash 留空表示只能用微信登录
        user.password_hash = None
        db.session.add(user)

    user.wechat_openid = openid
    if profile.get("unionid"):
        user.wechat_unionid = profile["unionid"]
    if profile.get("avatar_url"):
        user.avatar_url = profile["avatar_url"]
    if nickname and not user.password_hash:
        # 微信自动建的号昵称跟着微信走；绑定到已有工号时不动原来的姓名
        user.name = nickname

    db.session.commit()
    return user, None


def _validate_mock_openid(openid):
    if not 4 <= len(openid) <= 64:
        return "模拟 openid 长度需要在 4 到 64 个字符之间"
    if not all(char.isalnum() or char in "_-" for char in openid):
        return "模拟 openid 只能包含字母、数字、下划线和短横线"
    return None


def _result_redirect(status, message="", error_code=""):
    target = (
        current_app.config.get("WECHAT_RESULT_REDIRECT")
        or "/documents/wechat-callback.html"
    )
    separator = "&" if "?" in target else "?"
    url = f"{target}{separator}wechat={status}"
    if message:
        url += f"&message={quote(message)}"
    if status == "error" and error_code:
        url += f"&error={quote(error_code)}"
    return url


def _finish(user, message="", error_code="wechat_login_failed", status=400):
    """回调收尾：浏览器跳到结果页，带 ?format=json 时直接返回 JSON。"""
    if request.args.get("format") == "json":
        if user is None:
            return api_error(message or "微信登录失败", error_code, status)
        return api_success(user.to_dict())
    return redirect(
        _result_redirect(
            "success" if user is not None else "error",
            message,
            error_code,
        )
    )


@bp.get("/config")
def wechat_config():
    """给前端用的配置：当前是真实模式、演示模式还是没开启。"""
    mode = current_mode()
    hint = {
        "live": "使用微信扫描二维码登录",
        "mock": "演示模式：未配置 WECHAT_APP_ID / WECHAT_APP_SECRET，使用本地模拟微信登录",
        "disabled": "微信登录未开启",
    }[mode]
    return api_success(
        {
            "mode": mode,
            "configured": is_configured(),
            "app_id": current_app.config.get("WECHAT_APP_ID") or "",
            "authorize_mode": (
                current_app.config.get("WECHAT_AUTHORIZE_MODE") or "open"
            ).strip().lower(),
            # 联调时最容易出错的是回调地址和微信后台白名单不一致，
            # 所以直接把后端实际使用的地址返回给前端/自检脚本
            "redirect_uri": _redirect_uri() if is_configured() else "",
            "hint": hint,
            "mock": {
                "enabled": mock_enabled(),
                "openid": (
                    current_app.config.get("WECHAT_MOCK_OPENID")
                    or DEFAULT_MOCK_OPENID
                ),
                "nickname": (
                    current_app.config.get("WECHAT_MOCK_NICKNAME")
                    or DEFAULT_MOCK_NICKNAME
                ),
            },
        }
    )


@bp.get("/authorize-url")
def authorize_url():
    """生成带 state 的微信授权地址，state 存在 session 里防 CSRF。"""
    if not is_configured():
        log_event("authorize-url-rejected", mode=current_mode(), host=request.host)
        return api_error(
            "微信登录未配置，当前是演示模式，请使用模拟登录",
            "wechat_not_configured",
            400,
        )

    bind_user_id = (
        current_user.id
        if request.args.get("bind") == "1" and current_user.is_authenticated
        else None
    )
    state = new_state(bind_user_id)
    session[STATE_SESSION_KEY] = state

    # 已登录用户带 ?bind=1 扫码时，回调里做绑定而不是切换登录身份
    if bind_user_id:
        session[BIND_SESSION_KEY] = bind_user_id
    else:
        session.pop(BIND_SESSION_KEY, None)

    log_event(
        "authorize-url",
        mode=current_mode(),
        authorize_mode=authorize_mode(),
        scope=_authorize_base_and_scope()[1],
        host=request.host,
        redirect_uri=_redirect_uri(),
        state=mask_id(state),
        bind=BIND_SESSION_KEY in session,
        cookies=bool(request.cookies),
    )

    return api_success(
        {
            "authorize_url": build_authorize_url(state),
            "state": state,
            "redirect_uri": _redirect_uri(),
            "bind": BIND_SESSION_KEY in session,
        }
    )


@bp.get("/callback")
def callback():
    """微信授权回调：校验 state、换 openid、登录或绑定。"""
    if not is_configured():
        log_event("callback-rejected", reason="not-configured", host=request.host)
        return _finish(None, "微信登录未配置，当前是演示模式", "wechat_not_configured")

    code = (request.args.get("code") or "").strip()
    state = (request.args.get("state") or "").strip()
    expected_state = session.pop(STATE_SESSION_KEY, None)
    bind_user_id = session.pop(BIND_SESSION_KEY, None)

    # 两条校验路径：session 里的 state（一次性、最严格）；
    # 微信内置浏览器不带 cookie 时，退回「签名 + 时效」校验
    token_state = read_state(state)
    require_session = bool(current_app.config.get("WECHAT_STATE_REQUIRE_SESSION"))
    state_source = ""
    if expected_state and state == expected_state:
        state_source = "session"
    elif token_state is not None and not require_session:
        state_source = "signature"
        bind_user_id = bind_user_id or token_state["bind_user_id"]

    log_event(
        "callback",
        host=request.host,
        code=mask_id(code),
        state=mask_id(state),
        session_state=mask_id(expected_state),
        state_source=state_source or "-",
        bind_user=bind_user_id,
        args=",".join(sorted(request.args.keys())),
    )

    if not code:
        # 用户在微信页面上点了「取消」
        log_event("callback-cancelled", host=request.host)
        return _finish(None, "已取消微信登录", "wechat_cancelled")
    if not state_source:
        log_event(
            "callback-state-mismatch",
            host=request.host,
            signature_ok=token_state is not None,
            require_session=require_session,
            hint="签名校验没过（伪造/过期），或开了 WECHAT_STATE_REQUIRE_SESSION 但浏览器没带回 cookie",
        )
        return _finish(None, "微信登录校验失败，请重新扫码", "wechat_invalid_state")
    if state_source == "signature":
        log_event(
            "callback-state-from-signature",
            host=request.host,
            note="浏览器没带回 session cookie，按签名校验通过（可用 WECHAT_STATE_REQUIRE_SESSION=1 强制要求 cookie）",
        )

    try:
        profile = fetch_wechat_profile(code)
    except WeChatAPIError as exc:
        log_event("callback-wechat-api-error", host=request.host, error=str(exc))
        return _finish(None, str(exc), "wechat_api_error", 502)

    log_event(
        "callback-profile",
        openid=mask_id(profile.get("openid")),
        nickname=profile.get("nickname") or "-",
        unionid=bool(profile.get("unionid")),
    )

    bind_user = db.session.get(User, bind_user_id) if bind_user_id else None
    user, error_code = login_or_create_user(profile, bind_user=bind_user)
    if user is None:
        log_event(
            "callback-bind-conflict",
            host=request.host,
            error=error_code or "wechat_login_failed",
        )
        return _finish(
            None,
            BIND_ERROR_MESSAGES.get(error_code, "微信登录失败"),
            error_code or "wechat_login_failed",
            409,
        )

    if bind_user is None:
        login_user(user)
    log_event(
        "callback-login",
        user_id=user.id,
        username=user.username,
        role=user.role,
        action="bind" if bind_user is not None else "login",
    )
    return _finish(user)


@bp.post("/mock-login")
def mock_login():
    """演示模式下的模拟微信登录，真实模式恒返回 403。"""
    if not mock_enabled():
        return api_error("当前未开启微信登录演示模式", "wechat_mock_disabled", 403)

    payload = request.get_json(silent=True) or {}
    openid = (payload.get("openid") or "").strip() or (
        current_app.config.get("WECHAT_MOCK_OPENID") or DEFAULT_MOCK_OPENID
    )
    nickname = (payload.get("nickname") or "").strip() or (
        current_app.config.get("WECHAT_MOCK_NICKNAME") or DEFAULT_MOCK_NICKNAME
    )

    invalid = _validate_mock_openid(openid)
    if invalid:
        return api_error(invalid, "invalid_openid", 400)

    user, error_code = login_or_create_user(
        {
            "openid": openid,
            "nickname": nickname,
            "avatar_url": payload.get("avatar_url") or "",
        }
    )
    if user is None:
        log_event("mock-login-failed", openid=mask_id(openid), error=error_code)
        return api_error("模拟微信登录失败", error_code or "wechat_login_failed", 400)

    login_user(user)
    log_event(
        "mock-login",
        openid=mask_id(openid),
        user_id=user.id,
        username=user.username,
    )
    return api_success(user.to_dict())


@bp.post("/bind")
@login_required
def bind():
    """把微信绑定到当前登录账号，不会切换登录身份。"""
    payload = request.get_json(silent=True) or {}
    bind_user = db.session.get(User, current_user.id)

    if is_configured():
        code = (payload.get("code") or "").strip()
        state = (payload.get("state") or "").strip()
        expected_state = session.pop(STATE_SESSION_KEY, None)
        if not code:
            return api_error("缺少微信授权码", "wechat_missing_code", 400)
        if not expected_state or state != expected_state:
            return api_error(
                "微信授权校验失败，请重新扫码", "wechat_invalid_state", 400
            )
        try:
            profile = fetch_wechat_profile(code)
        except WeChatAPIError as exc:
            return api_error(str(exc), "wechat_api_error", 502)
    elif mock_enabled():
        openid = (payload.get("openid") or "").strip() or (
            current_app.config.get("WECHAT_MOCK_OPENID") or DEFAULT_MOCK_OPENID
        )
        invalid = _validate_mock_openid(openid)
        if invalid:
            return api_error(invalid, "invalid_openid", 400)
        profile = {
            "openid": openid,
            "nickname": (payload.get("nickname") or "").strip(),
        }
    else:
        return api_error("微信登录未开启", "wechat_not_configured", 400)

    user, error_code = login_or_create_user(profile, bind_user=bind_user)
    if user is None:
        log_event("bind-conflict", user_id=bind_user.id, error=error_code)
        return api_error(
            BIND_ERROR_MESSAGES.get(error_code, "微信绑定失败"),
            error_code or "wechat_bind_failed",
            409,
        )
    log_event("bind", user_id=user.id, username=user.username)
    return api_success(user.to_dict())


@bp.post("/unbind")
@login_required
def unbind():
    """解绑微信；微信建号且没有密码的账号不允许解绑，避免把自己锁在门外。"""
    user = db.session.get(User, current_user.id)
    if not user.wechat_bound:
        return api_error("当前账号还没有绑定微信", "wechat_not_bound", 409)
    if not user.password_login_enabled:
        return api_error(
            "该账号由微信创建，解绑后将无法登录，已拒绝操作",
            "wechat_unbind_not_allowed",
            409,
        )

    user.wechat_openid = None
    user.wechat_unionid = None
    user.avatar_url = None
    db.session.commit()
    log_event("unbind", user_id=user.id, username=user.username)
    return "", 204
