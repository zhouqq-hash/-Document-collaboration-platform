# 教学文档协作平台

当前仓库先实现“文档管理模块”，采用 Flask JSON API + 静态前端原型。

## 目录

- `docs/`：全部文档的索引和分组见 `docs/README.md`（需求、架构、接口规范、原型验收、微信登录手册与流程、部署、Django 对照学习、工作日志）。
- `prototype/`：业务方向原型的入口页，下面存放 `documents/`（文档管理模块原型，已接入 Flask API，入口页只展示它）和 `taskman/`（任务看板原型，已从入口页撤下、文件暂留）。
- `backend/`：Flask 后端实现。
- `djangotutorial/`：Django 官方教程的练习项目，属于对照学习资料，不是本项目成果，分享给别人时注意区分。

后端单独运行时，优先查看 `backend/README.md`。

项目分工与技术路线见 `docs/project-division.md`：当前个人角色为技术后端，Flask 为首选实现框架，Django 仅做对照学习。

文档管理模块的业务走查见 `docs/business-walkthrough.md`。

## Python 环境说明

仓库里有两个互相独立的虚拟环境，用途不同，不要混用：

| 环境 | 用途 | 主要依赖 | 对应代码 |
| --- | --- | --- | --- |
| `.venv` | 本项目后端 | Flask、Flask-SQLAlchemy、Flask-Migrate、Flask-Login、pytest | `backend/` |
| `.django-learning` | Django 对照学习 | Django | `djangotutorial/` |

两个环境的 `include-system-site-packages` 都是 `false`，彼此看不到对方的包，也不会继承 Anaconda base 里的包。

进入 Flask 环境（跑本项目的后端）：

```powershell
& .\.venv\Scripts\Activate.ps1
```

进入 Django 环境（学 Django 教程）：

```powershell
& .\.django-learning\Scripts\Activate.ps1
```

也可以不激活，直接用全路径调用对应环境的解释器，效果一样：

```powershell
.\.django-learning\Scripts\python.exe .\djangotutorial\manage.py runserver
```

三条规矩：

- 一个终端只激活一个环境，切换前先执行 `deactivate`。
- 装包统一用 `python -m pip install ...`，不要用裸 `pip`，免得装进另一个环境。
- 提示符前缀就是当前环境名，`(.venv)` 是 Flask，`(.django-learning)` 是 Django。

如果提示「在此系统上禁止运行脚本」，先执行一次：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

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

## 微信登录

登录页支持微信扫码登录，默认是「演示模式」，不用申请微信应用也能演示：

- 演示模式（默认）：后端没配 `WECHAT_APP_ID`，点「模拟微信扫码登录」直接登录；设 `$env:WECHAT_MOCK_ENABLED = "0"` 可以关掉。
- 真实模式：配好 `WECHAT_APP_ID` / `WECHAT_APP_SECRET` / `WECHAT_REDIRECT_URI` 后自动切换，走微信开放平台扫码或公众号网页授权。
- 绑定已有工号：登录后进右上角「账号设置」→「绑定微信」，绑定后扫码登录的就是同一个账号，权限和负责的文档都不变。

当前交付状态：**演示模式可用、真机联调暂停**（试过公众平台测试号 + 公网隧道，排错记录见 `docs/worklog-2026-09-27.md`）。配置项、命令手册、排错对照表和恢复联调的清单都在 `docs/wechat-login-guide.md`；原理和时序见 `docs/wechat-auth-flow.md`；一键起隧道用 `.\tools\wechat-tunnel.ps1`。

## 查看原型

`http://127.0.0.1:5000/` 是原型入口页，当前只展示文档管理模块原型：

| 原型 | 入口 | 说明 |
| --- | --- | --- |
| 文档管理模块原型 | `http://127.0.0.1:5000/documents/index.html` | 已接入真实 API，必须先启动后端 |

先启动后端：

```powershell
.\.venv\Scripts\python.exe backend\run.py
```

再打开 `http://127.0.0.1:5000/`，从入口页进入。文档管理原型的页面不能直接双击打开，因为 `file://` 方式无法调用 Flask API。

## 常见问题

### 运行 pytest / flask 报 ModuleNotFoundError: No module named 'flask_login'

说明当前终端用的不是本项目的虚拟环境。看提示符就能分辨：`(base)` 是 Anaconda 自带的 Python，`(.venv)` 才是本项目的环境。

本项目的依赖（Flask、Flask-Login、pytest 等）只装在 `.venv` 里，所以有两种正确写法：

```powershell
# 写法一（推荐）：直接用虚拟环境里的 python，不用管有没有激活
.\.venv\Scripts\python.exe -m pytest backend\tests -q
.\.venv\Scripts\python.exe -m flask --app backend\run.py db upgrade

# 写法二：先激活虚拟环境，再直接敲命令
.\.venv\Scripts\Activate.ps1
pytest backend\tests -q
```

想确认当前用的是哪个 python：

```powershell
python -c "import sys; print(sys.executable)"
```

输出路径里带 `\.venv\` 才是本项目的环境。另外注意别混用：`.venv` 是 Flask 项目环境，`.django-learning` 是 Django 学习环境，一个终端只激活一个。

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
