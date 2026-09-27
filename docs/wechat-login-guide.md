# 微信登录接入说明

一句话：登录页支持微信登录，**默认演示模式零配置可用**；接真实微信（测试号或正式应用）的步骤在下面，**真机联调目前暂停**，先按演示模式交付。

## 0. 当前状态（2026-09-27）

| 部分 | 状态 | 说明 |
| --- | --- | --- |
| 演示模式（`mock`） | ✅ 已完成 | 登录页「模拟微信扫码登录」，不联网也能跑通建号 / 复用 / 绑定 / 解绑；有自动化测试 |
| 真实模式代码（`live`） | ✅ 已完成，接口层已测 | 授权地址、回调、换 openid、建号 / 登录 / 绑定、解绑、事件日志、凭据自检都在；微信接口用假 `requests` 覆盖 |
| 真机联调（测试号） | ⏸ 暂停 | 遇到过「回调地址生成成 http」「scope 与 AppID 类型不匹配」「微信 webview 不带 cookie」三类问题，代码侧都已修，但**还没有一次完整的真机成功记录**，先不做 |
| 正式上线 | ⛔ 需要条件 | 企业 / 组织主体 + 微信认证 300 元/年起 + 备案域名，见第 2 节 |

真机联调想恢复的话，直接跳到第 6 节按清单走。

## 1. 名词与三种模式

先分清两个容易混的词：

| 说法 | 含义 | 属于 |
| --- | --- | --- |
| **微信登录 / 微信授权**（本项目实现的） | 用户用微信身份证明「我是谁」，系统据此建立登录态，走 OAuth2 授权码模式 | 开发工作，代码在 `backend/app/wechat.py` |
| **微信认证**（严格意义的） | 公众号 / 小程序 / 开放平台账号的主体资质审核（一般 300 元/年） | 平台侧审核，不是代码；它是拿到 AppID 的前置条件 |

微信登录的运行模式由配置决定，不用改代码：

| 模式 | 触发条件 | 用户体验 | 是否联网 |
| --- | --- | --- | --- |
| `live` 真实模式 | 配了 `WECHAT_APP_ID` + `WECHAT_APP_SECRET` | 微信扫码或微信内网页授权，openid 来自微信 | 是 |
| `mock` 演示模式（默认） | 没配应用信息，且没关掉演示开关 | 点「模拟微信扫码登录」直接登录，可手填 openid / 昵称 | 否 |
| `disabled` 未开启 | 设了 `WECHAT_MOCK_ENABLED=0` 且没配应用信息 | 登录页显示「微信登录未开启」 | 否 |

## 2. 三条路，成本先看清楚

| 路径 | 成本 | 前提 | 局限 |
| --- | --- | --- | --- |
| 演示模式（当前交付形态） | 0 元 | 无 | openid 是本地模拟的，不是真微信身份 |
| 公众平台接口测试号 | 0 元 | 个人微信扫码即得 | 只能在微信内置浏览器完成授权；不能上线；没有 PC 扫码 |
| 正式公众号 / 开放平台网站应用 | 认证 300 元/年起 | 企业 / 组织主体、对公验证、备案域名 | 有审核周期；认证费按主体账号收，同账号下多个应用共享 |

结论：课程演示和答辩用演示模式就够；被要求「真机走一次」时用免费测试号；正式上线才谈认证和备案。

