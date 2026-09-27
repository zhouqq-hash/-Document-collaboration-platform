# Flask 文档管理模块笔记

这份笔记只整理本项目 `backend/` 里的 Flask 文档管理模块，用于复习、答辩和交付讲解。
Django 的对照内容单独放在 `docs/django-vs-flask.md` 和 `docs/django-notes.md`，不要混在一起。

一句话结论：这是一个「Flask JSON API + 顺带托管静态原型」的单体后端，用 4 张表把登录（工号密码 + 微信扫码）、分类、文档、版本串成一条完整链路，21 个业务接口，48 个 pytest 用例全绿。

## 1. 三十秒速览

| 项目 | 内容 |
| --- | --- |
| 业务范围 | 文档管理模块：登录（工号密码 / 微信扫码）、分类、文档、历史版本 |
| 技术栈 | Flask 3.1、Flask-SQLAlchemy 3.1、Flask-Migrate 4.1、Flask-Login 0.6、pytest |
| 接口形态 | `/api/**` 返回 JSON；`/` 与 `/<path:filename>` 托管 `prototype/` 静态页面 |
| 数据存储 | SQLite（`backend/instance/doc_collab.db`）+ 本地文件（`backend/media/`） |
| 规模 | 4 张表、21 个业务接口（另加 `/api/health`）、48 个测试用例 |
| 启动入口 | `backend/run.py` → `create_app()` → `app.run(port=5000, debug=True)` |

## 2. 一次上传新版本，请求走了哪些路

以 `POST /api/documents/3/versions`（multipart：`file` + `changelog`）为例，这是整个模块里分支最多的一条链路：

```text
浏览器
  └─ POST /api/documents/3/versions
       ├─ 路由匹配 documents.bp 的 upload_version          app/documents.py
       ├─ @login_required 查会话，未登录 → unauthorized_handler 返回 401 JSON
       ├─ 取文档，取不到 → 404 document_not_found
       ├─ 权限判断：管理员 或 document.owner_id == 当前用户，否则 403
       ├─ _create_version
       │    ├─ 校验文件必填、扩展名在白名单内，否则 ValueError
       │    ├─ _save_file：落到 media/doc_<文档id>_v<版本号>_<毫秒><后缀>
       │    ├─ version_number = 该文档已有版本号的最大值 + 1
       │    ├─ 记录上传人 current_user、原始文件名、变更说明
       │    └─ document.updated_at = 当前时间
       ├─ db.session.commit()，异常则 rollback 并返回 400
       └─ api_success(version.to_dict(), status=201)
```

看懂这条链路，等于看懂了 Blueprint、装饰器认证、两层权限、文件上传、事务和统一响应格式。

## 3. 代码地图

| 文件 | 职责 | 关键点 |
| --- | --- | --- |
| `backend/run.py` | 启动入口 | 只做 `create_app()` 和 `app.run`，配置都在别处 |
| `backend/app/__init__.py` | 应用工厂 | 建目录、绑定扩展、注册蓝图和 CLI、挂静态路由、`/api/health` |
| `backend/app/config.py` | 配置 | `SECRET_KEY`、SQLite 路径、上传目录、50 MB 上限、扩展名白名单、`WECHAT_*` 微信登录配置 |
| `backend/app/models.py` | 数据模型 | `User` / `DocumentCategory` / `Document` / `DocumentVersion` |
| `backend/app/auth.py` | 认证蓝图 | 前缀 `/api/auth`，登录、登出、当前用户 |
| `backend/app/wechat.py` | 微信登录蓝图 | 前缀 `/api/auth/wechat`，授权地址、回调、模拟登录、绑定与解绑 |
| `backend/app/documents.py` | 文档业务蓝图 | 前缀 `/api`，分类、文档、版本、下载 + 4 个辅助函数 |
| `backend/app/utils.py` | 响应封装 | `api_success` / `api_error` 统一成功与失败格式 |
| `backend/app/cli.py` | 自定义命令 | `flask seed` 生成演示账号和样例文档；`flask wechat-check` 自检配置；`flask wechat-tunnel` 读隧道本地 API 算出要填的回调地址；`flask wechat-log` 回看登录事件；`flask wechat-token-test` 验证 AppID / AppSecret |
| `backend/db_migrations/` | 数据库迁移 | Alembic 脚本，6 个版本，可升级可回滚 |
| `backend/tests/` | 自动化测试 | `conftest.py` 造临时库、客户端和 `app_factory`（可覆盖配置），`test_documents.py` 23 个用例 + `test_wechat.py` 25 个用例 |

