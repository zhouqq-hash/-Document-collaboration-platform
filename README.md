# 教学文档协作平台

当前仓库先实现“文档管理模块”，采用 Flask JSON API + 静态前端原型。

## 目录

- `docs/`：需求、原型验收、架构、接口规范和 Django 对照学习笔记。
- `prototype/`：不连接后端的静态页面原型。
- `backend/`：Flask 后端实现。

项目分工与技术路线见 `docs/project-division.md`：当前个人角色为技术后端，Flask 为首选实现框架，Django 仅做对照学习。

## 本地运行后端

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m flask --app backend\run.py db upgrade
.\.venv\Scripts\python.exe -m flask --app backend\run.py seed
.\.venv\Scripts\python.exe backend\run.py
```

默认账号：

- 管理员：`admin / admin123`
- 教师：`teacher / teacher123`

## 查看原型

直接打开 `prototype/index.html`，或启动后端后访问：

```text
http://127.0.0.1:5000/
```

按页面提示浏览。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
```

## 数据库迁移

```powershell
.\.venv\Scripts\python.exe -m flask --app backend\run.py db init --directory backend\db_migrations
.\.venv\Scripts\python.exe -m flask --app backend\run.py db migrate -m "initial"
.\.venv\Scripts\python.exe -m flask --app backend\run.py db upgrade
```
