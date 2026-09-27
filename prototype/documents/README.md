# 文档管理模块原型（documents）

这是文档管理模块的管理端页面原型，已经接入 Flask API，不再使用假数据。

## 打开顺序

1. `index.html`：登录。
2. `categories.html`：选择文档分类。
3. `documents.html`：查看文档列表。
4. `document-detail.html?id=1`：查看文档详情。
5. `upload-version.html?id=1`：上传新版本。
6. `versions.html?id=1`：查看历史版本。
7. `download.html?id=1&version_id=1`：下载确认。
8. `account.html`：账号设置，绑定 / 解绑微信。

另外 `wechat-callback.html` 是微信授权回跳的中转页，不手写地址进去，扫码后会自动跳到它。

## 演示账号

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `admin123` | 管理员 |
| `teacher` | `teacher123` | 文档负责人 |
| `viewer` | `viewer123` | 普通教师 |

## 微信登录

登录页有微信入口，默认是「演示模式」（后端没配 `WECHAT_APP_ID`）：点「模拟微信扫码登录」就能进系统，展开「模拟参数」可以改用别的 openid / 昵称，用来演示「第一次扫码是建号、同一个 openid 再登录还是同一个账号」。

配好 `WECHAT_APP_ID` / `WECHAT_APP_SECRET` 后自动切换成真实扫码，说明见 `docs/wechat-login-guide.md`。

想把微信绑到已有的 `teacher` 账号上：先用工号密码登录 → 右上角「账号设置」→「绑定微信」，绑定后扫码登录就是同一个账号，权限和负责的文档都不变。

## 运行方式

先启动 `backend/run.py`，再访问 `http://127.0.0.1:5000/documents/index.html`，或者从原型入口页 `http://127.0.0.1:5000/` 进入。

不要直接双击这些 HTML 文件：`file://` 方式无法调用 Flask API，页面会卡在登录失败。

## 文件说明

| 文件 | 作用 |
| --- | --- |
| `index.html` / `categories.html` / ... | 页面只负责结构，逻辑都在 `app.js` 里按 `data-page` 分发 |
| `account.html` | 账号设置页：账号信息、登录方式、微信绑定与解绑 |
| `wechat-callback.html` | 微信授权回跳中转页，通知原页面后自动关闭或跳转 |
| `app.js` | 页面逻辑：调用 API、渲染列表、处理登录状态和权限提示 |
| `styles.css` | 自己写的样式，不依赖外部 CDN，离线也能正常显示 |
| `mock-data.js` | 早期假数据原型留下的文件，现在没有任何页面加载它，仅作参考保留 |

页面之间的跳转都用相对路径，整个目录可以整体移动，不会因为换了目录而失效。