## 4. 数据模型

```text
document_categories ──category_id──> documents
users               ──owner_id────> documents
documents           ──document_id─> document_versions
users               ──uploader_id─> document_versions
```

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `users` | `username`（唯一索引）、`role` | 角色只有 `admin` / `teacher`，`is_admin` 是属性不是字段 |
| `document_categories` | `name`（唯一）、`sort_order`、`created_at` | `document_count` 由 `len(self.documents)` 现算 |
| `documents` | `title`、`category_id`、`owner_id`、`description`、`status` | `updated_at` 用 `onupdate` 自动刷新；`status` 取值 active / archived / deprecated，默认 active |
| `document_versions` | `version_number`、`filename`、`file_path`、`uploader_id` | `(document_id, version_number)` 唯一约束 `uq_document_version` |

三个容易忽略但重要的细节：

1. **当前版本是算出来的，不是存出来的**：`Document.current_version` 直接取 `versions[0]`，靠的是 relationship 上的 `order_by="DocumentVersion.version_number.desc()"`。改排序就会改当前版本。
2. **删文档会连带删版本**：`versions` 关系上带 `cascade="all, delete-orphan"`。
3. **唯一约束是最后一道防线**：即使应用层算错版本号，数据库也会拦住重复的 `(document_id, version_number)`。

## 5. 关键机制

### 5.1 应用工厂

`create_app(config=None)` 先读 `Config` 类拿默认值，再按需要通过 `from_mapping` 覆盖（测试走这条）；不传配置时还会顺手建好 `instance/` 目录。
扩展对象在模块顶层创建、在工厂里 `init_app`，这样同一份代码可以创建多个互不干扰的应用实例（测试里就是这么用的）。
微信登录就是靠这个覆盖机制测的：同一份代码既能跑「演示模式」，也能跑「真实模式」，见 `backend/tests/test_wechat.py`。

### 5.2 Blueprint 拆分

`auth.bp` 挂在 `/api/auth`，`documents.bp` 挂在 `/api`。每个蓝图只管自己的业务，路由装饰器直接从方法上读出 HTTP 动词（`@bp.get` / `@bp.post`）。

### 5.3 统一响应格式

成功 `{"data": ...}`，失败 `{"error": {"code": ..., "message": ...}}`，由 `api_success` / `api_error` 收口。
好处是前端只需要判断一次结构；`code` 用英文常量（`permission_denied`、`invalid_file`）方便程序判断，`message` 用中文给人看。

### 5.4 Flask-Login 会话

- `user_loader` 从 session 里的用户 id 还原 `User` 对象。
- `@login_required` 保护所有业务接口。
- 关键改动是 `unauthorized_handler`：默认行为是 302 跳登录页，这里改成返回 401 JSON，因为前端是 fetch 调用而不是浏览器跳转。
- 密码用 `werkzeug.security` 的 `generate_password_hash` / `check_password_hash`，数据库里只有哈希。

### 5.5 两层权限

| 层次 | 依据 | 作用范围 |
| --- | --- | --- |
| 角色级 | `users.role`，`current_user.is_admin` | 建分类、建文档 |
| 资源级 | `documents.owner_id == current_user.id` | 上传新版本 |

上传新版本的判断是 `current_user.is_admin or document.owner_id == current_user.id`，即「管理员全放开，负责人只管自己的」。
权限判断写在视图函数里、紧挨着取资源的那几行，而不是抽到装饰器，是因为每个接口的资源类型和规则都不一样。

### 5.6 文件上传与下载

- 上传：先查扩展名白名单（`ALLOWED_EXTENSIONS`，共 8 种：`pdf` / `doc` / `docx` / `xls` / `xlsx` / `ppt` / `pptx` / `txt`），再由 `_save_file` 生成存储名 `doc_<文档id>_v<版本号>_<毫秒时间戳><后缀>`，落盘到 `UPLOAD_FOLDER`。
- 存进数据库的 `file_path` 是生成的名字，`filename` 才是用户上传时的原始文件名，下载时用它当 `download_name`。
- 下载：`send_from_directory(UPLOAD_FOLDER, version.file_path, as_attachment=True, download_name=version.filename)`，并且校验 `version.document_id == document.id`，防止拿别的文档的版本号来下载。
- 体积上限由 `MAX_CONTENT_LENGTH = 50 MB` 控制。

