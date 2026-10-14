# 部署到 PythonAnywhere（免费、免信用卡）

PythonAnywhere 免费版不需要信用卡，能跑这个 Flask 后端，而且磁盘是持久的——重新加载
网站不会清空数据库和上传的文件，这是它相比 Render 免费版的优势。适合给老师、外部测试
同学验收演示。

免费版的代价（下面「免费版能做/不能做」有完整清单）：只能用它给的
`<你的用户名>.pythonanywhere.com` 域名、不能绑自己的域名、外网访问受限（**真实微信登录
和 AI 问答/自动预审都用不了**）。

## 一、注册

1. 打开 <https://www.pythonanywhere.com>，点 Pricing → 选 **Beginner（Free）** → Create account。
2. 只填用户名、邮箱、密码，**不需要信用卡、不需要手机号**。
3. 用户名会变成你的网址：`https://<用户名>.pythonanywhere.com`。

## 二、把代码拉下来

Dashboard → New console → **Bash**，然后：

```bash
git clone https://github.com/zhouqq-hash/-Document-collaboration-platform.git ~/doc-collab
```

（GitHub 在免费账号的外网白名单里，`git clone` 可以正常用。）

## 三、建虚拟环境、装依赖

先看看有哪些 Python 版本：

```bash
ls /usr/bin/python3*
```

然后建环境、装依赖（把 `3.11` 换成上一步存在且 ≥ 3.11 的版本）：

```bash
mkvirtualenv --python=/usr/bin/python3.11 doc-collab-env
pip install -r ~/doc-collab/backend/requirements.txt
```

> 如果 `mkvirtualenv` 不存在，用 `python3.11 -m venv ~/doc-collab-env` 代替，后面虚拟环境
> 路径填 `/home/<你的用户名>/doc-collab-env`。

## 四、初始化数据库

```bash
cd ~/doc-collab
flask --app backend/run.py db upgrade
flask --app backend/run.py seed
```

`seed` 是幂等的，重复执行不会造重复数据。

## 五、配置 Web 应用

1. 顶部切到 **Web** 标签 → **Add a new web app**。
2. 域名用默认的 `<用户名>.pythonanywhere.com` → 下一步选 **Manual configuration**（不要选
   Flask 向导，我们用自己的项目结构）→ 选和第三步一致的 Python 版本。
3. 回到 Web 页面，填三处：

   | 字段 | 值 |
   | --- | --- |
   | Source code | `/home/<用户名>/doc-collab` |
   | Working directory | `/home/<用户名>/doc-collab` |
   | Virtualenv | `/home/<用户名>/.virtualenvs/doc-collab-env` |

4. 点 **WSGI configuration file** 那个链接（形如 `/var/www/<用户名>_pythonanywhere_com_wsgi.py`），
   把里面内容全部删掉，换成仓库里 [deploy/pythonanywhere_wsgi.py](../deploy/pythonanywhere_wsgi.py)
   的内容，并改两处：`PROJECT_ROOT` 填你的仓库路径，`SECRET_KEY` 填一串随机字符。
5. 回到 Web 页面点 **Reload**。

## 六、验证

1. 打开 `https://<用户名>.pythonanywhere.com/api/health`，返回 `{"status":"ok"}`。
2. 打开 `https://<用户名>.pythonanywhere.com/` 进登录页，用演示账号登录或点「模拟微信扫码登录」：

   ```text
   admin / admin123       管理员
   teacher / teacher123   文档负责人
   viewer / viewer123     普通教师
   ```

3. 走一遍建分类、上传文档、发起问答，确认都能用。

## 七、以后更新代码

```bash
cd ~/doc-collab
git pull
flask --app backend/run.py db upgrade   # 只有这次更新带了新迁移时才需要
```

然后在 Web 标签点一次 **Reload**。

## 八、免费版能做 / 不能做

| 功能 | 免费版 | 说明 |
| --- | --- | --- |
| 登录（工号密码） | ✅ | |
| 微信登录（演示模式） | ✅ | 页面的「模拟微信扫码登录」 |
| 微信登录（真实扫码） | ❌ | 需要外网调微信接口 + 已备案域名，免费版都做不到 |
| 分类 / 文档 / 版本 / 下载 | ✅ | 上传的文件存在账号磁盘里，重新加载不丢 |
| 问答讨论 / 时间线 / 意见汇总 | ✅ | |
| AI 问答 / 自动预审 | ❌ | 需要外网调模型接口，免费版外网受限 |
| 绑自己的域名 | ❌ | 免费版只能用 `<用户名>.pythonanywhere.com` |
| 每天 CPU 限额 | ⚠️ | 免费账号每天 100 CPU 秒，日常演示够用，别跑批量任务 |
| 磁盘 | ⚠️ | 免费账号 512 MB，装完依赖后剩的不多，别堆大文件 |

## 九、常见问题

- **打开是 502 / 报错页**：Web 标签下方有 error log，先看它。
- **ModuleNotFoundError: No module named 'app'**：WSGI 文件里的 `BACKEND_DIR` 路径不对，
  确认 `PROJECT_ROOT` 指向真正的仓库目录。
- **改了代码但页面没变**：Web 标签点 Reload；PythonAnywhere 不会像 Render 那样自动重启。
- **上传后下载报 500**：确认 `~/doc-collab/backend/media/` 存在且可写，重新跑一次
  `flask --app backend/run.py seed` 可以补回示例文件。
- **代码从哪来**：PythonAnywhere 是从 GitHub 拉代码的，**本地没提交的改动它拉不到**，先提交
  并推送。

## 十、和 Render 方案的关系

仓库里同时保留了 Render 的配置（`render.yaml`、`scripts/render-start.sh`）。哪天有了一张
双币信用卡、想要自定义域名或需要外网能力，可以直接切过去，不需要返工。
