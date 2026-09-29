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

## 微信登录补充验收（2026-09-24 接口 / 2026-09-27 浏览器复验）

本期在登录模块上新增了微信扫码登录，验收分两段：接口行为用 pytest 核对（2026-09-27 复跑：`83 passed`，其中微信登录 60 个），页面渲染和浏览器交互在 2026-09-27 补做，记录见本节末尾。

| 编号 | 页面/流程 | 验收标准 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
| W-01 | 登录页微信入口 | 按后端模式显示入口：`live` 显示「微信扫码登录」、`mock` 显示「模拟微信扫码登录」、`disabled` 显示未开启 | ✅ 接口通过 / ✅ 浏览器复验 | `GET /api/auth/wechat/config` 在未配置 `WECHAT_APP_ID` 时返回 `mode=mock`；浏览器里登录页渲染出「模拟微信扫码登录」按钮和演示模式提示（复验步骤 1） |
| W-02 | 模拟扫码登录 | 演示模式下点按钮完成登录；同一个 openid 再登录还是同一个账号 | ✅ 接口通过 / ✅ 浏览器复验 | `test_mock_login_creates_wechat_only_account`、`test_mock_login_reuses_user_for_same_openid`；浏览器里两次点按钮都进到同一个 `wx_a3ed0c2f49`（复验步骤 5、6） |
| W-03 | 真实扫码链路 | 授权地址带 appid / scope / state；回调校验 state、换 openid、跳结果页；state 不能重放 | ✅ 接口通过（微信接口用 monkeypatch 模拟）/ ✅ 结果页渲染复验 / ⏳ 真实微信号未走通（见 W-06） | `test_authorize_url_contains_appid_and_state`、`test_callback_creates_user_and_logs_in`、`test_callback_redirects_browser_to_result_page`、`test_callback_state_cannot_be_reused`；浏览器里失败结果页与成功跳转都验证过（复验步骤 7、8） |
| W-04 | 绑定与解绑 | 微信可绑到已有工号（权限不变）；一个微信不能绑两个账号；微信建号禁止解绑 | ✅ 接口通过 / ✅ 浏览器复验 | `test_mock_bind_links_wechat_to_current_account`、`test_one_wechat_cannot_bind_two_accounts`、`test_unbind_removes_wechat_binding`、`test_wechat_created_account_cannot_unbind`；浏览器里绑定、占用报错、解绑、微信建号无解绑入口全部走通，且权限仍是教师（复验步骤 2 ~ 5） |
| W-05 | 数据库迁移 | `users` 新增微信字段可升级可回滚 | ✅ 通过 | 用临时库执行 `upgrade` → 三个字段和唯一索引 `ix_users_wechat_openid` 到位 → `downgrade -1` → 字段移除 → 再 `upgrade` 成功 |
| W-06 | 免费测试号真机联调 | 用公众平台接口测试号完成一次真实网页授权（openid 来自微信） | ⏸ 暂停（本期按演示模式交付） | 代码已就绪：`mp` 模式带 `connect_redirect=1`、微信内同窗口跳转、`ProxyFix` 修正 https 回调、签名 state 兼容无 cookie、事件日志与 `wechat-log` / `wechat-token-test` 排错命令；接口层用假 `requests` 覆盖真实 HTTP 路径。步骤与检查清单见 `docs/wechat-login-guide.md` 第 6 节，搁置原因见 `docs/worklog-2026-09-27.md` |

### 浏览器复验记录（2026-09-27，演示模式）

启动真实后端（`.\.venv\Scripts\python.exe -m flask --app backend\run.py run --port 5000 --no-reload`）后，在浏览器里逐页走查，实测结果如下。

| 步骤 | 操作 | 实际结果 |
| --- | --- | --- |
| 1 | 打开 `documents/index.html` | 微信入口按 `mode=mock` 渲染为「模拟微信扫码登录」，旁边是「未配置 WECHAT_APP_ID / WECHAT_APP_SECRET，使用本地模拟微信登录」，下方还有可展开的「模拟参数」 |
| 2 | `teacher / teacher123` 登录 → 账号设置 → 绑定微信 | 提示「已绑定演示微信（mock_openid_demo）」；「登录方式」由「工号密码」变为「微信 + 工号密码」，「微信绑定」变为「已绑定」，顶栏出现「微信」标记，按钮变为「解绑微信」 |
| 3 | `admin` 登录 → 账号设置 → 绑定微信（同一个微信） | 页面顶部提示「该微信已经绑定了其他账号，请先在原账号解绑」，账号仍是「未绑定」，按钮恢复可点 |
| 4 | `teacher` 登录 → 账号设置 → 解绑微信 | 弹出确认框「确定解绑微信吗？解绑后需要用工号密码登录。」，确认后提示「已解绑微信」，文案与顶栏「微信」标记同步回退 |
| 5 | 登录页点「模拟微信扫码登录」 | 登录成功并跳到分类页；账号设置为新建的 `wx_a3ed0c2f49`，「工号」是 `wx_...`、「登录方式」是「仅微信」，微信绑定卡片显示「该账号由微信创建，解绑后将无法登录，因此不提供解绑。」，页面上没有解绑按钮 |
| 6 | 退出后再次点「模拟微信扫码登录」 | 仍登录到同一个 `wx_a3ed0c2f49`，账号被复用，没有重复建号 |
| 7 | 直接打开 `wechat-callback.html?wechat=error&message=...&error=40029` | 结果页渲染出失败文案、「错误码：40029」、「复制错误信息」和「返回登录」按钮，以及 `flask --app backend\run.py wechat-log` 排查提示 |
| 8 | 直接打开 `wechat-callback.html`（不带参数） | 自动跳转到 `categories.html` |

