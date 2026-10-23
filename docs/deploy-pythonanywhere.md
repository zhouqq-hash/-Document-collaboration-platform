# 部署到 PythonAnywhere：免信用卡、持久磁盘

## 1. 适用场景

PythonAnywhere Beginner（Free）不要信用卡，账号磁盘在 Reload、重启和重新部署之间
持续保留。适合没有 Render 可接受银行卡、以工号密码登录的小规模教研团队。

限制必须提前明确：

- 只能使用 `<用户名>.pythonanywhere.com`，不能绑定自己的域名；
- 免费账号每天约 100 CPU 秒，适合小团队低频使用；
- 账号磁盘约 512 MB，需要控制附件和备份数量；
- 免费账号外网访问受限，真实微信登录和模型 API 通常不可用；
- AI 不可用时文档、表格、问答、权限流程和人工兜底仍然可用。

## 2. 注册与拉取代码

1. 打开 <https://www.pythonanywhere.com>，选择 Beginner（Free）创建账号。
2. Dashboard → **New console → Bash**。
3. 拉取已经包含公网加固的 `main`：

```bash
git clone https://github.com/zhouqq-hash/-Document-collaboration-platform.git \
  ~/doc-collab
```

如果提示 `destination path ... already exists`，不要重复克隆，也不要直接删除旧目录：

```bash
cd ~/doc-collab
git status --short --branch
git remote -v
git pull --ff-only
```

- `git status` 显示工作区干净、远端是目标 GitHub 仓库时，直接 `git pull --ff-only`。
- 远端不是目标仓库时：`git remote set-url origin https://github.com/zhouqq-hash/-Document-collaboration-platform.git`，
  再执行 `git pull --ff-only`。
- 如果目录不是 Git 仓库，或本地改动无法合并，先改名保留：
  `mv ~/doc-collab ~/doc-collab-old-$(date +%Y%m%d%H%M)`，然后重新执行 clone。

## 3. 创建环境和持久数据目录

选择 Python 3.11 或更高版本：

```bash
ls /usr/bin/python3*
mkvirtualenv --python=/usr/bin/python3.11 doc-collab-env
pip install -r ~/doc-collab/backend/requirements.txt
mkdir -p ~/doc-collab-data/media ~/doc-collab-data/backups
```

如果 `mkvirtualenv` 不存在，可用：

```bash
python3.11 -m venv ~/doc-collab-env
source ~/doc-collab-env/bin/activate
pip install -r ~/doc-collab/backend/requirements.txt
```

## 4. 设置生产环境

每次新开 Bash 执行部署命令时都先设置：

```bash
test -f ~/doc-collab-data/secret_key || \
  python3 -c "from pathlib import Path; import secrets; Path.home().joinpath('doc-collab-data/secret_key').write_text(secrets.token_urlsafe(48))"
chmod 600 ~/doc-collab-data/secret_key
export SECRET_KEY="$(cat ~/doc-collab-data/secret_key)"
export APP_ENV=production
export PUBLIC_DEPLOYMENT=1
export DATABASE_URL="sqlite:////home/$USER/doc-collab-data/doc_collab.db"
export UPLOAD_FOLDER="/home/$USER/doc-collab-data/media"
export BACKUP_FOLDER="/home/$USER/doc-collab-data/backups"
export SESSION_COOKIE_SECURE=1
export WECHAT_MOCK_ENABLED=0
export SHOW_DEMO_CREDENTIALS=0
export TRUST_PROXY_HEADERS=1
```

`SECRET_KEY` 不需要手工保存到仓库：WSGI 模板会在第一次运行时生成
`~/doc-collab-data/secret_key`，权限为 600，并在以后保持不变。

## 5. 初始化数据库和管理员

先激活虚拟环境，然后执行一个引导脚本：

```bash
workon doc-collab-env
cd ~/doc-collab
bash scripts/pythonanywhere-bootstrap.sh
```

脚本会检查仓库无未提交改动，创建持久数据目录和随机密钥，执行迁移、管理员初始化和
`doctor --strict`。管理员密码会隐藏输入并要求二次确认。

完成后创建教师账号：

```bash
python -m flask --app backend/run.py create-user \
  --username teacher01 --name "张老师"
```

不要执行 `seed`、`demo-reset`，也不要创建 `admin123` / `teacher123` 这类演示弱口令。

`doctor --strict` 必须没有阻塞项；AI 未配置只会显示提醒，不影响核心业务。

## 6. 配置 Web 应用

1. Web → **Add a new web app**。
2. 使用默认域名 → **Manual configuration** → 选择与虚拟环境一致的 Python 版本。
3. Source code / Working directory 填 `/home/<用户名>/doc-collab`。
4. Virtualenv 填 `/home/<用户名>/.virtualenvs/doc-collab-env`
   （如果手动创建则是 `/home/<用户名>/doc-collab-env`）。
5. 打开 WSGI configuration file，清空后粘贴
   [deploy/pythonanywhere_wsgi.py](../deploy/pythonanywhere_wsgi.py) 的全部内容。
