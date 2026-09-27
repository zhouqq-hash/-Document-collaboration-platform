# 文档管理后端（Flask）

这是“教学文档协作平台”文档管理模块的 Flask 后端，包含登录认证（工号密码 + 微信扫码）、分类、文档、版本上传、下载和权限校验。

## Flask 技术点

- Flask 应用工厂：`app/__init__.py`
- Blueprint 拆分路由：`app/auth.py`、`app/documents.py`
- 微信登录：`app/wechat.py`（开放平台扫码 / 公众号网页授权，带演示模式）
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
| GET | `/api/auth/wechat/config` | 微信登录模式（live / mock / disabled） |
| GET | `/api/auth/wechat/authorize-url` | 生成微信授权地址，`?bind=1` 表示绑定 |
| GET | `/api/auth/wechat/callback` | 微信授权回调 |
| POST | `/api/auth/wechat/mock-login` | 演示模式模拟登录 |
| POST | `/api/auth/wechat/bind` | 绑定微信到当前账号 |
| POST | `/api/auth/wechat/unbind` | 解绑微信 |
| GET | `/api/categories` | 分类列表 |
| POST | `/api/categories` | 新建分类，仅管理员 |
| PATCH | `/api/categories/{id}` | 修改分类名称或排序，仅管理员 |
| DELETE | `/api/categories/{id}` | 删除分类，仅管理员（分类下仍有文档时返回 409） |
| GET | `/api/users` | 用户列表，仅管理员 |
| GET | `/api/documents` | 文档列表 |
| POST | `/api/documents` | 新建文档并上传首个版本 |
| GET | `/api/documents/{id}` | 文档详情 |
| PATCH | `/api/documents/{id}` | 修改文档信息或负责人，仅管理员 |
| GET | `/api/documents/{id}/versions` | 历史版本 |
| POST | `/api/documents/{id}/versions` | 上传新版本 |
| GET | `/api/documents/{id}/versions/{version_id}/download` | 下载版本 |

## 微信登录配置

默认不需要任何配置：没配 `WECHAT_APP_ID` 时进「演示模式」，页面上的「模拟微信扫码登录」直接建号 / 登录，适合离线演示和自动化测试。

接真实微信扫码时设置环境变量再启动：

```powershell
$env:WECHAT_APP_ID = "wx0123456789abcdef"
$env:WECHAT_APP_SECRET = "从开放平台复制"
$env:WECHAT_REDIRECT_URI = "https://你的域名/api/auth/wechat/callback"
```

- `WECHAT_AUTHORIZE_MODE`：`open`（开放平台网站应用扫码，默认）/ `mp`（公众号网页授权）。
- `WECHAT_DEFAULT_ROLE`：微信新账号的角色，默认 `teacher`，只接受 `teacher` / `admin`。
- `WECHAT_MOCK_ENABLED=0`：显式关掉演示模式（没配 AppID 时页面上不再出现微信入口）。
- 微信自动创建的账号没有密码（`password_hash` 为空），不能用工号密码登录；想复用已有工号的权限，登录后在「账号设置」里绑定微信。

配置步骤、接口字段、错误码和排错清单见 `docs/wechat-login-guide.md`。

当前状态：演示模式可用（默认，零配置）；真机联调（公众平台测试号 + 公网隧道）**暂停**，恢复步骤见该文档第 6 节。

配置完可以自检（不联网）：

```powershell
python -m flask --app run.py wechat-check
```

它会打印当前模式、AppID（打码）、授权方式、后端实际使用的回调地址和授权地址示例，并把「回调地址还是文档示例域名」「用了本机内网地址」「不是 https」「只配了一半凭据」等问题标成 `[问题]`，有问题时退出码为 1。

起了内网穿透之后还能让工具把地址算好（读 ngrok / cpolar 的本地 API 4040 端口）：

```powershell
python -m flask --app run.py wechat-tunnel
```

它会给出要设置的 `WECHAT_REDIRECT_URI`、要填进微信后台白名单的域名，以及在微信里该打开的页面地址。
没有 ngrok 的话，仓库根目录的 `tools\wechat-tunnel.ps1` 会用 Cloudflare Tunnel（免费、免注册）起隧道并顺手调用这条命令。

出问题时还有两条命令：

```powershell
python -m flask --app run.py wechat-log --lines 20    # 回看登录每一步的事件日志
python -m flask --app run.py wechat-token-test        # 验证 AppID / AppSecret 是否配对
```

## 学习重点

这个后端适合用来理解：

1. Flask 如何接收请求并返回 JSON。
2. Blueprint 如何组织不同业务模块。
3. SQLAlchemy 如何表达用户、分类、文档和版本之间的关系。
4. Flask-Migrate 如何管理数据库结构变化。
5. Flask-Login 如何保存登录状态。
6. 后端如何校验角色和资源权限。
7. pytest 如何验证上传、下载、版本递增和越权访问。
8. 微信 OAuth：`state` 怎么防重放、授权码怎么换 openid、微信账号怎么绑定到已有工号，以及怎么用配置在「真实 / 演示」两种模式之间切换。
