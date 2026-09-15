# 文档管理模块软件架构

## 1. 总体架构

采用前后端分离：

- 前端：静态 HTML/CSS/JS，位于 `prototype/`。入口是 `prototype/index.html`，下面并列 `documents/`（文档管理模块原型，已接入真实 JSON API）和 `taskman/`（任务看板原型，纯前端，不接后端）。
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
| 认证 | Flask-Login + Session |
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
    download.html
    app.js
    styles.css
    mock-data.js
  taskman/                 # 任务看板原型（独立原型，不属于本模块）
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

- `User`：id、username、name、password_hash、role。
- `DocumentCategory`：id、name、sort_order。
- `Document`：id、title、category_id、owner_id。
- `DocumentVersion`：id、document_id、version_number、filename、file_path、changelog、uploader_id、created_at。

文档的“当前版本”由 `DocumentVersion.version_number` 最大值计算，不额外维护冗余字段。

## 5. 权限策略

- 未登录：API 返回 401。
- 普通教师：只读文档和版本。
- 文档负责人：可上传新版本。
- 管理员：可管理分类、创建文档、上传任意文档新版本。

## 6. 文件存储

- 开发环境保存在 `backend/media/`。
- 文件命名使用“文档 id + 版本号 + 时间戳 + 原始扩展名”，避免重名。
- 数据库保存相对路径，下载接口通过 `send_from_directory` 返回文件。

## 7. 后续演进

- 生产环境切换 PostgreSQL。
- 文件存储迁移到腾讯云 COS。
- 使用 Gunicorn + Nginx 部署。