### 5.7 版本号怎么来的

```python
next_number = max((v.version_number for v in document.versions), default=0) + 1
```

首次上传得到 v1，之后 v2、v3 递增。历史版本只读，没有删除或覆盖接口。

### 5.8 迁移与初始化

- 模型改了字段就必须生成迁移并 `db upgrade`，否则查询会报 `no such column`。
- 迁移链：`6c07f889c867`（初始四张表）→ `721e32875e20`（documents 加 description）→ `66107800329f`（documents.created_at 允许为空）→ `df6013297280`（document_categories 加 created_at，documents.created_at 改回非空）→ `7f2a1b9c4d3e`（documents 加 status）→ `9b3c1d7e5a20`（users 加 wechat_openid / wechat_unionid / avatar_url，password_hash 改为可空）。
- `flask seed` 用 `db.create_all()` + 逐条查询，重复执行不会产生重复数据；同时写入样例文件 `sample_program_v1.txt`。

### 5.9 微信登录的两种模式

`WECHAT_APP_ID` / `WECHAT_APP_SECRET` 配了就是「真实模式」，没配就默认进「演示模式」，页面和测试都不用等微信开放平台的审核：

| 模式 | 触发条件 | 登录方式 | 代码路径 |
| --- | --- | --- | --- |
| `live` | 配好 `WECHAT_APP_ID` + `WECHAT_APP_SECRET` | 前端拿 `/api/auth/wechat/authorize-url` 跳微信扫码，微信回调 `/api/auth/wechat/callback` | `fetch_wechat_profile` 真的请求微信 `access_token` + `userinfo` |
| `mock` | 没配应用信息（默认） | 页面上的「模拟微信扫码登录」按钮，直接带 openid 调 `/mock-login` | `login_or_create_user`，不碰网络 |
| `disabled` | 设了 `WECHAT_MOCK_ENABLED=0` 且没配应用信息 | 页面只显示「微信登录未开启」 | `mock_login` 返回 403 |

几个设计点：

1. **state 是签名令牌**：`authorize-url` 用 `itsdangerous` 签一个带时间戳的 state（默认 10 分钟），同时存进 session；回调时优先按 session 比对（一次性、最严格），微信 webview 没带回 cookie 时退回验签（`state_source=signature`），可用 `WECHAT_STATE_REQUIRE_SESSION=1` 强制要求 cookie。日志会写明走的是哪条路径。
2. **微信建号没有密码**：`password_hash` 允许为空，`check_password` 直接返回 `False`，这样微信用户无法用工号密码登录，也不会因为空哈希报 500。
3. **绑定而不是顶号**：扫码后先按 `wechat_openid` 找账号；找不到且当前已登录（`?bind=1`）就绑到当前账号，找不到也没登录就新建 `wx_<openid摘要>` 账号。
4. **不写死回调地址**：`WECHAT_REDIRECT_URI` 没配时用 `url_for(..., _external=True)` 兜底，方便本机调试；上线按微信要求填备案域名。
5. **scope 不允许乱配**：`mp` 模式只接受 `snsapi_base` / `snsapi_userinfo`，`open` 模式只接受 `snsapi_login`，配错会回落到该模式默认值——因为微信在这种组合下只会回一句「Scope 参数错误或没有 Scope 权限」，回落比报错更有用。
6. **配置自检**：`flask wechat-check` 不联网就能检查模式、AppID（打码）、回调地址和 scope 组合，把示例域名、内网地址、非 https、半套凭据、scope 不匹配都列成 `[问题]`，有问题退出码 1。
7. **穿透协议识别**：`create_app` 里挂了 `ProxyFix`（`TRUST_PROXY_HEADERS` 默认开），Cloudflare / ngrok 透传的 `X-Forwarded-Proto: https` 会被采纳，`url_for(..., _external=True)` 才会生成 `https://` 回调地址；否则隧道里生成的是 `http://...`，微信那边直接对不上白名单，日志里只会看到 `authorize-url`、看不到 `callback`。
8. **可诊断性**：登录每一步都写事件日志（`backend/instance/wechat-log.txt`，openid / state / token 打码），`flask wechat-log` 回看、`flask wechat-token-test` 单独验证 AppID / AppSecret，失败现象能直接落到某一行。

