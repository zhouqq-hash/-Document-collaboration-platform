# 微信登录认证流程

这份文档只讲一件事：从用户点「微信扫码登录」到系统里出现登录态，中间到底发生了什么。
配置怎么填、报错怎么查见 `docs/wechat-login-guide.md`，接口字段见 `docs/api-spec.md`。

## 0. 先澄清两个容易混的词

| 说法 | 含义 | 属于 |
| --- | --- | --- |
| **微信登录 / 微信授权**（本模块实现的） | 用户用微信身份证明「我是谁」，系统据此建立登录态。走 OAuth2 授权码模式 | 开发工作，代码在 `backend/app/wechat.py` |
| **微信认证**（严格意义的） | 公众号 / 小程序 / 开放平台账号的**主体认证**（企业资质审核，通常 300 元/年）。认证过后才解锁高级接口 | 平台侧审核流程，不是代码 |

两者关系：要先有通过**认证**的开放平台网站应用（或已认证服务号），才拿到 `AppID` / `AppSecret`，然后才能跑下面的**登录授权**流程。
本项目把这一步做成可配置：没拿到 `AppID` 时自动进入演示模式，流程和代码路径完全一致，只是「向微信要身份」那一步换成了本地模拟。

## 1. 参与方与模式

流程里一共四个角色：

| 角色 | 职责 |
| --- | --- |
| 浏览器（登录页 / 账号设置页） | 发起授权、弹出二维码窗口、轮询登录结果 |
| 本项目后端（`backend/app/wechat.py`） | 存 `state`、换 `openid`、建号 / 登录 / 绑定、返回登录态 |
| 微信服务器（`open.weixin.qq.com`、`api.weixin.qq.com`） | 展示二维码、发一次性 `code`、用 `code` 换 `openid` |
| 用户手机上的微信 | 扫码并确认授权 |

| 模式 | 触发条件 | 「向微信要身份」这一步 |
| --- | --- | --- |
| `live` | 配好 `WECHAT_APP_ID` + `WECHAT_APP_SECRET` | 真实请求微信接口 |
| `mock` | 没配应用信息（默认） | 前端直接提交一个模拟 openid，等价于「微信已经告诉我们是这个人」 |

## 2. 总体时序（真实模式 / 首次登录）

```text
浏览器                        本项目后端                     微信服务器              用户手机
  |                              |                              |                    |
  | 1 GET /api/auth/wechat/config|                              |                    |
  |----------------------------->| 返回 mode=live               |                    |
  |<-----------------------------|                              |                    |
  |                              |                              |                    |
  | 2 GET /api/auth/wechat/authorize-url                         |                    |
  |----------------------------->| 生成 state 存 session        |                    |
  |<-----------------------------| 返回 authorize_url           |                    |
  |                              |                              |                    |
  | 3 新窗口打开 authorize_url                                   |                    |
  |------------------------------------------------------------------------------->|
  |                              |                              |  二维码页面         |
  |                              |                              |<-------------------|
  |                              |                              |  扫码 + 确认        |
  |                              |                              |                    |
  | 4 微信回调 GET /api/auth/wechat/callback?code=CODE&state=STATE                    |
  |------------------------------------------------------------------------------->|
  |                              | 5 校验 state（存过且只此一次）  |                    |
  |                              | 6 GET sns/oauth2/access_token |                    |
  |                              |----------------------------->|                    |
  |                              |   { openid, access_token, unionid }               |
  |                              |<-----------------------------|                    |
  |                              | 7 GET sns/userinfo            |                    |
  |                              |----------------------------->|                    |
  |                              |   { nickname, headimgurl }    |                    |
  |                              |<-----------------------------|                    |
  |                              | 8 按 openid 找账号 → 建号 / 登录 / 绑定            |
  |                              | 9 login_user(user) 写入会话    |                    |
  |<-------------------------------------------------------------------------------|
  | 302 /documents/wechat-callback.html?wechat=success           |                    |
  |                              |                              |                    |
  | 10 结果页 postMessage 通知原窗口并自动关闭                    |                    |
  | 11 原窗口轮询 GET /api/auth/me 拿到 200 → 进入分类列表         |                    |
```

