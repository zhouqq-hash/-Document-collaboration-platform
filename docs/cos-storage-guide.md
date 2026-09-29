# 接入腾讯云 COS 存储：你需要做的步骤

代码侧已经完成「本地 / COS 可切换」的存储抽象层，默认走本地 `backend/media/`，
不会影响现有功能。要真正把文件存到腾讯云 COS，需要你完成下面这些账号和配置操作。

## 零、先装 COS 的依赖

COS 的 SDK 不在默认依赖里（默认用本地存储，装它会顺带拉一个需要编译的 `crcmod`）。要用 COS 时先补上：

```powershell
python -m pip install -r backend\requirements-cos.txt
```

如果卡在编译 `crcmod`，在 Windows 上装一下 Visual C++ Build Tools 再重试。

## 一、准备工作（在腾讯云控制台完成）

1. 注册并登录腾讯云，完成个人或企业实名认证。
2. 打开「对象存储 COS」控制台，创建一个存储桶（Bucket）。
   - 记下**地域**，例如广州是 `ap-guangzhou`、上海是 `ap-shanghai`。
   - 记下**桶名**，桶名是全局唯一的，通常形如 `your-name-1250000000`
     （末尾一串数字是你的 APPID，控制台会显示）。
   - 访问权限建议选**私有读写**，下载时由后端签名，不要开公有读。
3. 获取密钥：
   - 进入「访问管理 CAM」→「访问密钥」→「API 密钥管理」。
   - 创建或复制一对 `SecretId` 和 `SecretKey`。
   - **这串 SecretKey 只能自己保管，不要提交到代码仓库或聊天里。**

## 二、配置环境变量

项目读取下面 5 个环境变量。`STORAGE_BACKEND` 默认是 `local`，改成 `cos` 才启用 COS。

| 环境变量 | 含义 | 示例值 |
| --- | --- | --- |
| `STORAGE_BACKEND` | 存储后端开关 | `cos` |
| `COS_SECRET_ID` | 密钥 ID | `AKIDxxxxxxxx` |
| `COS_SECRET_KEY` | 密钥 Key | `xxxxxxxx` |
| `COS_REGION` | 桶所在地域 | `ap-guangzhou` |
| `COS_BUCKET` | 桶名 | `your-name-1250000000` |

### PowerShell 临时设置（只对当前窗口生效）

```powershell
$env:STORAGE_BACKEND = "cos"
$env:COS_SECRET_ID = "你的SecretId"
$env:COS_SECRET_KEY = "你的SecretKey"
$env:COS_REGION = "ap-guangzhou"
$env:COS_BUCKET = "你的桶名"
```

### Windows 永久设置（对所有新窗口生效）

```powershell
[Environment]::SetEnvironmentVariable("STORAGE_BACKEND", "cos", "User")
[Environment]::SetEnvironmentVariable("COS_SECRET_ID", "你的SecretId", "User")
[Environment]::SetEnvironmentVariable("COS_SECRET_KEY", "你的SecretKey", "User")
[Environment]::SetEnvironmentVariable("COS_REGION", "ap-guangzhou", "User")
[Environment]::SetEnvironmentVariable("COS_BUCKET", "你的桶名", "User")
```

设置永久变量后需要**重开终端**才会生效。

## 三、安装依赖并验证

在项目的 `.venv` 环境里安装 COS SDK：

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

然后启动后端，上传一个新版本，再下载一次，确认能正常存取：

```powershell
.\.venv\Scripts\python.exe backend\run.py
```

上传成功后，可以在 COS 控制台的桶里看到对应的对象文件。

## 四、注意事项

- **不要把密钥写进代码**：`config.py` 里只读环境变量，没有硬编码密钥。
- **桶建议私有读写**：下载接口会通过后端把文件读出来返回，避免直接暴露公网地址。
- **如果配置了 `STORAGE_BACKEND=cos` 但缺了其它变量**，后端启动时会直接报错提示缺少哪几项，
  这是故意的，避免“看起来配了、实际没切过去”。
- 切回本地存储：把 `STORAGE_BACKEND` 改回 `local`（或直接不设）即可。
- 目前数据库仍是 SQLite，只适合单机或开发环境；将来要多实例部署，需要再切 PostgreSQL。