配置、命令、排错和真机联调步骤见 `docs/wechat-login-guide.md`；一次扫码的完整时序、三条业务分支（首次登录 / 再次登录 / 绑定已有工号）、失败分支见 `docs/wechat-auth-flow.md`。真机联调目前暂停，原因和恢复清单见 `docs/worklog-2026-09-27.md`。

## 6. 接口与权限矩阵

| 方法 | 路径 | 说明 | 管理员 | 负责人 | 普通教师 |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/auth/login` | 登录 | 公开 | 公开 | 公开 |
| POST | `/api/auth/logout` | 登出，返回 204 | 允许 | 允许 | 允许 |
| GET | `/api/auth/me` | 当前用户 | 允许 | 允许 | 允许 |
| GET | `/api/auth/wechat/config` | 微信登录当前模式（live / mock / disabled） | 公开 | 公开 | 公开 |
| GET | `/api/auth/wechat/authorize-url` | 生成带 state 的微信授权地址，`?bind=1` 表示绑定 | 公开 | 公开 | 公开 |
| GET | `/api/auth/wechat/callback` | 微信授权回调，登录或绑定后跳结果页 | 公开 | 公开 | 公开 |
| POST | `/api/auth/wechat/mock-login` | 演示模式的模拟扫码登录（真实模式 403） | 公开 | 公开 | 公开 |
| POST | `/api/auth/wechat/bind` | 把微信绑定到当前账号 | 允许 | 允许 | 允许 |
| POST | `/api/auth/wechat/unbind` | 解绑微信（仅微信建号且有密码的账号可解绑） | 允许 | 允许 | 允许 |
| GET | `/api/categories` | 分类列表（含文档数） | 允许 | 允许 | 允许 |
| POST | `/api/categories` | 新建分类 | 允许 | 403 | 403 |
| PATCH | `/api/categories/{id}` | 修改分类名称或排序 | 允许 | 403 | 403 |
| DELETE | `/api/categories/{id}` | 删除分类（有文档时 409） | 允许 | 403 | 403 |
| GET | `/api/users` | 用户列表（新建文档选负责人） | 允许 | 403 | 403 |
| GET | `/api/documents?category_id=&status=` | 文档列表，按更新时间倒序，可按分类和状态筛选 | 允许 | 允许 | 允许 |
| POST | `/api/documents` | 建文档并上传首个版本 | 允许 | 403 | 403 |
| GET | `/api/documents/{id}` | 文档详情 | 允许 | 允许 | 允许 |
| PATCH | `/api/documents/{id}` | 修改文档信息、负责人或状态 | 允许 | 403 | 403 |
| GET | `/api/documents/{id}/versions` | 历史版本（倒序） | 允许 | 允许 | 允许 |
| POST | `/api/documents/{id}/versions` | 上传新版本 | 允许 | 仅本人负责 | 403 |
| GET | `/api/documents/{id}/versions/{version_id}/download` | 下载指定版本 | 允许 | 允许 | 允许 |

未登录访问需要登录的业务接口都返回 401 + `unauthorized`；微信登录的 4 个公开接口按上面的说明开放。

## 7. 测试覆盖

`backend/tests/conftest.py` 每个用例都新建临时目录、临时 SQLite 和 `media/`，用完删除，因此测试之间互不影响。
`create_document()` 辅助函数用管理员建一份文档，方便后续围绕它做权限和版本测试。

| # | 用例 | 验证的东西 |
| --- | --- | --- |
| 1 | `test_health` | 健康检查 |
| 2 | `test_unauthorized_returns_401` | 未登录拦截，且返回 JSON 而不是重定向 |
| 3 | `test_login_and_me` | 登录 + 会话保持 |
| 4 | `test_teacher_can_list_categories` | 分类排序和 `created_at` 字段 |
| 5 | `test_create_document_and_version_increment` | v1 → v2 递增、description 落库、当前版本刷新 |
| 6 | `test_teacher_cannot_upload_if_not_owner` | 资源级越权 403 |
| 7 | `test_owner_can_upload_new_version` | 负责人本人可以上传 |
| 8 | `test_download_version` | 文件内容原样返回 |
| 9 | `test_teacher_cannot_create_category` | 角色级越权 403 |
| 10 | `test_admin_can_create_category` | 管理员建分类 201 |
| 11 | `test_admin_can_list_users` | 管理员获取用户列表，且不泄露密码哈希 |
| 12 | `test_teacher_cannot_list_users` | 普通教师调用户列表 403 |
| 13 | `test_admin_can_update_document` | 管理员改标题、负责人和说明 |
| 14 | `test_teacher_cannot_update_document` | 普通教师改文档 403 |
| 15 | `test_update_document_rejects_missing_category` | 改到不存在分类返回 404 |
| 16 | `test_document_has_default_active_status` | 新建文档默认状态为 active |
| 17 | `test_admin_can_change_document_status` | 管理员改状态，并按状态筛选列表 |
| 18 | `test_update_document_rejects_invalid_status` | 非法状态返回 400 |
| 19 | `test_admin_can_update_category` | 管理员改分类名称和排序 |
| 20 | `test_teacher_cannot_update_category` | 普通教师改分类 403 |
| 21 | `test_admin_can_delete_empty_category` | 管理员删除无文档的分类 |
| 22 | `test_teacher_cannot_delete_category` | 普通教师删分类 403 |
| 23 | `test_delete_category_with_documents_rejected` | 有文档的分类不能删除，返回 409 |

微信登录单独放一个文件 `backend/tests/test_wechat.py`，25 个用例按四组覆盖：

| 分组 | 用例数 | 覆盖的东西 |
| --- | --- | --- |
| 模式与配置 | 4 | 演示模式、真实模式、显式关闭、演示模式下拒绝走真实授权 |
| 授权地址与回调 | 7 | appid / scope / state 拼装、公众号模式、伪造 state、用户取消、首次登录建号、同 openid 复用、state 不可重放、微信接口报错转 502 |
| 模拟登录 | 5 | 微信建号、同 openid 复用、默认身份、非法 openid 400、微信账号无法用工号密码登录 |
| 绑定与解绑 | 6 | 未登录 401、绑定到已有工号、一个微信不能绑两个账号、一个账号不能绑两个微信、解绑、微信建号禁止解绑 |

实测：`.\.venv\Scripts\python.exe -m pytest backend\tests -q` → `48 passed`。

## 8. 踩过的坑与结论

| 现象 | 结论 |
| --- | --- |
| 启动后查询报 `no such column: document_categories.created_at` | 模型加了字段但没生成迁移；补迁移 + `flask db upgrade` 解决。SQLAlchemy 不会自动改表结构 |
| 浏览器打开页面 404 Not Found | 5000 端口被另一个 `doc-platform` 服务占用，不是本项目后端；用 `/api/health` 是否返回 `{"status":"ok"}` 判断 |
| 原型页面不能双击打开 | `file://` 方式无法带 Cookie 调 Flask API，必须先启动后端再从 `/` 进入 |
| 两个虚拟环境互相干扰 | `.venv` 跑 Flask 项目，`.django-learning` 只跑 Django 教程；一个终端只激活一个，装包统一用 `python -m pip` |
| 上传后重新 seed 找不到文件 | `instance/` 和 `media/` 不进版本库，换机器要重新执行 `db upgrade` + `seed` |
| 运行 `.ps1` 脚本报「字符串缺少终止符」 | Windows PowerShell 5.1 按 ANSI/GBK 解析**无 BOM 的 UTF-8** 脚本，中文的多字节序列会吃掉结尾引号。`tools/wechat-tunnel.ps1` 因此保持纯 ASCII；自己要写含中文的脚本，用 `pwsh` 或另存为 UTF-8 with BOM |

