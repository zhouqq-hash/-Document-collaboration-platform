"""微信登录测试：演示模式（mock）和真实模式（live）两条链路都要覆盖。"""

import json

from app import wechat

from conftest import login


def live_app(app_factory):
    """构造一个配好微信参数的测试应用（不会真的请求微信）。"""
    return app_factory(
        WECHAT_APP_ID="wx_test_appid",
        WECHAT_APP_SECRET="test_secret",
        WECHAT_REDIRECT_URI="http://127.0.0.1:5000/api/auth/wechat/callback",
    )


def placeholder_app(app_factory):
    """模拟「照抄文档示例地址」的状态：回调域名还是 abcd-1234.ngrok-free.app。"""
    return app_factory(
        WECHAT_APP_ID="wxd1be913f06f14888",
        WECHAT_APP_SECRET="test_secret",
        WECHAT_AUTHORIZE_MODE="mp",
        WECHAT_REDIRECT_URI="https://abcd-1234.ngrok-free.app/api/auth/wechat/callback",
    )


def mock_wechat_profile(code, openid="openid_from_wechat", nickname="张老师"):
    return {
        "openid": openid,
        "unionid": "unionid_from_wechat",
        "nickname": nickname,
        "avatar_url": "https://example.com/avatar.png",
    }


class FakeResponse:
    """假的 requests 响应，用来在没有外网的情况下验证真实 HTTP 代码路径。"""

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeTunnelResponse:
    """假的隧道本地 API 响应。"""

    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_wechat_http(calls, token_payload, userinfo_payload):
    def fake_get(url, params=None, timeout=None):
        calls.append((url, params or {}))
        if url == wechat.ACCESS_TOKEN_URL:
            return FakeResponse(token_payload)
        if url == wechat.USERINFO_URL:
            return FakeResponse(userinfo_payload)
        raise AssertionError(f"没有预期的微信接口调用：{url}")

    return fake_get


# ---------- 配置与模式 ----------


def test_wechat_config_reports_mock_mode(wechat_client):
    response = wechat_client.get("/api/auth/wechat/config")
    data = response.get_json()["data"]
    assert response.status_code == 200
    assert data["mode"] == "mock"
    assert data["configured"] is False
    assert data["mock"]["enabled"] is True


def test_wechat_config_reports_live_mode(app_factory):
    client = live_app(app_factory).test_client()
    data = client.get("/api/auth/wechat/config").get_json()["data"]
    assert data["mode"] == "live"
    assert data["configured"] is True
    assert data["app_id"] == "wx_test_appid"
    assert data["redirect_uri"] == "http://127.0.0.1:5000/api/auth/wechat/callback"
    assert data["mock"]["enabled"] is False


def test_forwarded_https_scheme_is_used_for_callback_url(app_factory):
    """穿透进来的请求带 X-Forwarded-Proto: https 时，回调地址必须是 https。"""
    app = app_factory(
        WECHAT_APP_ID="wx_tunnel_appid",
        WECHAT_APP_SECRET="test_secret",
        WECHAT_AUTHORIZE_MODE="mp",
    )
    client = app.test_client()
    headers = {
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "demo-9527.trycloudflare.com",
    }

    data = client.get("/api/auth/wechat/config", headers=headers).get_json()["data"]
    assert (
        data["redirect_uri"]
        == "https://demo-9527.trycloudflare.com/api/auth/wechat/callback"
    )

    url = client.get("/api/auth/wechat/authorize-url", headers=headers).get_json()[
        "data"
    ]["authorize_url"]
    assert (
        "redirect_uri=https%3A%2F%2Fdemo-9527.trycloudflare.com"
        "%2Fapi%2Fauth%2Fwechat%2Fcallback" in url
    )


def test_plain_request_falls_back_to_http(app_factory):
    """没有代理头时按请求本身推断（本机直连就是 http）。"""
    app = app_factory(
        WECHAT_APP_ID="wx_plain_appid",
        WECHAT_APP_SECRET="test_secret",
    )
    client = app.test_client()
    data = client.get("/api/auth/wechat/config").get_json()["data"]
    assert data["redirect_uri"].startswith("http://localhost/")