第 2 ~ 6 步覆盖的是演示模式下的真实页面链路；第 7、8 步覆盖的是结果页自身，失败分支以前只有接口层证据。**还没覆盖的**是「配好真实 `WECHAT_APP_ID` 后拿真实微信走一次授权」，这段属于 W-06，仍然暂停。

## 本次验收发现并修复的问题

| 问题 | 现象 | 原因 | 处理 |
| --- | --- | --- | --- |
| 详情页 JavaScript 报错 | 打开 `document-detail.html?id=1` 只显示一条错误信息「document.getElementById is not a function」，页面内容完全不渲染 | `prototype/documents/app.js` 里用 `const document = await apiRequest(...)` 接后端数据，遮蔽了浏览器的全局 `document`，后面的 `document.getElementById(...)` 因此调用失败 | 把详情、上传、历史、下载四个函数里的局部变量改名为 `doc`，不再遮蔽全局 `document`。修复后四个页面全部正常渲染 |
| 微信结果页里的命令显示成乱码 | 结果页底部提示显示成 `flask --app backend un.py wechat-log`，路径像是被截断了 | 同一处提示写在 `app.js` 的模板字符串里，`backend\run.py` 里的 `\r` 被 JavaScript 当成回车转义符，输出了换行 | 改写成 `backend\\run.py`，模板字符串里输出一个反斜杠。2026-09-27 浏览器复验时发现并修复，修复后页面显示 `flask --app backend\run.py wechat-log` |

这个 bug 在 2026-09-15 的检查中没有被发现，当时只确认了页面能返回 200，没有真正执行页面里的 JavaScript。

微信结果页那个 bug 同理：接口测试看不到模板字符串里的转义问题，只有把页面真正渲染出来读一遍文案才会发现。

## 剩余走查补充（2026-09-28）

上一版留下的三项走查已经补做。执行方式是「无头 Chromium 驱动真实页面 + 真实 Flask 后端」：后端跑在**临时数据库 + 临时上传目录**上（`127.0.0.1:5055`），没有读写开发库 `backend/instance/doc_collab.db`，也没有改动仓库里的任何文件。账号仍是 `admin` / `teacher` / `viewer`。

### 1. 上传页的文件选择

| 步骤 | 操作 | 实际结果 |
| --- | --- | --- |
| 1 | `teacher` 登录后进 `upload-version.html?id=1` | 标题显示「2026级计算机科学与技术专业培养计划」，文件框、变更说明、提交按钮齐全 |
| 2 | 不选文件直接点「上传并生成新版本」 | 被浏览器原生校验拦住，提示 `Please select a file.`（语言跟随浏览器）。页面里那句 `alert("请选择文件")` 走不到，因为 `<input type="file" required>` 会先拦下 |
| 3 | 选一个 `.png` 提交 | 弹窗「不支持的文件类型」，停在原页面，没有生成版本 ✅ |
| 4 | 选一个 `.txt` 并填变更说明后提交 | 上传成功，跳回详情页，当前版本 v1 → v2，历史里多一条记录 ✅ |
| 5 | 选一个 51 MB 的 `.txt` 提交 | 弹窗「请求失败（413）」，停在原页面，提示不可读 ❌ |
| 6 | 用鼠标打开系统文件选择框本身 | 自动化不弹系统对话框，仍需人工点一次确认（约 1 分钟） |

### 2. 微信建号后用工号密码登录

| 步骤 | 操作 | 实际结果 |
| --- | --- | --- |
| 1 | 登录页点「模拟微信扫码登录」 | 建号成功并进入分类页 |
| 2 | 账号设置页读工号 | `wx_a3ed0c2f49` |
| 3 | 退出后用该工号 + 任意密码登录 | 登录被拒（服务端 401），页面停在登录页，但提示文案是「请先登录」而不是「用户名或密码错误」❌ |

### 3. 文档列表的筛选与状态徽标

