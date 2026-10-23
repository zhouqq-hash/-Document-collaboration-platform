# 部署到 Render：公网运行与恢复

## 1. 先选对部署形态

| 用途 | 配置 | 数据是否可靠 |
| --- | --- | --- |
| 课堂演示、一次性验收 | Render `free` Web Service + 临时 SQLite | 否。休眠、部署、重启都可能清空数据 |
| 老师日常公网使用 | `starter` Web Service + 5 GB 持久盘 | 是。数据库、上传文件和备份都在 `/var/data` |

仓库里的 `render.yaml` 使用第二种配置。免费实例仍可用于看界面，但不能作为“数据不因重启
丢失”的交付环境。

## 2. Blueprint 首次部署

1. 代码推送到 GitHub 的 `main` 分支。
2. Render 控制台 → New → **Blueprint**，选择本仓库。
3. Render 读取 `render.yaml`，创建 `starter` Web Service 和持久盘
   `doc-collab-data`。
4. 按提示填写 `BOOTSTRAP_ADMIN_PASSWORD`，至少 12 位。不要把该密码提交到仓库。
5. 等待 `db upgrade`、管理员初始化、`doctor --strict` 和健康检查全部通过。
6. 首次登录并确认管理员账号后，清空 Render 里的 `BOOTSTRAP_ADMIN_PASSWORD`；
   已存在管理员时启动不会再次使用它。

生产启动不会运行 `flask seed`，因此不会自动写入 `admin/admin123`、
`teacher/teacher123`、`viewer/viewer123` 等演示弱口令。

## 3. 关键环境变量

| 变量 | 生产值 | 说明 |
| --- | --- | --- |
| `APP_ENV` | `production` | 启用生产安全策略 |
| `PUBLIC_DEPLOYMENT` | `1` | 自检时阻止弱口令、临时盘和模拟登录 |
| `SECRET_KEY` | Render 随机生成 | 至少 32 字符，修改后旧会话失效 |
| `DATABASE_URL` | `sqlite:////var/data/doc_collab.db` | 指向持久盘 |
| `UPLOAD_FOLDER` | `/var/data/media` | 上传文件持久化 |
| `BACKUP_FOLDER` | `/var/data/backups` | 恢复快照持久化 |
| `SESSION_COOKIE_SECURE` | `1` | 仅允许 HTTPS 发送会话 Cookie |
| `WECHAT_MOCK_ENABLED` | `0` | 公网禁止模拟微信登录 |
| `SHOW_DEMO_CREDENTIALS` | `0` | 登录页不预填、不展示演示账号 |
| `BOOTSTRAP_ADMIN_USERNAME` | `admin` | 首次创建的管理员工号 |
| `BOOTSTRAP_ADMIN_PASSWORD` | 自行填写 | 仅首次创建时需要，至少 12 位 |

如改用 Render PostgreSQL，把 `DATABASE_URL` 指向数据库连接串即可；项目通过
`psycopg 3` 连接，仍须把 `UPLOAD_FOLDER` 和 `BACKUP_FOLDER` 放在持久盘或改用 COS。

## 4. 创建教师账号

管理员账号建立后，在 Render Shell 执行：

```bash
python -m flask --app backend/run.py create-user \
  --username teacher01 --name "张老师"
```

命令会隐藏输入密码并要求二次确认，避免密码进入 Shell 历史。需要新增管理员时加
`--role admin`。生产环境不要执行 `demo-reset`。

## 5. 验证

```text
/api/health   进程存活
/api/ready    数据库和文件存储均可读写
/             登录页
```

`/api/ready` 任一依赖失败时返回 `503` 和 `not_ready`，Render 不会把新实例接入流量。
业务异常响应带 `X-Request-ID`；5xx 页面会显示同一追踪号，可直接在 Render Logs 中搜索。

上线前至少完成：

1. 管理员登录、退出、重新登录。
2. 新建文档、上传两个版本、下载、回滚。
3. 新建表格、改单元格、保存快照、回滚。
4. 发主题和发言，验证普通教师无法执行管理员操作。
5. 临时停用模型后上传文档，确认可人工兜底通过。
6. 手动重启服务，确认文档、表格、问答和附件仍在。

### 自动公网验收

在本机对公网地址执行两阶段脚本。第一次创建验收表格，随后在 Render 重启服务，再执行
verify；脚本会验证数据仍在，并用普通教师账号确认改名和删除均返回 403：

```powershell
$env:ACCEPTANCE_ADMIN_USER = "admin"
$env:ACCEPTANCE_TEACHER_USER = "teacher01"

.\.venv\Scripts\python.exe tools\public_acceptance.py `
  --base-url https://你的服务.onrender.com --phase create

# 在 Render 重启服务并等待 /api/ready 恢复后
.\.venv\Scripts\python.exe tools\public_acceptance.py `
  --base-url https://你的服务.onrender.com --phase verify --cleanup
```

密码在终端隐藏输入，也可通过 `ACCEPTANCE_ADMIN_PASSWORD` /
`ACCEPTANCE_TEACHER_PASSWORD` 临时注入。验收结束会删除创建的表格。

## 6. 备份与恢复

在 Render Shell 执行：

```bash
python -m flask --app backend/run.py backup
python -m flask --app backend/run.py backup --output /var/data/backups/manual.zip
```

备份包包含一致性快照的 SQLite 和本地文件。`restore` 会先自动生成
`pre-restore-*.zip`，再恢复数据库和文件：

```bash
python -m flask --app backend/run.py restore /var/data/backups/manual.zip --yes
```

生产至少每天备份一次，并把备份复制到 Render 持久盘之外的对象存储。只放在同一块盘上
不能抵御整盘故障。COS 模式不会把全部对象塞进 ZIP，必须在 COS 侧开启版本控制和生命周期
备份。

## 7. AI 不可用

未配置 `COSMOS_API_KEY` 或模型超时时：

- 文档上传、版本、下载、回滚不受影响；
- 问答规则汇总、表格协作、权限控制继续可用；
- 预审记录保留失败原因；
- 文档负责人可以“重新尝试 AI 预审”，也可以填写人工核验依据后明确选择人工兜底；
- 人工兜底不会覆盖或伪造 AI 结果，失败原因和人工确认人都会保留。

## 8. 故障排查

先用只读自检定位：

```bash
python -m flask --app backend/run.py doctor
python -m flask --app backend/run.py recover-reviews --older-than 15
```

常见现象：

- `doctor` 报临时路径：持久盘没有挂载，或环境变量指错了位置。
- `doctor` 报模拟登录：`WECHAT_MOCK_ENABLED` 没有关闭。
- `doctor` 报弱口令：生产数据库里仍有演示账号，应先建立强密码管理员再清理。
- 页面 500：记录页面追踪号，在 Render Logs 搜索 `request_id=<追踪号>`。
- 预审一直“执行中”：服务重启会中断后台任务，执行 `recover-reviews` 后重试或人工兜底。

## 9. 扩容边界

当前 Render 配置是单实例、单 Gunicorn worker、多线程，适合教研组规模。需要多实例时，
SQLite 和本地上传目录都不能共享，应迁移到 PostgreSQL + COS 后再增加实例。