## 3. 分步说明

### 步骤 1：前端问后端「现在是什么模式」

```http
GET /api/auth/wechat/config
```

```json
{ "data": { "mode": "live", "configured": true, "app_id": "wx0123...", "authorize_mode": "open", "mock": { "enabled": false } } }
```

前端据此决定显示哪个按钮：`live` 显示「微信扫码登录」、`mock` 显示「模拟微信扫码登录」、`disabled` 显示未开启。

### 步骤 2：后端生成带 `state` 的授权地址

```http
GET /api/auth/wechat/authorize-url
```

后端做三件事：

1. `state = secrets.token_urlsafe(16)`，存进 session（键 `wechat_oauth_state`）。
2. 拼授权地址：`https://open.weixin.qq.com/connect/qrconnect?appid=...&redirect_uri=...&response_type=code&scope=snsapi_login&state=...#wechat_redirect`。
3. 如果当前已登录且带 `?bind=1`，顺手把当前用户 id 写进 session（键 `wechat_bind_user_id`），表示「这次扫码是绑定，不是换人」。

```json
{ "data": { "authorize_url": "https://open.weixin.qq.com/connect/qrconnect?appid=...", "state": "Kq3...", "redirect_uri": "https://doc.example.edu.cn/api/auth/wechat/callback", "bind": false } }
```

### 步骤 3：浏览器弹二维码

前端 `window.open(authorize_url, "wechatAuthorize", "width=520,height=640,...")`。二维码是微信服务器渲染的，本项目不自己画二维码，也不接触用户密码。
弹窗被浏览器拦截时，退回「当前窗口直接跳转」，后续由结果页自己收尾。

### 步骤 4：微信回调，带回一次性 `code`

```http
GET /api/auth/wechat/callback?code=CODE&state=STATE
```

- 用户点了「取消」→ 微信不会带 `code`，后端跳结果页并提示「已取消微信登录」。
- `code` 是一次性的、几分钟内有效，只能换一次身份，泄漏了也只能换到一个 openid。

### 步骤 5：校验 `state`

`state` 是**签名令牌**（`itsdangerous` 签名，密钥用 `SECRET_KEY`，默认 10 分钟有效），同时也在 session 里存一份，回调时两条路径都能过：

```python
expected_state = session.pop("wechat_oauth_state", None)   # 一次性，取出即失效
token_state = read_state(state)                            # 验签 + 校验时效

if expected_state and state == expected_state:
    state_source = "session"        # 最严格：必须是同一个浏览器会话，而且只能用一次
elif token_state and not WECHAT_STATE_REQUIRE_SESSION:
    state_source = "signature"      # 兜底：微信 webview 没带回 cookie 时按签名放行
else:
    return 校验失败
```

为什么两套并存：session 那条能防 CSRF（攻击者把自己的授权链接骗你点，state 对不上你的会话）；但微信内置浏览器在部分机型上不带回 cookie（事件日志里能看到 `cookies=False`），只认 session 就会直接「登录失败」。所以默认允许签名兜底，并在日志里写明这次走的是 `state_source=session` 还是 `state_source=signature`；要最严格可以设 `WECHAT_STATE_REQUIRE_SESSION=1`，此时必须带回 cookie 才认。

绑定流程（`?bind=1`）要绑的账号 id 也放在签名 state 里，所以 cookie 丢了也能绑到原来的工号上。

### 步骤 6~7：用 `code` 换 openid 和资料

```http
GET https://api.weixin.qq.com/sns/oauth2/access_token?appid=&secret=&code=&grant_type=authorization_code
→ { "access_token", "openid", "unionid", "scope" }

GET https://api.weixin.qq.com/sns/userinfo?access_token=&openid=&lang=zh_CN
→ { "openid", "nickname", "headimgurl", "unionid" }
```

