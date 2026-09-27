# 文档管理模块原型验收清单

## 说明

原型位于 `prototype/documents/`（入口页是 `prototype/index.html`），已经接入 Flask API。

- 验收时间：2026-09-20
- 验收方式：启动真实后端（`backend\run.py`），先用 HTTP 请求逐条核对接口行为，再在浏览器里用三个账号（`admin` / `teacher` / `viewer`）走页面流程。

同级的 `prototype/taskman/` 是另一份独立原型，已从原型入口页撤下，不属于本模块的验收范围。

## 验收结果

| 编号 | 页面/流程 | 验收标准 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
| P-01 | 登录页 | 工号密码调用真实登录接口，成功后进入分类列表 | ✅ 通过 | 未登录 `/api/auth/me` = 401；错误密码 = 401；`admin` 正确登录 = 200，`/me` 返回 `role=admin`；浏览器里登录 `viewer` 后自动跳到 `categories.html` |
| P-02 | 分类列表 | 展示默认分类和文档数量，可点击进入文档列表 | ✅ 通过 | `GET /api/categories` = 200，返回 5 个默认分类，`document_count` 正确（专业培养计划 1 篇、其余 0）；页面渲染 5 张分类卡片 |
| P-03 | 文档列表 | 可按分类筛选，显示标题/负责人/版本/时间 | ✅ 通过 | `GET /api/documents` = 200（1 篇），`?category_id=1` 筛选 = 200 返回 1 条；页面表格显示「标题 ｜ 分类 ｜ 负责人 ｜ 当前版本 v2 ｜ 更新时间」，筛选下拉 6 个选项 |
| P-04 | 文档详情 | 展示当前版本，下载/上传/历史入口清晰 | ✅ 通过 | 负责人 `teacher` 看到「下载当前版本 / 上传新版本 / 查看历史版本」三个入口；页面显示标题、分类、负责人、当前版本 v2、最近更新时间 |
| P-05 | 上传新版本 | 可选择文件、填写变更说明，提交后出现新版本 | ✅ 通过 | `POST /api/documents/1/versions`（multipart）= 201，版本号 v1 → v2，上传人自动记为当前用户、时间自动记录；上传页表单与「返回详情」链接渲染正常 |
| P-06 | 历史版本 | 版本倒序展示，包含上传人和时间 | ✅ 通过 | `GET /api/documents/1/versions` = 200，顺序 v2 > v1，每条含文件名、变更说明、上传人、上传时间；历史版本页渲染两张版本卡片 |
| P-07 | 下载确认 | 下载前有确认提示，确认后调用真实下载接口 | ✅ 通过 | 下载接口 = 200，返回 31 字节，SHA256 与上传文件一致，响应头 `Content-Disposition: attachment; filename=acceptance_check.txt`；未登录下载 = 401；下载确认页显示文件名、版本号、上传人 |
| P-08 | 权限提示 | 非负责人/非管理员看到只读提示，不能上传 | ✅ 通过 | 普通教师上传版本 = 403、建分类 = 403、查看详情与下载 = 200；浏览器里普通教师的详情页显示「你当前为只读权限，不能上传新版本」，且页面上没有上传入口 |

## 微信登录补充验收（2026-09-24）

本期在登录模块上新增了微信扫码登录，验收分两段：接口行为用 pytest 核对（48 个用例全绿，其中微信登录 25 个），页面渲染和浏览器交互需要启动后端再人工走一遍。

