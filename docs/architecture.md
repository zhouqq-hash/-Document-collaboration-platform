# 文档管理模块软件架构

## 1. 总体架构

采用前后端分离：

- 前端：静态 HTML/CSS/JS，位于 `prototype/`。入口是 `prototype/index.html`，当前只展示 `documents/`（文档管理模块原型，已接入真实 JSON API）。
- 后端：Flask JSON API，位于 `backend/`，负责认证、权限、数据持久化和文件存储。

```text
Browser
  -> static pages (prototype/)
  -> fetch JSON
  -> Flask API (backend/)
  -> SQLAlchemy
  -> SQLite + local media/
```

## 2. 技术选型

| 层次 | 技术 |
| --- | --- |
| Web 框架 | Flask 3 |
| ORM | Flask-SQLAlchemy |
| 数据库迁移 | Flask-Migrate / Alembic |
| 认证 | Flask-Login + Session，支持工号密码和微信扫码两种登录方式 |
| 数据库 | SQLite（开发） |
| 文件存储 | 本地 `backend/media/` |
| 前端 | 原生 HTML/CSS/JS + Bootstrap 5 |
| 测试 | pytest |

## 3. 目录结构

```text
backend/
  app/
    __init__.py
    config.py
    models.py
    auth.py
    wechat.py
    documents.py
    cli.py
  tests/
  db_migrations/
  run.py
  requirements.txt
prototype/
  index.html               # 原型入口页
  documents/               # 文档管理模块原型（本模块的前端界面）
    index.html
    categories.html
    documents.html
    document-detail.html
    upload-version.html
    versions.html
    account.html
    download.html
    wechat-callback.html
    app.js
    styles.css
    mock-data.js
  taskman/                 # 任务看板原型（独立原型，已从入口页撤下，文件暂留）
    index.html
    edit.html
    detail.html
    settings.html
    js/
    css/
docs/
media/
```

## 4. 数据模型

- `User`：id、username、name、password_hash（微信用可为空）、role、wechat_openid、wechat_unionid、avatar_url。
- `DocumentCategory`：id、name、sort_order。
- `Document`：id、title、category_id、owner_id。
- `DocumentVersion`：id、document_id、version_number、filename、file_path、changelog、uploader_id、created_at。

文档的“当前版本”由 `DocumentVersion.version_number` 最大值计算，不额外维护冗余字段。

## 5. 权限策略

- 未登录：API 返回 401。
- 普通教师：只读文档和版本。
- 文档负责人：可上传新版本。
- 管理员：可管理分类、创建文档、上传任意文档新版本。

## 6. 认证方式

- 工号密码：`POST /api/auth/login`，密码用 werkzeug 哈希存储，登录态交给 Flask-Login 的 session。
- 微信扫码：`backend/app/wechat.py`（前缀 `/api/auth/wechat`），支持开放平台扫码（`open`）和公众号网页授权（`mp`）。

微信登录有两种模式：配好 `WECHAT_APP_ID` / `WECHAT_APP_SECRET` 走真实微信 OAuth（`live`）；没配时默认进入演示模式（`mock`），用本地模拟登录跑通页面和测试，离线也能演示。

扫码链路：前端取授权地址 → 微信回调 `/api/auth/wechat/callback` → 服务端校验 `state`、用 code 换 openid → 按 openid 登录 / 建号 / 绑定 → 跳回结果页，原页面轮询 `/api/auth/me` 后进入系统。微信自动创建的账号没有密码（`password_hash` 为空），可以绑定到已有工号上共享原来的权限和文档。

配置步骤、错误码和排错清单见 `docs/wechat-login-guide.md`。

## 7. 文件存储

- 存储层已抽象为「本地 / COS」可切换，默认使用本地 `backend/media/`。
- 通过环境变量 `STORAGE_BACKEND=cos` 切换到腾讯云 COS（见 `docs/cos-storage-guide.md`）。
- 文件命名使用“文档 id + 版本号 + 时间戳 + 原始扩展名”，避免重名。
- 数据库保存的 `file_path` 在本地模式下是文件名、在 COS 模式下是对象 Key，
  下载接口通过存储层的 `read()` 统一返回文件内容。

## 8. 后续演进

- 生产环境切换 PostgreSQL。
- 文件存储已支持切换到腾讯云 COS，生产环境按需启用。
- 微信登录已支持真实模式和演示模式，生产环境配好 `WECHAT_*` 并关闭演示开关即可。
- 使用 Gunicorn + Nginx 部署。