6. 如果仓库或数据目录不在默认位置，修改模板顶部的
   `DOC_COLLAB_PROJECT_ROOT` / `DOC_COLLAB_DATA_ROOT` 默认值。
7. 保存并点 **Reload**。

模板会自动启用：

```text
生产环境 / 公网模式
持久 SQLite + 持久附件 + 持久备份
Secure / HttpOnly / SameSite=Lax Cookie
关闭模拟微信登录和演示凭据
稳定且持久化的随机 SECRET_KEY
```

## 7. 验证

```text
https://<用户名>.pythonanywhere.com/api/health
https://<用户名>.pythonanywhere.com/api/ready
https://<用户名>.pythonanywhere.com/
```

登录页应当为空，不显示演示账号。随后完成一次：

1. 管理员登录；
2. 新建分类和文档并上传附件；
3. 普通教师访问与越权操作；
4. Web → Reload 后重新登录，确认数据仍在；
5. 没有模型时上传文档，确认可走人工兜底。

也可在本机使用 [public_acceptance.py](../tools/public_acceptance.py) 做两阶段验收：

```powershell
$env:ACCEPTANCE_ADMIN_USER = "admin"
$env:ACCEPTANCE_TEACHER_USER = "teacher01"

.\.venv\Scripts\python.exe tools/public_acceptance.py `
  --base-url https://你的用户名.pythonanywhere.com --phase create

# PythonAnywhere Web 页面点 Reload 后
.\.venv\Scripts\python.exe tools/public_acceptance.py `
  --base-url https://你的用户名.pythonanywhere.com --phase verify --cleanup
```

## 8. 备份与恢复

```bash
cd ~/doc-collab
flask --app backend/run.py backup --keep 2
flask --app backend/run.py restore \
  /home/$USER/doc-collab-data/backups/备份文件.zip --yes
```

由于免费磁盘只有约 512 MB，建议保留最新 1 至 2 份备份，并定期把备份下载到本机。
执行 restore 后，在 Web 页面立即点 Reload。

## 9. 更新代码

```bash
cd ~/doc-collab
git pull
test -f ~/doc-collab-data/secret_key || \
  python3 -c "from pathlib import Path; import secrets; Path.home().joinpath('doc-collab-data/secret_key').write_text(secrets.token_urlsafe(48))"
export SECRET_KEY="$(cat ~/doc-collab-data/secret_key)"
export APP_ENV=production
export PUBLIC_DEPLOYMENT=1
export DATABASE_URL="sqlite:////home/$USER/doc-collab-data/doc_collab.db"
export UPLOAD_FOLDER="/home/$USER/doc-collab-data/media"
export BACKUP_FOLDER="/home/$USER/doc-collab-data/backups"
export SESSION_COOKIE_SECURE=1
export WECHAT_MOCK_ENABLED=0
export SHOW_DEMO_CREDENTIALS=0
flask --app backend/run.py db upgrade
flask --app backend/run.py doctor --strict
```

最后在 Web 页面点 **Reload**。数据目录与代码目录分离，拉取新代码不会覆盖业务数据。

## 10. 常见问题

- 页面 502：Web 页面下方查看 error log，先确认虚拟环境和 `PROJECT_ROOT`。
- `pip` 报 `No module named '_posixsubprocess'`：这是虚拟环境/平台 Python 扩展问题，
  不是项目依赖缺失。虚拟环境与 `~/doc-collab-data` 数据目录互不影响，可安全重建：

  ```bash
  deactivate 2>/dev/null || true
  bash ~/doc-collab/scripts/pythonanywhere-environment-check.sh
  mv ~/.virtualenvs/doc-collab-env \
    ~/.virtualenvs/doc-collab-env-broken-$(date +%Y%m%d%H%M)
  mkvirtualenv --python=/usr/bin/python3.11 doc-collab-env
  python -m pip install --upgrade pip
  python -m pip install -r ~/doc-collab/backend/requirements.txt
  ```

  检查脚本会列出每个版本“可用 / 损坏 / 版本低”。如果 Python 3.11 也标记为损坏，
  说明该 Python 版本本身不完整，不要再复制旧环境；选择脚本标记为可用的版本重建，
  并把上方 `--python` 路径换成对应版本。旧环境只改名，不直接删除。
- 克隆提示目录已存在：进入旧目录检查 `git status` / `git remote -v`，通过 `git pull --ff-only`
  更新；不要直接覆盖或删除旧目录。
- `ModuleNotFoundError: app`：检查 `~/doc-collab/backend` 是否存在。
- Cookie 登录后立即失效：确认站点是 HTTPS，且 `SESSION_COOKIE_SECURE=1`。
- AI 请求失败：免费账号外网受限属于预期情况，使用预审记录中的人工兜底。
- 预审一直执行中：在 Bash 执行 `flask --app backend/run.py recover-reviews`。
- 磁盘不足：下载并清理旧备份，或减少大附件。