| 编号 | 页面/流程 | 验收标准 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
| W-01 | 登录页微信入口 | 按后端模式显示入口：`live` 显示「微信扫码登录」、`mock` 显示「模拟微信扫码登录」、`disabled` 显示未开启 | ✅ 接口通过 / ⏳ 待浏览器复验 | `GET /api/auth/wechat/config` 在未配置 `WECHAT_APP_ID` 时返回 `mode=mock`；`app.js` 的 `initWechatLogin()` 按 mode 分支渲染 |
| W-02 | 模拟扫码登录 | 演示模式下点按钮完成登录；同一个 openid 再登录还是同一个账号 | ✅ 接口通过 / ⏳ 待浏览器复验 | `test_mock_login_creates_wechat_only_account`、`test_mock_login_reuses_user_for_same_openid` |
| W-03 | 真实扫码链路 | 授权地址带 appid / scope / state；回调校验 state、换 openid、跳结果页；state 不能重放 | ✅ 接口通过（微信接口用 monkeypatch 模拟）/ ⏳ 待真实 AppID 联调 | `test_authorize_url_contains_appid_and_state`、`test_callback_creates_user_and_logs_in`、`test_callback_redirects_browser_to_result_page`、`test_callback_state_cannot_be_reused` |
| W-04 | 绑定与解绑 | 微信可绑到已有工号（权限不变）；一个微信不能绑两个账号；微信建号禁止解绑 | ✅ 接口通过 / ⏳ 待浏览器复验 | `test_mock_bind_links_wechat_to_current_account`、`test_one_wechat_cannot_bind_two_accounts`、`test_unbind_removes_wechat_binding`、`test_wechat_created_account_cannot_unbind` |
| W-05 | 数据库迁移 | `users` 新增微信字段可升级可回滚 | ✅ 通过 | 用临时库执行 `upgrade` → 三个字段和唯一索引 `ix_users_wechat_openid` 到位 → `downgrade -1` → 字段移除 → 再 `upgrade` 成功 |
| W-06 | 免费测试号真机联调 | 用公众平台接口测试号完成一次真实网页授权（openid 来自微信） | ⏸ 暂停（本期按演示模式交付） | 代码已就绪：`mp` 模式带 `connect_redirect=1`、微信内同窗口跳转、`ProxyFix` 修正 https 回调、签名 state 兼容无 cookie、事件日志与 `wechat-log` / `wechat-token-test` 排错命令；接口层用假 `requests` 覆盖真实 HTTP 路径。步骤与检查清单见 `docs/wechat-login-guide.md` 第 6 节，搁置原因见 `docs/worklog-2026-09-27.md` |

浏览器复验步骤（还没做，建议补一次）：

1. 启动后端，打开 `http://127.0.0.1:5000/documents/index.html`，确认微信入口出现并可登录。
2. 用工号密码登录后进「账号设置」，走一遍绑定微信 / 解绑微信，确认「登录方式」「微信绑定」文案和顶部「微信」标记同步变化。
3. 配好真实 `WECHAT_APP_ID` 后用真实微信走一次授权（没有正式应用时用免费测试号，步骤见 `docs/wechat-login-guide.md` 第 6 节），核对回跳地址与结果页提示。

## 本次验收发现并修复的问题

| 问题 | 现象 | 原因 | 处理 |
| --- | --- | --- | --- |
| 详情页 JavaScript 报错 | 打开 `document-detail.html?id=1` 只显示一条错误信息「document.getElementById is not a function」，页面内容完全不渲染 | `prototype/documents/app.js` 里用 `const document = await apiRequest(...)` 接后端数据，遮蔽了浏览器的全局 `document`，后面的 `document.getElementById(...)` 因此调用失败 | 把详情、上传、历史、下载四个函数里的局部变量改名为 `doc`，不再遮蔽全局 `document`。修复后四个页面全部正常渲染 |

这个 bug 在 2026-09-15 的检查中没有被发现，当时只确认了页面能返回 200，没有真正执行页面里的 JavaScript。

## 尚未覆盖的部分

- 上传页的「选择文件」是通过接口层（multipart 上传）验证的，没有驱动浏览器的文件选择框再走一遍。
- 删除文档、修改负责人等操作本期没有接口，也没有对应页面。

## 冻结条件

- 上述 8 项全部通过 ✅
- 页面文案、字段和流程与 `document-module-requirements.md` 一致。
- 原型早期是「纯假数据的静态页面」，当时要求原型里不出现接口细节；现在原型已经接入真实 API，前端会直接调用 `/api/**`，这条要求已不适用，改为「页面不展示数据库字段名和内部错误码等技术细节」。