## 9. 代码里还没解决的隐患

这些是读代码时发现、但当前实现没有处理的点，答辩被追问时可以主动说：

1. `_get_document_or_404` / `_get_category_or_404` 名字里有 404，实际只返回 `None`，404 靠调用方手动判断。要么改名成 `_get_document`，要么直接 `abort(404)`。
2. 版本号用「查最大值 + 1」计算，高并发下两个请求可能算到同一个号；数据库唯一约束能拦住，但会抛 `IntegrityError`，目前没捕获，表现为 500。
3. 文件先写盘、后提交事务。如果 commit 失败，`media/` 里会留下没有数据库记录的孤儿文件。
4. 超过 50 MB 时 Flask 抛 413，返回的是 HTML 错误页，不是统一 JSON 格式；前端拿到会解析失败。
5. `create_category` 没处理分类名重复，唯一约束冲突会变成 500。
6. `SECRET_KEY` 是硬编码的开发值，上线必须换成环境变量。
7. 微信登录的 `state` 存在 Flask session 里，依赖浏览器 Cookie；如果以后改成前后端完全分离、跨站部署，`state` 和会话都要跟着调整（SameSite、CORS、凭证模式）。
8. 演示模式（`WECHAT_MOCK_ENABLED`）默认开启，任何人在拿不到 `WECHAT_APP_ID` 的开发环境里都能用一个 openid 建号登录；上线前要么配好真实应用信息，要么显式设成 `0`。

