# 腾讯云轻量应用服务器部署：Docker + 持久云硬盘

## 1. 选择地域与配置

| 场景 | 建议 |
| --- | --- |
| 暂时没有 ICP 备案 | 选择香港地域 |
| 已有 ICP 备案和域名 | 选择上海、广州等大陆地域，访问速度更好 |
| 系统镜像 | Ubuntu 24.04 或腾讯云提供的 Docker CE 镜像 |
| 配置 | 至少 2 GB 内存；数据主要占用系统云硬盘 |

轻量服务器、域名和实名认证都可用微信或支付宝支付。生产环境不要选择月流量过低或自动关机
的体验套餐。

## 2. 域名、DNS 和防火墙

1. 准备域名，例如 `docs.example.com`。
2. 在 DNS 中添加 `A` 记录，直接指向轻量服务器公网 IPv4，并关闭冲突的 AAAA 记录。
3. 腾讯云防火墙只放行：

```text
22/tcp    SSH
80/tcp    HTTP 跳转和证书验证
443/tcp   HTTPS
443/udp   HTTP/3，可选
```

不要对外开放 8000 端口。应用只在 Docker 内网中由 Caddy 反向代理。

DNS 生效后再申请证书；可用 `ping docs.example.com` 或
`nslookup docs.example.com` 核对 IP。

## 3. 安装 Docker

如果购买时选择 Docker CE 镜像，可跳过安装步骤。否则使用 Docker 官方仓库安装
Docker Engine 和 Compose v2，并把当前用户加入 docker 组：

```bash
sudo apt update
sudo apt install -y git curl ca-certificates
sudo usermod -aG docker "$USER"
newgrp docker
docker version
docker compose version
```

香港或大陆服务器均可访问 Docker Hub；若拉取镜像慢，可在腾讯云控制台为 Docker 配置镜像加速。

## 4. 拉取代码并部署

```bash
cd ~
git clone https://github.com/zhouqq-hash/-Document-collaboration-platform.git doc-collab
cd doc-collab
bash scripts/tencent-lighthouse-bootstrap.sh
```

脚本会询问：

- 已解析到服务器的域名；
- 证书通知邮箱；
- 首个管理员的隐藏密码和二次确认。

然后自动生成 `.env` 和随机 `SECRET_KEY`、构建镜像、启动应用、等待 `/api/ready`、
初始化管理员并运行 `doctor --strict`。最后会检查 HTTPS。

部署地址：

```text
https://你的域名/
```

## 5. 持久化结构

Docker Compose 创建三个命名卷：

| 卷 | 内容 |
| --- | --- |
| `app_data` | SQLite、上传附件、应用备份 |
| `caddy_data` | HTTPS 证书和私钥 |
| `caddy_config` | Caddy 运行配置 |

这些卷位于腾讯云系统盘，容器重建、服务器重启和拉取新代码都不会删除。

查看实际卷名：

```bash
docker compose config --volumes
docker volume inspect doc-collab_app_data
```

不要执行 `docker compose down -v`，`-v` 会删除持久卷。

## 6. 公网验收

在本地仓库运行两阶段验收：

```powershell
$env:ACCEPTANCE_ADMIN_USER = "admin"
$env:ACCEPTANCE_TEACHER_USER = "teacher01"

.\.venv\Scripts\python.exe tools/public_acceptance.py `
  --base-url https://你的域名 --phase create
```

在腾讯云控制台重启轻量服务器或执行：

```bash
docker compose restart
```

等待 HTTPS 恢复后：

```powershell
.\.venv\Scripts\python.exe tools/public_acceptance.py `
  --base-url https://你的域名 --phase verify --cleanup
```

该脚本验证：

- `/api/health` 和 `/api/ready`；
- 公网登录页不暴露演示凭据；
- 写入的数据在重启后仍存在；
- 普通教师修改/删除管理员表格均返回 403；
- 最后清理验收表格。

## 7. 创建老师账号

```bash
cd ~/doc-collab
docker compose exec app python -m flask --app backend/run.py \
  create-user --username teacher01 --name "张老师"
```

密码隐藏输入。不要创建 `teacher123` 等弱口令。

## 8. 备份、恢复和云快照

手工备份并只保留最近 14 份自动备份：

```bash
docker compose exec app python -m flask --app backend/run.py \
  backup --keep 14
```

复制备份到服务器当前目录：

```bash
docker compose exec app sh -c 'ls -lh /data/app/backups'
docker compose cp app:/data/app/backups/备份文件名.zip ./
```

恢复时先停止应用，再运行一次性容器；恢复命令会自动生成恢复前快照：

```bash
docker compose stop caddy app
docker compose run --rm app python -m flask --app backend/run.py \
  restore /data/app/backups/备份文件名.zip --yes
docker compose up -d
```

同时在腾讯云控制台为轻量服务器磁盘开启**自动快照**，并把重要备份下载到另一位置。
Cloud disk snapshot 与备份 ZIP 互补，不能只保留其中一种。

每日自动备份示例，在服务器执行 `crontab -e`：

```cron
30 3 * * * cd /home/ubuntu/doc-collab && docker compose exec -T app python -m flask --app backend/run.py backup --keep 14 >> /home/ubuntu/doc-backup.log 2>&1
```

如果登录用户不是 `ubuntu`，同步修改路径。

## 9. AI 与微信

不配置 `COSMOS_API_KEY` 时：

- 文档、表格、问答、版本和回滚正常；
- 预审记录会标记 AI 不可用；
- 负责人可填写核验依据后人工兜底。

需要 AI 时在 `.env` 增加：

```text
COSMOS_API_KEY=你的密钥
COSMOS_API_BASE=https://api.siliconflow.cn/v1
COSMOS_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

然后：

```bash
docker compose up -d
```

真实微信登录还需要应用 ID、密钥和已备案且配置正确的回调域名。模拟微信登录在这个
Compose 配置中固定关闭。

## 10. 更新、排障和回滚

更新代码：

```bash
cd ~/doc-collab
git pull --ff-only
docker compose up -d --build
docker compose exec -T app python -m flask --app backend/run.py doctor --strict
```

查看日志：

```bash
docker compose ps
docker compose logs --tail=200 app
docker compose logs --tail=200 caddy
```

页面 5xx 会显示 `request_id`，在上述日志中搜索同一 ID。

常见问题：

- HTTPS 证书失败：检查 DNS A 记录、80/443 防火墙和 `docker compose logs caddy`。
- 应用不健康：执行 `docker compose logs app`，确认 `/data` 持久卷可写。
- 端口被占用：运行 `sudo ss -lntp | grep -E ':80|:443'`。
- 预审卡住：执行 `docker compose exec app python -m flask --app backend/run.py recover-reviews`。
- 需要代码回滚：使用 `git revert` 生成反向提交，再 `docker compose up -d --build`；
  不要使用覆盖云硬盘数据的方式回滚代码。

## 11. 文件清单

| 文件 | 用途 |
| --- | --- |
| `Dockerfile` | Python 3.11、Gunicorn、非 root 用户、只读应用层 |
| `docker-compose.yml` | 应用、Caddy、健康检查、自动重启、持久卷 |
| `deploy/Caddyfile` | 域名反向代理和自动 HTTPS |
| `scripts/docker-entrypoint.sh` | 迁移、中断预审回收、启动检查 |
| `scripts/tencent-lighthouse-bootstrap.sh` | 首次环境和管理员初始化 |
