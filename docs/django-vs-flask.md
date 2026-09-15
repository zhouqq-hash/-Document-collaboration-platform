# Flask 与 Django 对照学习笔记

本项目使用 Flask 实现，Django 只做对照学习。

| 概念 | Flask | Django |
| --- | --- | --- |
| 项目结构 | 手动组织 app/blueprint | 自动生成 project/app |
| 路由 | `@app.route` | `urls.py` path 配置 |
| 视图 | 函数视图，返回 JSON/模板 | 函数视图或类视图，返回 HttpResponse |
| 模板 | Jinja2 | Django Template Language |
| ORM | Flask-SQLAlchemy | Django ORM |
| 模型 | 继承 `db.Model` | 继承 `models.Model` |
| 迁移 | Flask-Migrate/Alembic | `manage.py makemigrations/migrate` |
| 认证 | Flask-Login | Django auth |
| 后台 | 需自己搭建 | Django Admin 自带 |
| 表单 | 手动处理请求数据 | Django Form/ModelForm |

学习顺序建议：

1. 先通过 Flask 文档管理模块理解路由、请求、响应、模型和权限。
2. 再读 Django 官方 tutorial，理解 MVT、Admin、ORM 和迁移。
3. 遇到同一业务时，尝试用 Django 思路做小练习，但不重复实现本项目。
