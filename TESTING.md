# 给测试同学：怎么把系统跑起来

这是「教学文档协作平台」，当前只实现了**文档管理模块**（登录、分类、文档、版本、上传、下载、权限，外加微信扫码登录的演示模式）。花 10 分钟按下面 5 步跑起来，再照 `docs/testing-guide.md` 里的用例逐条测就行。

## 1. 拿到代码

```powershell
git clone https://github.com/zhouqq-hash/-Document-collaboration-platform.git
cd ./-Document-collaboration-platform
```

不想装 git 也可以：在仓库页面点 **Code → Download ZIP**，解压后进到目录里，后面步骤完全一样。

## 2. 环境要求

| 项目 | 要求 |
| --- | --- |
| 系统 | Windows（文档里的命令都是 PowerShell 写法） |
| Python | 3.11 以上，安装时记得勾选 Add Python to PATH |
| 浏览器 | 桌面版 Chrome 或 Edge，窗口宽度 ≥ 1280 |
| 网络 | 只在装依赖时需要联网，跑起来之后离线也能用 |

用 Mac 或 Linux 的同学对应命令要自己换一下（`python3 -m venv .venv`、`source .venv/bin/activate`、路径用 `/`），其余步骤一致。

## 3. 五步跑起来

在仓库根目录执行：

```powershell
# ① 建虚拟环境并激活（提示符前会出现 (.venv)）
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# ② 装依赖
python -m pip install -r backend\requirements.txt

# ③ 建数据库（第一次必须执行）
python -m flask --app backend\run.py db upgrade

# ④ 灌入演示数据（3 篇文档：正常 / 归档 / 废弃 各一篇）
python -m flask --app backend\run.py demo-reset --yes

# ⑤ 启动
python backend\run.py
```

浏览器打开 **http://127.0.0.1:5000/**，从入口页进「文档管理原型」。注意不能双击 HTML 文件打开，必须走这个地址。

## 4. 演示账号

| 角色 | 账号 | 密码 | 能做什么 |
| --- | --- | --- | --- |
| 管理员 | `admin` | `admin123` | 分类管理、新建/编辑文档、上传任意文档新版本 |
| 文档负责人 | `teacher` | `teacher123` | 上传自己负责的文档新版本 |
| 普通教师 | `viewer` | `viewer123` | 只能查看和下载 |

登录页还有个「模拟微信扫码登录」按钮，那是没配微信应用时的演示模式，点了会直接建号进系统，属于正常现象。

## 5. 开始测试

1. 生成测试用的上传素材：

   ```powershell
   .\tools\make-test-files.ps1
   ```

   会在 `testdata\` 下生成正常文件、不支持的格式、超过 50 MB 的超限文件各一个。

2. 打开 [`docs/testing-guide.md`](docs/testing-guide.md)，按 TC-01 ~ TC-31 逐条走，把结果填在表格里。标「必测」的请务必走完，标「建议测」的尽力。

3. **每跑完一轮先复位再开始下一轮**（上传、新建、改状态都会改数据）：

   ```powershell
   python -m flask --app backend\run.py demo-reset
   ```

## 6. 发现问题怎么反馈

在仓库页面点 **Issues → New issue**，一条缺陷一个 issue，写清这几项：

```text
标题：一句话说清哪里不对
环境与时间：机器 / 浏览器版本 / 测试时间
账号：用的哪个账号
前置条件：从什么状态开始（是否刚跑过 demo-reset）
复现步骤：1. … 2. … 3. …
预期结果：
实际结果：
证据：截图、浏览器控制台报错、后端终端日志
复现概率：每次都出现 / 偶尔出现
```

嫌麻烦也可以直接把填好的用例表格和截图发到群里，汇总由测试负责人处理。

## 7. 常见问题

| 现象 | 处理办法 |
| --- | --- |
| 提示「在此系统上禁止运行脚本」 | 先执行 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` |
| 终端里中文显示成乱码 | 先执行 `$env:PYTHONIOENCODING = "utf-8"` 再跑命令 |
| 打开 `http://127.0.0.1:5000/` 是 404 或不是本系统 | 5000 端口被别的程序占了，见 `README.md`「常见问题」，或换端口：`python -m flask --app backend\run.py run --port 5001` |
| 页面样式错乱、点按钮没反应 | 确认是从 `http://127.0.0.1:5000/` 打开的，不是双击 HTML（`file://` 打不开接口） |
| `pip install` 卡住 | 换国内源：`python -m pip install -r backend\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| 页面在手机上很难看 | 这个原型只做了桌面端，1280 宽以上才正常，请用电脑测 |

## 8. 关于仓库里的文件

- `backend/instance/`、`backend/media/`、`testdata/` 里的东西都是本机运行产生的，**不会**进版本库，也可以随便删。
- 测完想恢复干净状态，执行一次 `python -m flask --app backend\run.py demo-reset` 就行。
- `djangotutorial/` 是 Django 官方教程的练习项目，属于学习资料，不是本系统的一部分，测试时不用管它。