def test_wechat_can_be_turned_off(app_factory):
    app = app_factory(WECHAT_MOCK_ENABLED=False)
    client = app.test_client()
    data = client.get("/api/auth/wechat/config").get_json()["data"]
    assert data["mode"] == "disabled"

    response = client.post("/api/auth/wechat/mock-login", json={})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "wechat_mock_disabled"


def test_authorize_url_is_rejected_in_mock_mode(wechat_client):
    response = wechat_client.get("/api/auth/wechat/authorize-url")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "wechat_not_configured"


# ---------- 真实模式的授权地址 ----------


def test_authorize_url_contains_appid_and_state(app_factory):
    client = live_app(app_factory).test_client()
    response = client.get("/api/auth/wechat/authorize-url")
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["authorize_url"].startswith(
        "https://open.weixin.qq.com/connect/qrconnect?"
    )
    assert "appid=wx_test_appid" in data["authorize_url"]
    assert "scope=snsapi_login" in data["authorize_url"]
    assert f"state={data['state']}" in data["authorize_url"]

    with client.session_transaction() as session:
        assert session["wechat_oauth_state"] == data["state"]


def test_authorize_url_uses_mp_mode_when_configured(app_factory):
    app = app_factory(
        WECHAT_APP_ID="wx_mp_appid",
        WECHAT_APP_SECRET="test_secret",
        WECHAT_AUTHORIZE_MODE="mp",
    )
    client = app.test_client()
    data = client.get("/api/auth/wechat/authorize-url").get_json()["data"]
    assert data["authorize_url"].startswith(
        "https://open.weixin.qq.com/connect/oauth2/authorize?"
    )
    assert "scope=snsapi_userinfo" in data["authorize_url"]
    # 公众号网页授权建议带 connect_redirect=1，避免在微信里反复跳授权页
    assert "connect_redirect=1" in data["authorize_url"]


def test_open_mode_falls_back_when_scope_belongs_to_mp(app_factory):
    """公众号的 scope 配到扫码模式上，微信会报「Scope 参数错误或没有 Scope 权限」。"""
    app = app_factory(
        WECHAT_APP_ID="wx_open_appid",
        WECHAT_APP_SECRET="test_secret",
        WECHAT_AUTHORIZE_MODE="open",
        WECHAT_SCOPE="snsapi_userinfo",
    )
    client = app.test_client()
    url = client.get("/api/auth/wechat/authorize-url").get_json()["data"]["authorize_url"]
    assert "scope=snsapi_login" in url
    assert "scope=snsapi_userinfo" not in url

    with app.app_context():
        report = wechat.config_report()
    assert any("不匹配" in problem for problem in report["problems"])
    assert any("Scope 参数错误" in note for note in report["notes"])


def test_mp_mode_keeps_silent_scope(app_factory):
    """公众号静默授权 snsapi_base 是合法组合，要原样保留。"""
    app = app_factory(
        WECHAT_APP_ID="wx_mp_appid",
        WECHAT_APP_SECRET="test_secret",
        WECHAT_AUTHORIZE_MODE="mp",
        WECHAT_SCOPE="snsapi_base",
        WECHAT_REDIRECT_URI="https://demo-9527.ngrok-free.app/api/auth/wechat/callback",
    )
    client = app.test_client()
    url = client.get("/api/auth/wechat/authorize-url").get_json()["data"]["authorize_url"]
    assert "scope=snsapi_base" in url

    with app.app_context():
        report = wechat.config_report()
    assert report["scope"] == "snsapi_base"
    assert report["problems"] == []


def test_config_report_mentions_appid_type_mismatch(app_factory):
    app = app_factory(
        WECHAT_APP_ID="wxd1be913f06f14888",
        WECHAT_APP_SECRET="test_secret",
        WECHAT_AUTHORIZE_MODE="open",
        WECHAT_REDIRECT_URI="https://demo-9527.ngrok-free.app/api/auth/wechat/callback",
    )
    with app.app_context():
        report = wechat.config_report()
    assert report["problems"] == []
    assert any("开放平台网站应用" in note for note in report["notes"])
    assert any("WECHAT_AUTHORIZE_MODE=mp" in note for note in report["notes"])


