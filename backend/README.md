# 文档管理后端（Flask）

这是“教学文档协作平台”文档管理模块的 Flask 后端，包含登录认证、分类、文档、版本上传、下载和权限校验。

## Flask 技术点

- Flask 应用工厂：`app/__init__.py`
- Blueprint 拆分路由：`app/auth.py`、`app/documents.py`
- Flask-SQLAlchemy 数据模型：`app/models.py`
- Flask-Migrate 数据库迁移：`db_migrations/`
- Flask-Login 登录和会话：`app/auth.py`
- 文件上传和下载：`app/documents.py`
- JSON 接口和统一响应格式：`app/utils.py`
- pytest 自动化测试：`tests/`

## 运行环境

- Python 3.11+
- Flask 3
- SQLite（开发环境）

## 本地运行

在 `backend` 目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m flask --app run.py db upgrade
python -m flask --app run.py seed
python run.py
```

上面这段是按「只拿到 `backend/` 目录」的场景写的，`.venv` 会建在 `backend/` 下。在完整仓库里，Flask 环境是仓库根目录的 `.venv`，Django 对照学习用的是另一个环境 `.django-learning`，对应 `djangotutorial/`，两者互不相通，别把 Django 装进 `.venv`。详见根目录 `README.md` 的「Python 环境说明」。

启动后访问：

```text
http://127.0.0.1:5000/
```

演示账号：

```text
admin / admin123       管理员
teacher / teacher123   文档负责人
viewer / viewer123     普通教师
```

## 运行测试

```powershell
python -m pytest tests -q
```

## 数据存储

- SQLite 数据库：`instance/doc_collab.db`
- 上传文件：`media/`
- 数据库结构：`db_migrations/`

`instance/` 和 `media/` 下的运行数据默认不提交版本库。其他人拿到代码后执行 `db upgrade` 和 `seed` 即可生成自己的数据库和演示数据。

## 主要接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/logout` | 退出登录 |
| GET | `/api/auth/me` | 当前用户 |
| GET | `/api/categories` | 分类列表 |
| POST | `/api/categories` | 新建分类，仅管理员 |
| GET | `/api/documents` | 文档列表 |
| POST | `/api/documents` | 新建文档并上传首个版本 |
| GET | `/api/documents/{id}` | 文档详情 |
| GET | `/api/documents/{id}/versions` | 历史版本 |
| POST | `/api/documents/{id}/versions` | 上传新版本 |
| GET | `/api/documents/{id}/versions/{version_id}/download` | 下载版本 |

## 学习重点

这个后端适合用来理解：

1. Flask 如何接收请求并返回 JSON。
2. Blueprint 如何组织不同业务模块。
3. SQLAlchemy 如何表达用户、分类、文档和版本之间的关系。
4. Flask-Migrate 如何管理数据库结构变化。
5. Flask-Login 如何保存登录状态。
6. 后端如何校验角色和资源权限。
7. pytest 如何验证上传、下载、版本递增和越权访问。
