# Django 学习笔记（索引 + 结论）

用法只有两条：

1. 一个话题开一个会话，话题结束后立刻在下面的表里加一行。
2. 想法和结论写进“话题记录”，不要指望回头翻聊天记录。

会话可以随时丢，这份文件不会丢。

## 话题索引

| 日期 | 话题 | 一句话结论 | 相关文件 / 代码 |
| --- | --- | --- | --- |
| 2026-09-18 | 示例：Django 与 Flask 的关系 | 两者都是后端框架，Django 自带 Admin 和 ORM 约定 | `docs/django-vs-flask.md` |
| 2026-09-18 | 模型与迁移 | `models.py` 定义模型，`makemigrations` 生成迁移，`migrate` 落到数据库；迁移是可回滚的 Python 文件 | `djangotutorial/polls/models.py`、`djangotutorial/polls/migrations/0001_initial.py` |
| 2026-09-19 | 模型与迁移（实操） | 给 `Question` 加 `description` 字段，生成并应用 `0002_question_description`；SQLite 加列会重建表并复制数据 | `djangotutorial/polls/models.py`、`djangotutorial/polls/migrations/0002_question_description.py` |
|  |  |  |  |

## 预习：大概会分成这几个话题

一次学习差不多只需要开这几场会话，不是一天一场、更不是一问一场：

- [x] 模型与迁移（`models.py`、`makemigrations`、`migrate`）
- [ ] 视图与 URL（`views.py`、`urls.py`、`render`、`HttpResponse`）
- [ ] 模板（DTL、`{% url %}`、`{% static %}`、表单与 `csrf_token`）
- [ ] Admin 后台
- [ ] 表单与用户输入
- [ ] 测试（`manage.py test`、`TestCase`、`client`）
- [ ] 对照练习：用 Django 重写文档模块的一小部分
- [ ] 复盘：为什么本项目最终选 Flask

## 话题记录

每个话题下面按这个格式记，五行以内：

```text
今天做了什么：
产出文件：
报错与结论：
明天第一件事：
待确认：
```

### 1. 模型与迁移

今天做了什么：

- 对照阅读 `polls/models.py` 和 `polls/migrations/0001_initial.py`，理解 `models.Model`、字段类型、`ForeignKey` 的 `on_delete`、Django 默认自增主键。
- 理解迁移链路：改模型 -> `makemigrations` 生成迁移文件 -> `migrate` 应用 -> `showmigrations` 查看状态 -> `sqlmigrate` 可预览 SQL。
- 在 `Question` 里添加 `description = models.CharField(max_length=500, default="")`。
- 用 `makemigrations polls` 生成 `0002_question_description.py`，再用 `migrate polls` 应用到数据库。
- 用 `check`、`showmigrations polls`、`makemigrations --check --dry-run polls` 验证迁移已完成。
- 用 `sqlmigrate polls 0002` 观察 SQL，理解 SQLite 是通过“建新表 -> 复制数据 -> 删旧表 -> 改名”来完成字段增加。
- 和 Flask 对照：`backend/app/models.py` + Flask-Migrate/Alembic，命令是 `flask db migrate` / `flask db upgrade`，迁移文件同样可升级/回滚。

产出文件：

- `djangotutorial/polls/migrations/0002_question_description.py`
- 本笔记（`docs/django-notes.md` 第 1 节）

报错与结论：

- 最开始 `makemigrations --check --dry-run polls` 输出 `0002_question_description.py`，说明模型比迁移多了一个 `description` 字段。
- 执行 `makemigrations` + `migrate` 后，`showmigrations polls` 显示 `[X] 0001_initial` 和 `[X] 0002_question_description`，`makemigrations --check --dry-run` 输出 `No changes detected in app 'polls'`。
- `sqlmigrate polls 0002` 显示 SQLite 用 `CREATE TABLE new__polls_question`、`INSERT ... SELECT`、`DROP TABLE`、`RENAME TO` 完成加列；这不是错误，而是 SQLite 对 `ALTER TABLE` 支持有限时的迁移实现方式。

明天第一件事：

- 进入「视图与 URL」，先清理 `views.py` 的重复导入和重复 `get_object_or_404`，再把 `results` 从占位改成真实渲染。

待确认：

- 暂无。新练习应在 `djangotutorial` 内继续，不动本项目 `backend/`。

### 2. 视图与 URL

### 3. 模板

### 4. Admin 后台

### 5. 表单与用户输入

### 6. 测试

### 7. 对照练习

### 8. 复盘