## 10. 自测问答

**为什么这个项目选 Flask 而不是 Django？**
模块只提供 JSON API，业务边界清晰，不需要 Admin 和完整的 ORM 约定；Flask 的路由和蓝图更轻，代码量小、依赖少，适合先跑通业务。Django 作为对照学习，不重复实现。

**版本号唯一性靠什么保证？**
应用层 `max(已有版本号) + 1` 算出下一个号，数据库层再加 `(document_id, version_number)` 唯一约束兜底。前者保证正常流程连续，后者防止异常写入。

**为什么 `create_document` 里要 `db.session.flush()`？**
文件名和版本记录都需要文档 id，而 id 要等插入数据库才有；`flush` 会把 INSERT 发给数据库并拿到自增 id，但不提交事务，后面出错还能整体回滚。

**未登录为什么返回 401 而不是跳转登录页？**
前端用 fetch 调接口，跳转会拿到一页 HTML，解析不出错误；改成 `unauthorized_handler` 返回 JSON，前端统一按 401 处理并跳自己的登录页。

**文件为什么存磁盘、数据库只存路径？**
SQLite 存大二进制会拖慢查询和备份；文件系统更适合存文件，数据库只保留名字和元信息，两者靠 `file_path` 对应。

**上传文件名会不会有路径穿越风险？**
不会。落盘用的是后端生成的 `doc_<id>_v<n>_<毫秒><后缀>`，用户提供的原始文件名只作为字符串存库、并在下载时作为 `download_name` 使用，不参与路径拼接。

**权限为什么要分两层？**
建分类、建文档这类操作只跟人的角色有关；上传版本跟「这份文档归谁负责」有关。两者依据不同，所以一层用 `role`，一层用 `owner_id`。

## 11. 常用命令

```powershell
# 进入 Flask 环境
& .\.venv\Scripts\Activate.ps1

# 初始化并启动
.\.venv\Scripts\python.exe -m flask --app backend\run.py db upgrade
.\.venv\Scripts\python.exe -m flask --app backend\run.py seed
.\.venv\Scripts\python.exe backend\run.py

# 测试
.\.venv\Scripts\python.exe -m pytest backend\tests -q

# 迁移
.\.venv\Scripts\python.exe -m flask --app backend\run.py db migrate -m "说明"
.\.venv\Scripts\python.exe -m flask --app backend\run.py db upgrade

# 微信登录配置自检（不联网，有问题退出码 1）
.\.venv\Scripts\python.exe -m flask --app backend\run.py wechat-check

# 起了 ngrok / cpolar 之后，让它算出回调地址和白名单域名
.\.venv\Scripts\python.exe -m flask --app backend\run.py wechat-tunnel

# 排查「微信里提示登录失败」：回看事件日志 / 验证凭据
.\.venv\Scripts\python.exe -m flask --app backend\run.py wechat-log --lines 20
.\.venv\Scripts\python.exe -m flask --app backend\run.py wechat-token-test
```

## 12. 还没做完的事

已补齐（2026-09-22）：

- `GET /api/users`：管理员获取用户列表，供新建文档选择负责人。
- `PATCH /api/documents/{id}`：管理员修改文档信息 / 负责人 / 状态。
- 分类管理、新建文档两个管理员页面。
- 文档编辑页面（改标题、分类、负责人、状态、说明）。
- 下拉选单改为可搜索下拉。
- 文档「废弃 / 归档」状态（active / archived / deprecated），列表可按状态筛选。
- 上传大小上限调整为 50 MB。
- 分类改名 / 删除（`PATCH` / `DELETE /api/categories/{id}`）。
- 微信扫码登录（`/api/auth/wechat/**`）：真实模式走开放平台 / 公众号授权，没配应用信息时进演示模式；支持绑定已有工号、解绑和「账号设置」页面。

还没做完：

暂无（此前列出的项已全部补齐）。

更细的业务走查看 `docs/business-walkthrough.md`，接口字段看 `docs/api-spec.md`，需求原文看 `docs/document-module-requirements.md`。