## 3. 配置项

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WECHAT_APP_ID` | 空 | 微信应用 AppID，配了它才会进真实模式 |
| `WECHAT_APP_SECRET` | 空 | AppSecret，只放服务端，不要下发前端、不要提交仓库 |
| `WECHAT_REDIRECT_URI` | 空（按当前域名推断） | 授权回调地址，建议显式写成 `https://你的域名/api/auth/wechat/callback` |
| `WECHAT_AUTHORIZE_MODE` | `open` | `open` 开放平台网站应用扫码 / `mp` 公众号网页授权（测试号用 `mp`） |
| `WECHAT_SCOPE` | 按模式自动 | `mp` 只接受 `snsapi_base` / `snsapi_userinfo`，`open` 只接受 `snsapi_login`，配错会回落 |
| `WECHAT_DEFAULT_ROLE` | `teacher` | 微信新建账号的角色，只接受 `teacher` / `admin` |
| `WECHAT_RESULT_REDIRECT` | `/documents/wechat-callback.html` | 授权结束后浏览器跳转的结果页 |
| `WECHAT_MOCK_ENABLED` | `1` | 演示模式开关，配了 AppID 时自动失效 |
| `WECHAT_MOCK_OPENID` / `WECHAT_MOCK_NICKNAME` | `mock_openid_demo` / `微信演示用户` | 演示模式的默认身份 |
| `WECHAT_HTTP_TIMEOUT` | `5` | 请求微信接口的超时秒数 |
| `WECHAT_STATE_MAX_AGE` | `600` | state 签名令牌的有效期（秒） |
| `WECHAT_STATE_REQUIRE_SESSION` | `0` | 设为 `1` 时强制要求浏览器带回 session cookie（最严格，正式环境建议开） |
| `TRUST_PROXY_HEADERS` | `1` | 采纳穿透 / Nginx 的 `X-Forwarded-Proto`，否则回调地址会被生成成 `http://` |
| `DOC_COLLAB_HOST` / `DOC_COLLAB_PORT` | `127.0.0.1` / `5000` | 后端监听地址，手机走局域网时需要 `0.0.0.0` |

## 4. 命令手册

| 命令 | 作用 |
| --- | --- |
| `flask wechat-check` | 配置自检（不联网）：模式、AppID（打码）、授权方式、实际回调地址、该在微信里打开的地址；把示例域名 / 内网地址 / 非 https / 半套凭据 / scope 不匹配列成 `[问题]`，有问题退出码 1 |
| `flask wechat-tunnel` | 读 ngrok / cpolar 的本地 API（4040），算出要填的三处地址；带 `--url https://你的地址` 时直接用给定地址（给 cloudflared 这类没有本地 API 的隧道用） |
| `flask wechat-log --lines 20` | 回看最近的事件日志（每一步一行），排查「登录失败」用 |
| `flask wechat-token-test` | 用配置里的 AppID / AppSecret 向微信换一次 access_token，验证凭据是否配对 |
| `.\tools\wechat-tunnel.ps1` | 一键：起 Cloudflare 快速隧道 + 自动执行上一条命令并打印要填的内容（保持隧道运行，Ctrl+C 关闭） |
| `.\tools\wechat-tunnel.ps1 -Port 5001` | 后端换端口时用 |

只有 `wechat-check` 不联网，其余会请求微信或本地隧道 API。

## 5. 演示模式怎么用（默认，零配置）

1. 启动后端：`.\.venv\Scripts\python.exe backend\run.py`。
2. 打开 `http://127.0.0.1:5000/documents/index.html`。
3. 点「模拟微信扫码登录」→ 进入分类列表，右上角姓名后面多一个「微信」标记。
4. 展开「模拟参数」可以改 openid / 昵称，用于演示「第一次扫码是建号、同一个 openid 再登录还是同一个账号」。
5. 想演示绑定：先用 `teacher / teacher123` 登录 → 右上角「账号设置」→「绑定微信」→ 再退出，用同一个 openid 模拟扫码，登录进去的就是 `teacher`。

演示模式建出来的账号没有密码（`password_login=false`），不能用工号密码登录，也不允许解绑微信；这些行为都有自动化测试覆盖。

## 6. 真机联调（免费测试号 + 隧道）——暂停中

恢复联调时按顺序做，前面几步做完再动微信，能省很多来回。

### 6.1 申请测试号（约 2 分钟，免费）

1. 打开 `https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login`，微信扫码登录，拿到 `appID` / `appsecret`。
2. 页面往下找「体验接口权限表 → 网页服务 → 网页账号 → 网页授权获取用户基本信息 → 修改」，填**授权回调页面域名**：只填域名，不带 `http://`、不带端口和路径。
3. 让参与演示的微信号扫「测试号用户列表」里的二维码加入。