- 两个请求都由**后端**发起，`AppSecret` 不出服务端。
- 第二步失败不影响登录（`snsapi_base` 静默授权拿不到昵称头像），只用 openid 建立身份。
- 微信返回 `errcode` 或网络异常 → 转成 502 `wechat_api_error`，前端直接显示原因。

### 步骤 8：按 openid 决定「登录 / 建号 / 绑定」

```text
按 wechat_openid 查用户
├─ 查到，且就是当前会话本人（或没走绑定流程）→ 直接登录
├─ 查到，但属于别的账号，而本次是绑定流程 → 409 该微信已绑定其他账号
├─ 没查到
│   ├─ 本次是绑定流程（session 里有 bind_user_id）
│   │     └─ 当前账号已有别的微信 → 409；否则把 openid 写到当前账号
│   └─ 普通扫码登录 → 新建账号：工号 wx_<openid摘要>、无密码、角色取 WECHAT_DEFAULT_ROLE
└─ 微信带了昵称且账号没有密码 → 用微信昵称刷新姓名（已有工号的账号不改名）
```

### 步骤 9：写入登录态

只有**普通扫码登录**和**模拟登录**会调 `login_user(user)`；绑定流程刻意不切换登录身份，用户仍然是自己，只是多了一个登录方式。

### 步骤 10~11：结果回传与页面收敛

```text
回调 → 302 /documents/wechat-callback.html?wechat=success
        （失败时带 ?wechat=error&message=中文原因）
结果页 → window.opener.postMessage({ type: "wechat-login", status, message }, 同源)
        → 自己 window.close()（由脚本打开的窗口才关得掉）
原窗口 → 每 2 秒 GET /api/auth/me，最多 60 次（约 2 分钟）
        ├─ 拿到 200 → 进入 categories.html
        └─ 超时 → 提示「没有等到微信授权结果，请重试」
```

如果结果是当前窗口（弹窗被拦截的情况），结果页自己 `location.replace("categories.html")`，失败则停在提示页并提供「返回登录」。

## 4. 三条业务分支的区别

| 分支 | 触发方式 | 结果 | 权限 |
| --- | --- | --- | --- |
| 首次扫码登录 | 登录页 → 微信入口 | 新建 `wx_` 账号，无密码 | 默认 `teacher`，看不到别人负责的文档的上传入口 |
| 再次扫码登录 | 同一微信再扫 | 命中已有 openid，登录同一账号 | 与既有账号完全一致 |
| 绑定已有工号 | 登录后 → 账号设置 → 绑定微信（`?bind=1`） | 原工号账号多一个 openid，姓名和角色不变 | 原账号权限、负责的文档全部不变 |

解绑走 `POST /api/auth/wechat/unbind`：有密码的账号可解绑；微信自动创建、没有密码的账号禁止解绑，避免解绑后彻底进不来。

## 5. 演示模式下流程怎么简化

```text
登录页 → GET /api/auth/wechat/config → mode=mock
      → 点「模拟微信扫码登录」
      → POST /api/auth/wechat/mock-login { openid, nickname }
      → 后端走同一个 login_or_create_user() 分支：建号 / 复用 / 登录
      → 前端直接跳 categories.html（不用弹窗、不用轮询）
```

也就是说：**演示模式只省掉了第 2~7 步的「向微信要身份」，第 8 步之后的业务逻辑、数据库操作和会话处理完全一样**，测试因此可以覆盖两条链路。

## 6. 安全约定小结

| 风险 | 处理 |
| --- | --- |
| CSRF / 伪造回调 | `state` 是签名令牌（防伪造、防过期），同时在 session 里存一份做一次性校验；cookie 丢失时退回签名校验，可用 `WECHAT_STATE_REQUIRE_SESSION=1` 强制要求 cookie |
| `code` 被重复使用 | `code` 一次性，微信侧也会拦截；后端只认第一次成功的交换 |
| AppSecret 泄漏 | 只存在服务端配置/环境变量，接口和前端都不返回 |
| openid 被拿来当身份伪造 | 只有服务端（`fetch_wechat_profile`）能产出 openid；`mock-login` 在配好真实应用信息后返回 403 |
| 顶号 | 一个 openid 只能绑一个账号；绑定他人已绑的微信返回 409 |
| 解绑自锁 | 无密码账号禁止解绑 |
| openid 直接当工号暴露 | 工号取 `wx_` + openid 的 SHA-256 摘要前 10 位 |