| 步骤 | 操作 | 实际结果 |
| --- | --- | --- |
| 1 | 管理员进 `documents.html` | 3 篇文档，状态列分别是 正常 / 归档 / 废弃 |
| 2 | 点开分类筛选 | 菜单展开，6 个选项（全部分类 + 5 个分类） |
| 3 | 输入「教学」后按 ↓ 再回车 | 选中「教学大纲」，URL 带 `?category_id=2`，列表显示空状态「该分类暂无文档」✅ |
| 4 | 再选回「全部分类」 | 列表恢复 3 行；URL 变成 `documents.html?`（多一个空问号） |
| 5 | 读三个状态徽标的计算样式 | 正常 `rgb(31,68,115)` / `rgb(230,240,251)`；归档 `rgb(71,85,105)` / `rgb(241,245,249)`；废弃 `rgb(153,27,27)` / `rgb(254,226,226)`，与 `styles.css` 一致 ✅ |

### 这轮走查发现的问题

| # | 问题 | 现象 | 原因 | 影响 | 处理建议 |
| --- | --- | --- | --- | --- | --- |
| 1 | 登录失败提示文案不对 | 密码错误、微信建号用工号密码登录，页面都提示「请先登录」 | `prototype/documents/app.js` 的 `apiRequest` 里 `response.status === 401` 时无条件抛 `new Error("请先登录")`；登录接口传的 `redirectOn401: false` 只挡住了跳转，没让服务端文案透出来 | 与 `business-walkthrough.md` 第 5.1 节要求的「用户名或密码错误」不符，老师会误以为是会话问题 | 401 分支优先用服务端返回的 `error.message`，取不到再回落到「请先登录」；补一条断言登录失败文案的测试 |
| 2 | 超过 50 MB 的提示不可读 | 弹窗「请求失败（413）」 | Flask 的 `MAX_CONTENT_LENGTH` 超限时返回 HTML 错误页，`apiRequest` 拿不到 JSON，只能拼状态码 | 需求要求「超过 50 MB 时给出错误提示」，这条目前不达验收标准；新建文档页共用同一套逻辑，问题相同 | 后端把 413（以及文件类型错误）统一转成 JSON 错误，前端提示「文件超过 50 MB，请压缩后再上传」 |
| 3 | 切回「全部分类」后 URL 留一个 `?` | URL 变成 `documents.html?` | `window.location.search = ""` | 只影响观感和复制出来的链接，功能正常 | 改成 `window.location.href = window.location.pathname` |
| 4 | 文件选择框没有类型过滤 | 选文件时能看到所有类型，选错要到提交后才知道 | `#file` 没有 `accept` 属性 | 体验问题，容易误选 | 给 `#file` 加 `accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt"`；服务端校验仍然保留 |

第 1、2 条影响验收结论，第 3、4 条属于体验优化，四条已一并修复，见下节。

### 修复与复验（2026-09-28）

| # | 改了什么 | 涉及文件 | 复验结果 |
| --- | --- | --- | --- |
| 1 | `apiRequest` 改成先解析响应体再判断状态码，401 时优先使用服务端文案 | `prototype/documents/app.js` | 密码错误提示「用户名或密码错误」；微信建号 `wx_a3ed0c2f49` 用工号密码登录同样提示「用户名或密码错误」；未登录访问受保护页面仍正常跳登录页 |
| 2 | 新增 413 处理，把 Flask 默认的 HTML 错误页统一成 JSON（`file_too_large`），上限文案由 `MAX_CONTENT_LENGTH` 换算 | `backend/app/__init__.py`、`backend/app/utils.py` | 传 51 MB 文件提示「上传文件超过 50 MB 上限，请压缩后再上传」；`.png` 仍提示「不支持的文件类型」；`.txt` 正常上传，版本 v1 → v2 |
| 3 | 切回「全部分类」时改用 `pathname` 拼查询串 | `prototype/documents/app.js` | 选回全部分类后 URL 就是 `documents.html`，没有多余的 `?`，列表恢复全部文档 |
| 4 | 文件框加 `accept` 类型过滤，与后端允许的扩展名一致 | `prototype/documents/app.js`（上传页与新建文档页共用） | 文件框 `accept` 为 `.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt` |

回归验证记录：

| 验证项 | 命令 / 方式 | 结果 |
| --- | --- | --- |
| 后端全量测试 | `.\.venv\Scripts\python.exe -m pytest backend\tests -q` | `85 passed`（新增 2 个：413 可读文案、上限换算） |
| 前端脚本语法 | `node --check prototype\documents\app.js` | 通过 |
| 浏览器流程复验 | 无头 Chromium：登录失败文案 / 列表筛选 / 上传（超限、格式、正常）/ 微信建号 / 未登录跳转 | 10 项断言全部符合预期 |

### 仍需人工补的一步

用鼠标真实打开一次系统文件选择框（确认弹窗能弹出、能选中文件），约 1 分钟。自动化不会弹系统对话框，这一步替代不了。

## 冻结条件

- 上述 8 项全部通过 ✅
- 页面文案、字段和流程与 `document-module-requirements.md` 一致。
- 原型早期是「纯假数据的静态页面」，当时要求原型里不出现接口细节；现在原型已经接入真实 API，前端会直接调用 `/api/**`，这条要求已不适用，改为「页面不展示数据库字段名和内部错误码等技术细节」。