### 6.2 起一条公网隧道

```powershell
# 推荐：免注册的 Cloudflare Tunnel
winget install --id Cloudflare.cloudflared -e     # 只装一次
.\tools\wechat-tunnel.ps1                         # 起隧道并打印要填的内容
```

同类工具还有 ngrok（需要注册 + `ngrok config add-authtoken`，免费额度第一次打开会多一个中间页）、cpolar、花生壳。cloudflared 没有本地查询 API，所以一键脚本会把地址塞给 `wechat-tunnel --url`。

### 6.3 配置并启动后端

```powershell
$env:WECHAT_APP_ID = "测试号的 appID"
$env:WECHAT_APP_SECRET = "测试号的 appsecret"
$env:WECHAT_AUTHORIZE_MODE = "mp"
$env:WECHAT_REDIRECT_URI = "https://你的隧道域名/api/auth/wechat/callback"

.\.venv\Scripts\python.exe -m flask --app backend\run.py db upgrade
.\.venv\Scripts\python.exe -m flask --app backend\run.py wechat-check
.\.venv\Scripts\python.exe backend\run.py
```

`wechat-check` 必须没有 `[问题]`，并确认它打印的「微信里打开」地址就是你隧道的域名。

### 6.4 在微信里走一遍

1. 把 `https://你的隧道域名/documents/index.html` 发到微信「文件传输助手」，在手机上点开（**不要用 `127.0.0.1`，也不要手点授权链接**）。
2. 点「微信登录」→ 微信授权页 → 允许 → 自动回到分类列表。
3. 想看过程：`flask wechat-log --lines 20`，正常顺序是 `authorize-url` → `callback`（`state_source=session` 或 `signature`）→ `callback-profile` → `callback-login`。

### 6.5 恢复联调时的检查清单

- [ ] 测试号白名单里的域名 = `WECHAT_REDIRECT_URI` 里的域名（只比域名，但 http/https、端口、路径最容易踩）
- [ ] `wechat-check` 里「授权方式」是 `mp`（测试号必须 mp，用 `open` 会报「Scope 参数错误或没有 Scope 权限」）
- [ ] 回调地址是 **https**（穿透场景由 `TRUST_PROXY_HEADERS` 自动推断；显式设置 `WECHAT_REDIRECT_URI` 最稳）
- [ ] 全程用同一个隧道域名打开页面和回调（换域名 / 换设备会让 state 对不上）
- [ ] 隧道地址变了，同时改环境变量和白名单两处
- [ ] 别复用旧的授权链接（`code` 一次性、约 5 分钟失效，复用会报 40029 / 40163）
- [ ] AppID 与 AppSecret 是同一个测试号的（混用报 40001，可先用 `wechat-token-test` 验证）
- [ ] 联调期间关掉自动重载，避免保存文件打断回调：`.\.venv\Scripts\python.exe -m flask --app backend\run.py run`
- [ ] 联调完把环境变量清掉，回到演示模式

