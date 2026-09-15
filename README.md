# 教学文档协作平台

当前仓库先实现“文档管理模块”，采用 Flask JSON API + 静态前端原型。

## 目录

- `docs/`：需求、原型验收、架构、接口规范、Django 对照学习笔记和工作日志（`worklog-*.md`）。
- `prototype/`：业务方向原型的入口页，下面并列 `documents/`（文档管理模块原型，已接入 Flask API）和 `taskman/`（任务看板原型，纯前端）。
- `backend/`：Flask 后端实现。

后端单独运行时，优先查看 `backend/README.md`。

项目分工与技术路线见 `docs/project-division.md`：当前个人角色为技术后端，Flask 为首选实现框架，Django 仅做对照学习。

文档管理模块的业务走查见 `docs/business-walkthrough.md`。

## 本地运行后端

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m flask --app backend\run.py db upgrade
.\.venv\Scripts\python.exe -m flask --app backend\run.py seed
.\.venv\Scripts\python.exe backend\run.py
```

默认账号：

- 管理员：`admin / admin123`
- 文档负责人：`teacher / teacher123`
- 普通教师：`viewer / viewer123`

## 查看原型

`http://127.0.0.1:5000/` 是原型入口页，里面并列两个原型：

| 原型 | 入口 | 说明 |
| --- | --- | --- |
| 文档管理模块原型 | `http://127.0.0.1:5000/documents/index.html` | 已接入真实 API，必须先启动后端 |
| 任务看板原型 | `http://127.0.0.1:5000/taskman/index.html` | 纯前端，数据在浏览器 localStorage，不依赖后端 |

先启动后端：

```powershell
.\.venv\Scripts\python.exe backend\run.py
```

再打开 `http://127.0.0.1:5000/`，从入口页进入。文档管理原型的页面不能直接双击打开，因为 `file://` 方式无法调用 Flask API；任务看板原型可以直接双击 `prototype\taskman\index.html` 打开。

## 常见问题

### 打开页面显示 404 Not Found

说明 5000 端口上跑的很可能不是本项目的后端。先看是谁占着端口：

```powershell
netstat -ano | findstr :5000
```

判断方法：本项目后端的 `/api/health` 返回 `{"status":"ok"}`，并且 `/` 就是原型入口页。如果返回的是别的格式（例如 `{"code":0,"data":...}`），或者 `/` 是 404，那说明端口被另一个程序占用了。停掉它以后重新运行 `backend\run.py`：

```powershell
Stop-Process -Id <占用端口的 PID>
```

### 不想关掉占用 5000 的程序

换端口启动：

```powershell
.\.venv\Scripts\python.exe -m flask --app backend\run.py run --port 5001
```

然后访问 `http://127.0.0.1:5001/`。

### 以前的页面地址打不开了

原型页面已经整理到 `prototype/documents/` 下，地址要加一层目录，例如：

```text
旧：http://127.0.0.1:5000/categories.html
新：http://127.0.0.1:5000/documents/categories.html
```

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