# ---------- 授权回调 ----------


def test_callback_rejects_invalid_state(app_factory):
    client = live_app(app_factory).test_client()
    client.get("/api/auth/wechat/authorize-url")

    response = client.get(
        "/api/auth/wechat/callback?code=code123&state=forged&format=json"
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "wechat_invalid_state"


def test_callback_handles_cancelled_authorize(app_factory):
    client = live_app(app_factory).test_client()
    response = client.get("/api/auth/wechat/callback?format=json")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "wechat_cancelled"


def test_callback_creates_user_and_logs_in(app_factory, monkeypatch):
    app = live_app(app_factory)
    client = app.test_client()
    monkeypatch.setattr(wechat, "fetch_wechat_profile", mock_wechat_profile)

    state = client.get("/api/auth/wechat/authorize-url").get_json()["data"]["state"]
    response = client.get(
        f"/api/auth/wechat/callback?code=code123&state={state}&format=json"
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["name"] == "张老师"
    assert data["username"].startswith("wx_")
    assert data["wechat_bound"] is True
    assert data["password_login"] is False
    assert data["role"] == "teacher"
    assert data["avatar_url"] == "https://example.com/avatar.png"

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["data"]["id"] == data["id"]


def test_callback_reuses_user_for_same_openid(app_factory, monkeypatch):
    app = live_app(app_factory)
    client = app.test_client()
    monkeypatch.setattr(wechat, "fetch_wechat_profile", mock_wechat_profile)

    first_state = client.get("/api/auth/wechat/authorize-url").get_json()["data"]["state"]
    first = client.get(
        f"/api/auth/wechat/callback?code=code1&state={first_state}&format=json"
    ).get_json()["data"]
    client.post("/api/auth/logout")

    second_state = client.get("/api/auth/wechat/authorize-url").get_json()["data"]["state"]
    second = client.get(
        f"/api/auth/wechat/callback?code=code2&state={second_state}&format=json"
    ).get_json()["data"]

    assert first["id"] == second["id"]
    assert first["username"] == second["username"]


def test_callback_redirects_browser_to_result_page(app_factory, monkeypatch):
    client = live_app(app_factory).test_client()
    monkeypatch.setattr(wechat, "fetch_wechat_profile", mock_wechat_profile)

    state = client.get("/api/auth/wechat/authorize-url").get_json()["data"]["state"]
    response = client.get(f"/api/auth/wechat/callback?code=code123&state={state}")

    assert response.status_code == 302
    assert "/documents/wechat-callback.html?wechat=success" in response.headers["Location"]


def test_callback_reports_wechat_api_error(app_factory, monkeypatch):
    client = live_app(app_factory).test_client()

    def boom(code):
        raise wechat.WeChatAPIError("微信接口调用失败：连接超时")

    monkeypatch.setattr(wechat, "fetch_wechat_profile", boom)

    state = client.get("/api/auth/wechat/authorize-url").get_json()["data"]["state"]
    response = client.get(
        f"/api/auth/wechat/callback?code=code123&state={state}&format=json"
    )

    assert response.status_code == 502
    assert response.get_json()["error"]["code"] == "wechat_api_error"


def test_callback_state_cannot_be_reused_when_session_required(app_factory, monkeypatch):
    """开了强制 cookie 校验后，同一个 state 不能用第二次。"""
    app = app_factory(
        WECHAT_APP_ID="wx_test_appid",
        WECHAT_APP_SECRET="test_secret",
        WECHAT_REDIRECT_URI="http://127.0.0.1:5000/api/auth/wechat/callback",
        WECHAT_STATE_REQUIRE_SESSION=True,
    )
    client = app.test_client()
    monkeypatch.setattr(wechat, "fetch_wechat_profile", mock_wechat_profile)

    state = client.get("/api/auth/wechat/authorize-url").get_json()["data"]["state"]
    first = client.get(
        f"/api/auth/wechat/callback?code=code1&state={state}&format=json"
    )
    assert first.status_code == 200

    replay = client.get(
        f"/api/auth/wechat/callback?code=code2&state={state}&format=json"
    )
    assert replay.status_code == 400
    assert replay.get_json()["error"]["code"] == "wechat_invalid_state"


def test_callback_accepts_signed_state_without_cookies(app_factory, monkeypatch):
    """微信 webview 不回传 cookie 时（日志里 cookies=False），签名 state 也要能登录。"""
    app = live_app(app_factory)
    monkeypatch.setattr(wechat, "fetch_wechat_profile", mock_wechat_profile)

    state = app.test_client().get("/api/auth/wechat/authorize-url").get_json()["data"][
        "state"
    ]
    fresh_client = app.test_client()
    response = fresh_client.get(
        f"/api/auth/wechat/callback?code=code1&state={state}&format=json"
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["wechat_bound"] is True


def test_callback_rejects_signed_state_when_session_required(app_factory, monkeypatch):
    app = app_factory(
        WECHAT_APP_ID="wx_test_appid",
        WECHAT_APP_SECRET="test_secret",
        WECHAT_REDIRECT_URI="http://127.0.0.1:5000/api/auth/wechat/callback",
        WECHAT_STATE_REQUIRE_SESSION=True,
    )
    monkeypatch.setattr(wechat, "fetch_wechat_profile", mock_wechat_profile)

    state = app.test_client().get("/api/auth/wechat/authorize-url").get_json()["data"][
        "state"
    ]
    response = app.test_client().get(
        f"/api/auth/wechat/callback?code=code1&state={state}&format=json"
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "wechat_invalid_state"


def test_callback_rejects_tampered_state(app_factory, monkeypatch):
    app = live_app(app_factory)
    monkeypatch.setattr(wechat, "fetch_wechat_profile", mock_wechat_profile)

    state = app.test_client().get("/api/auth/wechat/authorize-url").get_json()["data"][
        "state"
    ]
    response = app.test_client().get(
        f"/api/auth/wechat/callback?code=code1&state={state}x&format=json"
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "wechat_invalid_state"


def test_bind_state_carries_account_without_cookies(app_factory, monkeypatch):
    """?bind=1 时账号 id 存在签名 state 里，cookie 丢了也能绑到原账号。"""
    app = live_app(app_factory)
    monkeypatch.setattr(
        wechat,
        "fetch_wechat_profile",
        lambda code: mock_wechat_profile(
            code, openid="openid_bind", nickname="绑定用户"
        ),
    )

    signed_in = app.test_client()
    login(signed_in, "teacher", "teacher123")
    state = signed_in.get("/api/auth/wechat/authorize-url?bind=1").get_json()["data"][
        "state"
    ]

    fresh_client = app.test_client()
    response = fresh_client.get(
        f"/api/auth/wechat/callback?code=code1&state={state}&format=json"
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["username"] == "teacher"
    assert data["wechat_bound"] is True


# ---------- 配置自检 ----------


def test_config_report_accepts_public_domain(app_factory):
    app = app_factory(
        WECHAT_APP_ID="wxd1be913f06f14888",
        WECHAT_APP_SECRET="test_secret",
        WECHAT_AUTHORIZE_MODE="mp",
        WECHAT_REDIRECT_URI="https://demo-9527.ngrok-free.app/api/auth/wechat/callback",
    )
    with app.app_context():
        report = wechat.config_report()

    assert report["mode"] == "live"
    assert report["app_id"] == "wxd1be****4888"
    assert report["authorize_mode"] == "mp"
    assert report["scope"] == "snsapi_userinfo"
    assert (
        report["entry_url"]
        == "https://demo-9527.ngrok-free.app/documents/index.html"
    )
    assert report["problems"] == []
    assert any("微信内置浏览器" in note for note in report["notes"])


def test_config_report_flags_document_placeholder(app_factory):
    app = placeholder_app(app_factory)
    with app.app_context():
        report = wechat.config_report()
    assert any("示例域名" in problem for problem in report["problems"])


def test_config_report_flags_local_and_insecure_callback(app_factory):
    app = app_factory(
        WECHAT_APP_ID="wx_local_appid",
        WECHAT_APP_SECRET="test_secret",
        WECHAT_REDIRECT_URI="http://127.0.0.1:5000/api/auth/wechat/callback",
    )
    with app.app_context():
        report = wechat.config_report()
    joined = " ".join(report["problems"])
    assert "https" in joined
    assert "内网" in joined


def test_config_report_flags_partial_credentials(app_factory):
    app = app_factory(WECHAT_APP_ID="wx_only_appid")
    with app.app_context():
        report = wechat.config_report()
    assert report["mode"] == "mock"
    assert any("WECHAT_APP_SECRET" in problem for problem in report["problems"])


def test_wechat_check_command_reports_problems(app_factory):
    app = placeholder_app(app_factory)
    result = app.test_cli_runner().invoke(args=["wechat-check"])
    assert result.exit_code == 1
    assert "示例域名" in result.output
    assert "回调地址" in result.output


def test_wechat_check_command_passes_in_mock_mode(app_factory):
    app = app_factory()
    result = app.test_cli_runner().invoke(args=["wechat-check"])
    assert result.exit_code == 0
    assert "演示模式" in result.output
    assert "没有发现配置问题" in result.output


# ---------- 隧道地址检测 ----------


def test_detect_local_tunnel_prefers_project_port(monkeypatch):
    payload = {
        "tunnels": [
            {
                "public_url": "https://other.ngrok-free.app",
                "proto": "https",
                "config": {"addr": "http://localhost:8080"},
            },
            {
                "public_url": "https://demo.ngrok-free.app",
                "proto": "https",
                "config": {"addr": "http://localhost:5000"},
            },
        ]
    }
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda url, timeout=None: FakeTunnelResponse(payload)
    )

    tunnel = wechat.detect_local_tunnel()
    assert tunnel["public_url"] == "https://demo.ngrok-free.app"
    assert tunnel["addr"] == "http://localhost:5000"
    assert tunnel["source_port"] == 4040


def test_detect_local_tunnel_returns_none_without_api(monkeypatch):
    def refuse(url, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", refuse)
    assert wechat.detect_local_tunnel() is None


def test_wechat_tunnel_command_prints_what_to_fill(app_factory, monkeypatch):
    app = app_factory()
    monkeypatch.setattr(
        wechat,
        "detect_local_tunnel",
        lambda timeout=0.8: {
            "public_url": "https://demo-9527.ngrok-free.app",
            "addr": "http://localhost:5000",
            "proto": "https",
            "source_port": 4040,
        },
    )

    result = app.test_cli_runner().invoke(args=["wechat-tunnel"])
    assert result.exit_code == 0
    assert "https://demo-9527.ngrok-free.app/api/auth/wechat/callback" in result.output
    assert "demo-9527.ngrok-free.app" in result.output
    assert "/documents/index.html" in result.output


def test_wechat_tunnel_command_warns_when_env_differs(app_factory, monkeypatch):
    app = app_factory(WECHAT_REDIRECT_URI="https://abcd-1234.ngrok-free.app/api/auth/wechat/callback")
    monkeypatch.setattr(
        wechat,
        "detect_local_tunnel",
        lambda timeout=0.8: {
            "public_url": "https://demo-9527.ngrok-free.app",
            "addr": "http://localhost:5000",
            "proto": "https",
            "source_port": 4040,
        },
    )

    result = app.test_cli_runner().invoke(args=["wechat-tunnel"])
    assert "[提醒]" in result.output
    assert "abcd-1234.ngrok-free.app" in result.output


def test_wechat_tunnel_command_without_tunnel(app_factory, monkeypatch):
    app = app_factory()
    monkeypatch.setattr(wechat, "detect_local_tunnel", lambda timeout=0.8: None)

    result = app.test_cli_runner().invoke(args=["wechat-tunnel"])
    assert result.exit_code == 1
    assert "cloudflared tunnel --url http://localhost:5000" in result.output
    assert "--url" in result.output


def test_wechat_tunnel_command_accepts_explicit_url(app_factory):
    """cloudflared 这类拿不到本地 API 的隧道，直接把地址粘进来。"""
    app = app_factory()
    result = app.test_cli_runner().invoke(
        args=["wechat-tunnel", "--url", "https://trial-abc.trycloudflare.com/"]
    )
    assert result.exit_code == 0
    assert (
        "https://trial-abc.trycloudflare.com/api/auth/wechat/callback" in result.output
    )
    assert "trial-abc.trycloudflare.com" in result.output
    assert "https://trial-abc.trycloudflare.com/documents/index.html" in result.output


def test_wechat_tunnel_accepts_bare_domain_and_warns_on_http(app_factory):
    app = app_factory()
    bare = app.test_cli_runner().invoke(
        args=["wechat-tunnel", "--url", "trial-abc.trycloudflare.com"]
    )
    assert "https://trial-abc.trycloudflare.com/api/auth/wechat/callback" in bare.output

    insecure = app.test_cli_runner().invoke(
        args=["wechat-tunnel", "--url", "http://trial-abc.trycloudflare.com"]
    )
    assert "[提醒]" in insecure.output


# ---------- 事件日志与凭据自检 ----------


def read_wechat_log(app):
    with app.app_context():
        path = wechat.event_log_path()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def test_mock_login_writes_event_log(wechat_client):
    wechat_client.post(
        "/api/auth/wechat/mock-login",
        json={"openid": "mock_openid_logcheck", "nickname": "日志用户"},
    )
    content = read_wechat_log(wechat_client.application)
    assert "mock-login" in content
    # openid 只留头尾，避免日志里出现完整标识
    assert "mock_openid_logcheck" not in content


def test_callback_error_logs_and_carries_error_code(app_factory, monkeypatch):
    app = live_app(app_factory)
    client = app.test_client()

    def boom(code):
        raise wechat.WeChatAPIError("微信接口返回错误 40029：invalid code")

    monkeypatch.setattr(wechat, "fetch_wechat_profile", boom)
    state = client.get("/api/auth/wechat/authorize-url").get_json()["data"]["state"]
    response = client.get(f"/api/auth/wechat/callback?code=c1&state={state}")

    assert response.status_code == 302
    location = response.headers["Location"]
    assert "wechat=error" in location
    assert "error=wechat_api_error" in location

    content = read_wechat_log(app)
    assert "callback-wechat-api-error" in content
    assert "40029" in content


def test_callback_state_mismatch_logs_hint(app_factory):
    app = live_app(app_factory)
    client = app.test_client()
    client.get("/api/auth/wechat/authorize-url")
    client.get("/api/auth/wechat/callback?code=c1&state=forged")

    content = read_wechat_log(app)
    assert "callback" in content
    assert "callback-state-mismatch" in content


def test_wechat_log_command_prints_events(app_factory):
    app = app_factory()
    app.test_client().post(
        "/api/auth/wechat/mock-login", json={"openid": "mock_openid_clilog"}
    )
    result = app.test_cli_runner().invoke(args=["wechat-log"])
    assert result.exit_code == 0
    assert "mock-login" in result.output


def test_wechat_log_command_without_events(app_factory):
    app = app_factory()
    result = app.test_cli_runner().invoke(args=["wechat-log"])
    assert result.exit_code == 1
    assert "还没有事件日志" in result.output


def test_check_credentials_reports_success(app_factory, monkeypatch):
    app = live_app(app_factory)
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params or {}))
        return FakeResponse({"access_token": "abcdefghijklmnop", "expires_in": 7200})

    monkeypatch.setattr("requests.get", fake_get)
    with app.app_context():
        result = wechat.check_credentials()

    assert result["ok"] is True
    assert result["expires_in"] == 7200
    assert result["token"] == "abcdef***mnop"
    assert calls[0][0] == wechat.CREDENTIAL_URL
    assert calls[0][1]["grant_type"] == "client_credential"
    assert calls[0][1]["appid"] == "wx_test_appid"


def test_check_credentials_reports_wechat_error(app_factory, monkeypatch):
    app = live_app(app_factory)
    monkeypatch.setattr(
        "requests.get",
        lambda url, params=None, timeout=None: FakeResponse(
            {"errcode": 40001, "errmsg": "invalid credential"}
        ),
    )
    with app.app_context():
        result = wechat.check_credentials()

    assert result["ok"] is False
    assert "40001" in result["reason"]


def test_check_credentials_without_config(app_factory):
    app = app_factory()
    with app.app_context():
        result = wechat.check_credentials()
    assert result["ok"] is False
    assert "没有配置" in result["reason"]


def test_wechat_token_test_command(app_factory, monkeypatch):
    app = live_app(app_factory)
    monkeypatch.setattr(
        wechat,
        "check_credentials",
        lambda: {"ok": True, "token": "abcdef***mnop", "expires_in": 7200},
    )
    result = app.test_cli_runner().invoke(args=["wechat-token-test"])
    assert result.exit_code == 0
    assert "凭据正常" in result.output


def test_wechat_token_test_command_in_mock_mode(app_factory):
    app = app_factory()
    result = app.test_cli_runner().invoke(args=["wechat-token-test"])
    assert result.exit_code == 1
    assert "不用测凭据" in result.output


# ---------- 真实 HTTP 代码路径（测试号 / 生产环境走的就是这条） ----------


def test_callback_calls_wechat_http_api(app_factory, monkeypatch):
    client = live_app(app_factory).test_client()
    calls = []
    monkeypatch.setattr(
        "requests.get",
        fake_wechat_http(
            calls,
            {"access_token": "token_1", "openid": "openid_real", "unionid": "union_real"},
            {
                "openid": "openid_real",
                "nickname": "真机测试用户",
                "headimgurl": "https://wx.example.com/avatar.png",
                "unionid": "union_real",
            },
        ),
    )

    state = client.get("/api/auth/wechat/authorize-url").get_json()["data"]["state"]
    response = client.get(
        f"/api/auth/wechat/callback?code=real_code&state={state}&format=json"
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["name"] == "真机测试用户"
    assert data["avatar_url"] == "https://wx.example.com/avatar.png"
    assert data["username"].startswith("wx_")

    token_params = calls[0][1]
    assert calls[0][0] == wechat.ACCESS_TOKEN_URL
    assert token_params["appid"] == "wx_test_appid"
    assert token_params["secret"] == "test_secret"
    assert token_params["code"] == "real_code"
    assert token_params["grant_type"] == "authorization_code"

    userinfo_params = calls[1][1]
    assert calls[1][0] == wechat.USERINFO_URL
    assert userinfo_params["access_token"] == "token_1"
    assert userinfo_params["openid"] == "openid_real"


def test_callback_surfaces_wechat_errcode(app_factory, monkeypatch):
    client = live_app(app_factory).test_client()
    calls = []
    monkeypatch.setattr(
        "requests.get",
        fake_wechat_http(
            calls,
            {"errcode": 40029, "errmsg": "invalid code"},
            {},
        ),
    )

    state = client.get("/api/auth/wechat/authorize-url").get_json()["data"]["state"]
    response = client.get(
        f"/api/auth/wechat/callback?code=bad_code&state={state}&format=json"
    )

    assert response.status_code == 502
    error = response.get_json()["error"]
    assert error["code"] == "wechat_api_error"
    assert "40029" in error["message"]


def test_callback_without_userinfo_still_logs_in(app_factory, monkeypatch):
    """静默授权或用户未关注时拿不到昵称头像，只用 openid 也要能登录。"""
    client = live_app(app_factory).test_client()
    calls = []
    monkeypatch.setattr(
        "requests.get",
        fake_wechat_http(
            calls,
            {"access_token": "token_2", "openid": "openid_silent"},
            {"errcode": 48001, "errmsg": "api unauthorized"},
        ),
    )

    state = client.get("/api/auth/wechat/authorize-url").get_json()["data"]["state"]
    response = client.get(
        f"/api/auth/wechat/callback?code=silent_code&state={state}&format=json"
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["wechat_bound"] is True
    assert data["avatar_url"] == ""
    assert len(calls) == 2


# ---------- 模拟登录 ----------


def test_mock_login_creates_wechat_only_account(wechat_client):
    response = wechat_client.post(
        "/api/auth/wechat/mock-login",
        json={"openid": "mock_openid_visitor", "nickname": "微信访客"},
    )
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["name"] == "微信访客"
    assert data["username"].startswith("wx_")
    assert data["wechat_bound"] is True
    assert data["password_login"] is False
    assert wechat_client.get("/api/auth/me").get_json()["data"]["id"] == data["id"]


def test_mock_login_reuses_user_for_same_openid(wechat_client):
    first = wechat_client.post(
        "/api/auth/wechat/mock-login", json={"openid": "mock_openid_repeat"}
    ).get_json()["data"]
    wechat_client.post("/api/auth/logout")
    second = wechat_client.post(
        "/api/auth/wechat/mock-login", json={"openid": "mock_openid_repeat"}
    ).get_json()["data"]

    assert first["id"] == second["id"]


def test_mock_login_uses_default_identity(wechat_client):
    data = wechat_client.post("/api/auth/wechat/mock-login", json={}).get_json()["data"]
    assert data["name"] == "微信演示用户"


def test_mock_login_rejects_bad_openid(wechat_client):
    response = wechat_client.post(
        "/api/auth/wechat/mock-login", json={"openid": "bad openid!"}
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_openid"


def test_wechat_only_account_cannot_use_password_login(wechat_client):
    data = wechat_client.post(
        "/api/auth/wechat/mock-login", json={"openid": "mock_openid_nopass"}
    ).get_json()["data"]
    wechat_client.post("/api/auth/logout")

    response = login(wechat_client, data["username"], "whatever")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "invalid_credentials"


# ---------- 绑定与解绑 ----------


def test_bind_requires_login(wechat_client):
    response = wechat_client.post(
        "/api/auth/wechat/bind", json={"openid": "mock_openid_teacher"}
    )
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthorized"


def test_mock_bind_links_wechat_to_current_account(wechat_client):
    login(wechat_client, "teacher", "teacher123")
    response = wechat_client.post(
        "/api/auth/wechat/bind", json={"openid": "mock_openid_teacher"}
    )
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["username"] == "teacher"
    assert data["name"] == "胡军成"
    assert data["wechat_bound"] is True
    assert data["password_login"] is True

    # 绑定之后，同一个微信可以直接登录到 teacher
    wechat_client.post("/api/auth/logout")
    again = wechat_client.post(
        "/api/auth/wechat/mock-login", json={"openid": "mock_openid_teacher"}
    ).get_json()["data"]
    assert again["username"] == "teacher"


def test_one_wechat_cannot_bind_two_accounts(wechat_client):
    login(wechat_client, "teacher", "teacher123")
    wechat_client.post(
        "/api/auth/wechat/bind", json={"openid": "mock_openid_shared"}
    )
    wechat_client.post("/api/auth/logout")

    login(wechat_client, "other", "other123")
    response = wechat_client.post(
        "/api/auth/wechat/bind", json={"openid": "mock_openid_shared"}
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "wechat_already_bound"


def test_account_cannot_bind_second_wechat(wechat_client):
    login(wechat_client, "teacher", "teacher123")
    wechat_client.post("/api/auth/wechat/bind", json={"openid": "mock_openid_first"})

    response = wechat_client.post(
        "/api/auth/wechat/bind", json={"openid": "mock_openid_second"}
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "account_already_bound"


def test_unbind_removes_wechat_binding(wechat_client):
    login(wechat_client, "teacher", "teacher123")
    wechat_client.post("/api/auth/wechat/bind", json={"openid": "mock_openid_unbind"})

    response = wechat_client.post("/api/auth/wechat/unbind")
    assert response.status_code == 204

    me = wechat_client.get("/api/auth/me").get_json()["data"]
    assert me["wechat_bound"] is False
    assert me["username"] == "teacher"


def test_wechat_created_account_cannot_unbind(wechat_client):
    wechat_client.post(
        "/api/auth/wechat/mock-login", json={"openid": "mock_openid_only"}
    )
    response = wechat_client.post("/api/auth/wechat/unbind")
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "wechat_unbind_not_allowed"


def test_unbind_without_binding_returns_409(wechat_client):
    login(wechat_client, "teacher", "teacher123")
    response = wechat_client.post("/api/auth/wechat/unbind")
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "wechat_not_bound"