## 7. 失败分支与用户看到的话

| 场景 | 后端返回 | 页面提示 |
| --- | --- | --- |
| 没配 AppID 却走了真实授权地址 | 400 `wechat_not_configured` | 微信登录未配置，当前是演示模式，请使用模拟登录 |
| 用户在微信里点取消 | 302 结果页 `wechat=error`，`wechat_cancelled` | 已取消微信登录 |
| `state` 不匹配 / 已用过 | 400 `wechat_invalid_state` | 微信登录校验失败，请重新扫码 |
| 微信接口报错（code 失效、AppSecret 错） | 502 `wechat_api_error` | 微信接口返回错误 40029：invalid code |
| 该微信已绑到别的账号 | 409 `wechat_already_bound` | 该微信已经绑定了其他账号，请先在原账号解绑 |
| 当前账号已绑过别的微信 | 409 `account_already_bound` | 当前账号已经绑定过其他微信，请先解绑 |
| 无密码账号解绑 | 409 `wechat_unbind_not_allowed` | 该账号由微信创建，解绑后将无法登录，已拒绝操作 |
| 真实模式下调模拟登录 | 403 `wechat_mock_disabled` | 当前未开启微信登录演示模式 |
| 微信直接拒绝授权页：**Scope 参数错误或没有 Scope 权限** | 微信原样返回错误页，请求还没回到本项目 | 发生在第 3 步。原因是 AppID 类型和 scope 不匹配：公众号 / 测试号要用 `mp` + `snsapi_base`/`snsapi_userinfo`，开放平台网站应用要用 `open` + `snsapi_login`。后端只接受该模式允许的 scope，配错会回落到默认值并在 `wechat-check` 里报出来 |
| 事件日志里**没有 `callback` 行** | 没有任何请求到达 `/api/auth/wechat/callback` | 失败发生在第 3~4 步之间：`redirect_uri` 与微信后台白名单不一致、协议生成成了 `http://`（穿透场景必须是 https），或者用户没在微信里完成授权。对比日志里 `authorize-url` 那行的 `redirect_uri` 即可确认 |

## 8. 和官方文档的对应关系

| 官方概念 | 本项目对应 |
| --- | --- |
| 微信开放平台 · 网站应用微信登录（扫码） | `WECHAT_AUTHORIZE_MODE=open`，默认 |
| 微信公众平台 · 网页授权（微信内打开） | `WECHAT_AUTHORIZE_MODE=mp`，scope 默认 `snsapi_userinfo` |
| `snsapi_base` 静默授权 | 配 `WECHAT_SCOPE=snsapi_base`，此时只有 openid，昵称头像为空 |
| `access_token` / `userinfo` 接口 | `fetch_wechat_profile()` 里的两个请求 |
| 授权回调域名 | `WECHAT_REDIRECT_URI`，需与微信后台配置一致 |

## 9. 相关代码与文档

| 内容 | 位置 |
| --- | --- |
| 后端流程实现 | `backend/app/wechat.py` |
| 前端登录入口与轮询 | `prototype/documents/app.js`（`initWechatLogin` / `startWechatPolling` / `initWechatCallback`） |
| 绑定与解绑页面 | `prototype/documents/account.html` + `initAccount` / `renderWechatBinding` |
| 回跳中转页 | `prototype/documents/wechat-callback.html` |
| 配置与排错 | `docs/wechat-login-guide.md` |
| 配置、命令、排错、真机联调步骤 | `docs/wechat-login-guide.md` |
| 接口字段 | `docs/api-spec.md` 的「微信登录接口」一节 |
| 自动化测试 | `backend/tests/test_wechat.py`（25 个用例） |
