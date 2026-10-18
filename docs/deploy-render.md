# 部署到 Render（免费）

Render 是海外 PaaS，可以免费跑这个 Flask 后端：连上 GitHub 仓库、点几下就能拿到一个
`https://<名字>.onrender.com` 的公开地址。适合给老师、外部测试同学验收演示。

## 先看清免费额度的三个限制

- **15 分钟没人访问就休眠**，下次访问约 1 分钟后才醒（首次打开慢是正常的）。
- **磁盘是临时的**：每次重新部署（`git push`）都会新建容器，SQLite 数据库和上传的
  `media/` 文件都会回到初始状态。启动脚本会重新灌一遍演示数据，所以站点永远有账号和
  示例内容，但**上传的文档、问答记录留不住**——这是免费版的取舍，要留存数据得换成付费
  磁盘或 PostgreSQL。
- **真实微信登录用不了**：微信回调要求已备案域名 + HTTPS，`onrender.com` 不满足。线上
  保持默认的**演示模式**（不用申请微信应用，点「模拟微信扫码登录」即可）。

## 一、前置条件

1. 代码已经推到 GitHub（本仓库远端：`zhouqq-hash/-Document-collaboration-platform`，`main` 分支）。
2. Render 能拉到最新代码。**本地没提交的改动不会被部署**，先提交并推送。

## 二、创建服务（二选一）

### 方式 A：用 Blueprint（推荐）

仓库根目录已经有 `render.yaml`，框架、构建命令、启动命令、环境变量都写好了。

1. 打开 Render 控制台 → New → **Blueprint**。
2. 选这个 GitHub 仓库，Render 会读 `render.yaml` 自动建一个免费 Web Service。
3. 点确认，等首次构建完成。

### 方式 B：手动建 Web Service

New → **Web Service**，选仓库后按下面填：

| 配置项 | 值 |
| --- | --- |
| Language / Runtime | Python |
| Branch | `main` |
| Build Command | `pip install -r backend/requirements-render.txt` |
| Start Command | `bash scripts/render-start.sh` |
| Health Check Path | `/api/health` |
| Instance Type | Free |

再在 **Environment** 里加两个变量：

| 变量 | 值 |
| --- | --- |
| `PYTHON_VERSION` | `3.11.9` |
| `SECRET_KEY` | 自己填一串随机字符（覆盖开发默认值，必填） |

## 三、部署后怎么验证

1. 打开 `https://<你的服务>.onrender.com/api/health`，返回 `{"status":"ok"}` 说明后端活着。
2. 打开根地址 `https://<你的服务>.onrender.com/`，进登录页。
3. 用演示账号登录，或点「模拟微信扫码登录」：

   ```text
   admin / admin123       管理员
   teacher / teacher123   文档负责人
   viewer / viewer123     普通教师
   ```

4. 进文档管理和问答管理页各点一遍，确认能建分类、上传版本、发话题。

## 四、可选：让 AI 问答 / 自动预审可用

AI 功能依赖模型接口，没配密钥时这两块会报「没有配置 COSMOS_API_KEY」。要启用就在
Environment 里补：

| 变量 | 值 |
| --- | --- |
| `COSMOS_API_KEY` | 你的模型平台密钥 |
| `COSMOS_API_BASE` | 非默认接口才需要，默认 `https://cosmos.datapower.top/v1` |
| `COSMOS_MODEL` | 非默认模型才需要 |
| `COSMOS_SUMMARY_TIMEOUT` | 问答模块 AI 摘要的等待秒数，默认 30，一般不用改 |

## 五、日常更新

改了代码推上去就会自动重新部署：

```bash
git add -A
git commit -m "update"
git push origin main
```

Render 重新构建时会重置数据（见开头的限制），演示数据由启动脚本自动重建。

## 六、常见问题

- **第一次打开很慢**：免费实例在休眠，约 1 分钟后唤醒，属正常现象。
- **部署失败在 `db upgrade`**：看 Render 的构建日志；本地可先跑
  `flask --app backend/run.py db upgrade` 复现。
- **换端口**：不用改代码，Render 通过 `PORT` 环境变量注入，启动脚本已读取。
- **想换机房**：服务设置的 Region 可在 Singapore 等区域里选，离国内更近。
- **要数据持久 + 真实微信**：免费平台都做不到，需要一台备案域名 + 低价云服务器，
  见根目录 `README.md` 与 `docs/cos-storage-guide.md`。