## 7. 排错对照表

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 登录页没有微信入口 | 配置成 `disabled`（既没配 AppID，又把 `WECHAT_MOCK_ENABLED` 设成 0） | 看 `/api/auth/wechat/config` 的 `mode`，去掉 `WECHAT_MOCK_ENABLED=0` |
| 点按钮报「微信登录未配置，当前是演示模式」 | 走的是真实授权地址接口，但没配 AppID | 配好参数，或直接用演示按钮 |
| 微信显示「Scope 参数错误或没有 Scope 权限」 | scope 与 AppID 类型不匹配：公众号 / 测试号要用 `mp`，开放平台网站应用要用 `open` | 设 `WECHAT_AUTHORIZE_MODE=mp`，再跑 `wechat-check` 确认「授权方式」 |
| 微信显示「请在微信客户端打开链接」 | 把授权地址直接丢进了电脑浏览器，`mp` 只能在微信内置浏览器完成 | 改为在微信里打开页面地址（`wechat-check` 打印的「微信里打开」那一行），再点页面按钮 |
| 微信里提示「登录失败」 | 页面会显示具体原因 + 错误码，后端同时写事件日志 | `flask wechat-log --lines 20` 看 `callback` 那几行；凭据类问题再跑 `wechat-token-test` |
| 日志里只有 `authorize-url`、**没有 `callback`** | 回调请求没到后端：白名单不一致、`redirect_uri` 是 http、或用户没完成授权 | 对照日志里 `redirect_uri` 与隧道 / 白名单是否一致 |
| `callback ... state_source=-` | state 验签失败或过期，或开了 `WECHAT_STATE_REQUIRE_SESSION=1` 但没带回 cookie | 从登录页重新点一次；确认域名一致；必要时把 `WECHAT_STATE_REQUIRE_SESSION` 设回 0 |
| `callback-wechat-api-error ... 40029 / 40163` | `code` 已被使用或过期（刷新过回调地址） | 回登录页重新走 |
| `callback-wechat-api-error ... 40001` | AppSecret 不对，或与 AppID 不是同一账号 | `wechat-token-test` 验证后重新复制 |
| 提示「该账号由微信创建，解绑后将无法登录」 | 纯微信账号不允许解绑（防自锁） | 预期行为；要密码登录就改用「绑定已有工号」 |
| 自检报「回调地址还是文档里的示例域名」 | 照抄了示例 `abcd-1234.ngrok-free.app` | 起隧道后跑 `wechat-tunnel`，按它打印的值填 |
| 自检报「回调地址是本机 / 内网地址」 | 用了 `127.0.0.1` / `192.168.x.x` | 微信访问不到，必须用公网隧道 |
| 微信里第一次打开出现「You are about to visit …」 | ngrok 免费额度的浏览器警告页 | 点「Visit Site」继续；或改用 Cloudflare Tunnel |
| 运行 `.ps1` 报「字符串缺少终止符」 | Windows PowerShell 5.1 按 GBK 解析无 BOM 的 UTF-8 脚本，中文会吃掉结束引号 | `tools\wechat-tunnel.ps1` 已保持纯 ASCII；自己写含中文的脚本请用 `pwsh` 或 UTF-8 with BOM |

## 8. 安全与实现要点

- **state 双路径校验**：`state` 是 `itsdangerous` 签名令牌（默认 600 秒有效），同时在 session 里存一份做一次性校验；微信 webview 没带回 cookie 时退回验签（日志里写 `state_source=`）。要最严格就设 `WECHAT_STATE_REQUIRE_SESSION=1`。
- **AppSecret 只在服务端**：接口和前端都不返回；`fetch_wechat_profile()` 在后端换 openid。
- **微信建号没有密码**：`password_hash` 为空，`check_password()` 直接拒绝；绑定到已有工号后权限和负责的文档不变。
- **一个微信只能绑一个账号**，冲突返回 409；纯微信账号不允许解绑。
- **日志脱敏**：事件日志里 openid / state / token 都只留头尾。

完整时序、三条业务分支、失败分支和与官方文档的对应关系见 `docs/wechat-auth-flow.md`；接口字段见 `docs/api-spec.md` 的「微信登录接口」一节。

## 9. 相关文件

| 内容 | 位置 |
| --- | --- |
| 后端实现 | `backend/app/wechat.py` |
| 配置项 | `backend/app/config.py` |
| 命令 | `backend/app/cli.py`（`wechat-check` / `wechat-tunnel` / `wechat-log` / `wechat-token-test`） |
| 一键隧道脚本 | `tools/wechat-tunnel.ps1` |
| 数据库迁移 | `backend/db_migrations/versions/9b3c1d7e5a20_add_wechat_login_fields.py` |
| 自动化测试 | `backend/tests/test_wechat.py` |
| 前端登录入口 / 账号设置 / 回跳中转页 | `prototype/documents/index.html`、`account.html`、`wechat-callback.html`、`app.js` |
| 事件日志（运行后生成） | `backend/instance/wechat-log.txt` |
