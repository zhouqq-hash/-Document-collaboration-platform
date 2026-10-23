# 文档管理模块前后端接口规范

## 通用约定

- Base URL：`/api`。
- 请求和响应默认使用 JSON。
- 文件上传使用 `multipart/form-data`。
- 时间字段使用 ISO 8601 字符串。
- 单个上传文件大小上限：50 MB。
- 超过 50 MB 时返回 413 `file_too_large`，message 形如「上传文件超过 50 MB 上限，请压缩后再上传」；文件类型不在允许范围时返回 400 `invalid_file`，message 为「不支持的文件类型」。

## 通用响应格式

成功：

```json
{ "data": {} }
```

失败：

```json
{ "error": { "code": "permission_denied", "message": "没有权限执行此操作" } }
```

常见 HTTP 状态码：200、201、204、400、401、403、404、409、413。

## 认证接口

### POST /api/auth/login

请求：

```json
{ "username": "admin", "password": "admin123" }
```

响应：

```json
{
  "data": {
    "id": 1,
    "username": "admin",
    "name": "管理员",
    "role": "admin"
  }
}
```

### POST /api/auth/logout

返回 204。

### GET /api/auth/me

返回当前登录用户，未登录返回 401：

```json
{
  "data": {
    "id": 2,
    "username": "teacher",
    "name": "胡军成",
    "role": "teacher",
    "wechat_bound": false,
    "password_login": true,
    "avatar_url": ""
  }
}
```

用户对象字段说明：

- `wechat_bound`：是否已绑定微信。
- `password_login`：是否可以用工号密码登录；微信扫码自动创建的账号为 `false`。
- `avatar_url`：微信头像地址，未绑定时为空字符串。

## 微信登录接口

微信登录的运行模式由服务端配置决定，前端先用 `config` 接口判断该显示哪条入口：

| 模式 | 触发条件 | 说明 |
| --- | --- | --- |
| `live` | 配好 `WECHAT_APP_ID` 和 `WECHAT_APP_SECRET` | 真实扫码登录，服务端会请求微信官方接口 |
| `mock` | 没配应用信息（默认） | 演示模式，用模拟登录跑通流程，不联网 |
| `disabled` | 设了 `WECHAT_MOCK_ENABLED=0` 且没配应用信息 | 前端不展示微信登录入口 |

### GET /api/auth/wechat/config

公开接口，不需要登录。

```json
{
  "data": {
    "mode": "mock",
    "configured": false,
    "app_id": "",
    "authorize_mode": "open",
    "hint": "演示模式：未配置 WECHAT_APP_ID / WECHAT_APP_SECRET，使用本地模拟微信登录",
    "mock": { "enabled": true, "openid": "mock_openid_demo", "nickname": "微信演示用户" }
  }
}
```

### GET /api/auth/wechat/authorize-url

公开接口。已登录用户带 `?bind=1` 时，这次扫码用于绑定当前账号而不是切换身份。

```json
{
  "data": {
    "authorize_url": "https://open.weixin.qq.com/connect/qrconnect?appid=...&state=...#wechat_redirect",
    "state": "签名令牌（itsdangerous，默认 10 分钟有效），同时存进 session 做一次性校验",
    "redirect_uri": "https://doc.example.edu.cn/api/auth/wechat/callback",
    "bind": false
  }
}
```

演示模式下该接口返回 400 `wechat_not_configured`（演示登录请用 `mock-login`）。

### GET /api/auth/wechat/callback

微信授权回跳地址，参数 `code`、`state`。

- 浏览器访问：302 跳转到 `WECHAT_RESULT_REDIRECT`（默认 `/documents/wechat-callback.html`），并把结果拼在查询串上：`?wechat=success` 或 `?wechat=error&message=失败原因`。
- 带 `?format=json` 时直接返回 JSON，成功返回用户对象，失败返回错误。

可能的错误码：`wechat_cancelled`（用户取消）、`wechat_invalid_state`（state 不匹配或已使用）、`wechat_api_error`（微信接口报错，502）、`wechat_already_bound`（该微信已绑定其他账号，409）、`account_already_bound`（当前账号已绑定其他微信，409）。

### POST /api/auth/wechat/mock-login

仅演示模式可用，真实模式返回 403 `wechat_mock_disabled`。请求体字段都可选：

```json
{ "openid": "mock_openid_demo", "nickname": "微信演示用户" }
```

成功返回用户对象并建立登录会话。`openid` 只允许字母、数字、下划线和短横线，长度 4～64，否则返回 400 `invalid_openid`。

### POST /api/auth/wechat/bind

需要登录。把微信绑定到当前账号，不改变当前登录身份。

- 真实模式请求体：`{ "code": "微信授权码", "state": "授权时返回的 state" }`
- 演示模式请求体：`{ "openid": "...", "nickname": "..." }`

成功返回用户对象；`409` 表示冲突（`wechat_already_bound` / `account_already_bound`）。

### POST /api/auth/wechat/unbind

需要登录。解绑成功返回 204。

- 未绑定：409 `wechat_not_bound`。
- 微信自动创建且没有密码的账号：409 `wechat_unbind_not_allowed`，避免解绑后无法登录。

## 分类接口

### GET /api/categories

返回分类列表，包含每个分类的文档数量和 AI 预审模板：
`review_template_key`、`review_template_name`、`review_template_version`。

### GET /api/review-templates

仅管理员。返回可用模板的 key、名称、版本、说明和规则数量。目前提供：

- `generic_document_v1`：通用文档质量检查，4项；
- `syllabus_v1`：教学大纲规范检查，10项。

### POST /api/categories

仅管理员。请求：

```json
{
  "name": "新分类",
  "sort_order": 10,
  "review_template_key": "generic_document_v1"
}
```

### PATCH /api/categories/{id}

仅管理员。修改分类名称或排序，字段可选：

```json
{
  "name": "新名称",
  "sort_order": 5,
  "review_template_key": "syllabus_v1"
}
```

`review_template_key` 不存在时返回 400 `invalid_template`。未显式指定的新分类使用
`generic_document_v1`，不会让 AI 自由生成检查规则。

### DELETE /api/categories/{id}

仅管理员。分类下仍有文档时返回 409，不能删除。

## 用户接口

### GET /api/users

仅管理员。返回用户列表，供新建文档时选择负责人：

```json
{
  "data": [
    { "id": 1, "username": "admin", "name": "管理员", "role": "admin" }
  ]
}
```

## 文档接口

### GET /api/documents?category_id=1&status=active

返回文档列表，可按分类和状态筛选。状态取值：`active`（正常）、`archived`（归档）、`deprecated`（废弃）。

### POST /api/documents

仅管理员，创建文档并上传首个版本。使用 multipart：

```text
title, category_id, owner_id, description, changelog, file
```

`title` 最多 200 字，`description` / `changelog` 最多 500 字，`file` 必须有且符合文档模块的类型和 50 MB 限制。文档记录与 v1 在同一事务中创建，文件校验失败不会留下空文档。

### GET /api/documents/{id}

返回文档详情、当前版本和 `review_state` 预审工作流摘要。`review_state.code`
取值如下：

- `unreviewed`：当前版本未预审；
- `reviewing`：预审排队或执行中；
- `awaiting_confirmation`：AI 预审完成，等待负责人确认；
- `changes_required`：负责人已退回，需要修改后重新提交；
- `resubmitted`：新版本已提交，等待以上次退回问题为基准复审；
- `approved`：当前版本已由负责人确认通过；
- `review_unavailable` / `review_failed`：预审未执行或执行失败。

`review_state` 还包含 `version_id`、`review_id`、`note`、`error` 和
`previous_review_id`，前端据此显示明确待办。

### PATCH /api/documents/{id}

仅管理员。修改文档信息、负责人或状态，字段均可选：

```json
{
  "title": "新标题",
  "category_id": 2,
  "owner_id": 3,
  "status": "archived",
  "description": "新说明"
}
```

## 版本接口

### GET /api/documents/{id}/versions

返回该文档全部版本，按版本号倒序。每个版本带 `review` 摘要；
负责人确认通过后，`review.human_decision` 为 `pass`，版本历史会显示
“已通过负责人确认”。退回版本则为 `return`。

### POST /api/documents/{id}/versions

仅管理员或文档负责人。使用 multipart：

```text
changelog, file
```

成功返回新版本对象，版本号自动递增。

### GET /api/documents/{id}/versions/{version_id}/download

下载指定版本文件，返回文件流。

### POST /api/documents/{id}/versions/{version_id}/rollback

仅管理员或文档负责人。把指定历史版本复制成一个新版本，版本号继续递增、历史不被覆盖，
新版本的 `changelog` 为「回滚到版本 N」。成功返回 201 和新版本对象。

## 权限映射

| 接口 | 管理员 | 文档负责人 | 普通教师 |
| --- | --- | --- | --- |
| 微信登录相关接口（`/api/auth/wechat/config`、`authorize-url`、`callback`、`mock-login`） | 公开 | 公开 | 公开 |
| POST /api/auth/wechat/bind | 允许 | 允许 | 允许 |
| POST /api/auth/wechat/unbind | 允许 | 允许 | 允许 |
| GET /api/categories | 允许 | 允许 | 允许 |
| POST /api/categories | 允许 | 403 | 403 |
| PATCH /api/categories/{id} | 允许 | 403 | 403 |
| DELETE /api/categories/{id} | 允许 | 403 | 403 |
| GET /api/users | 允许 | 403 | 403 |
| GET /api/documents | 允许 | 允许 | 允许 |
| POST /api/documents | 允许 | 403 | 403 |
| PATCH /api/documents/{id} | 允许 | 403 | 403 |
| POST /api/documents/{id}/versions | 允许 | 允许（仅本人负责） | 403 |
| POST /api/documents/{id}/versions/{version_id}/rollback | 允许 | 允许（仅本人负责） | 403 |
| GET 版本/下载 | 允许 | 允许 | 允许 |

## 问答接口

Base URL 仍是 `/api`，问答接口统一挂在 `/api/qa` 前缀下。所有接口都需要登录，未登录返回 401。

### GET /api/qa/topics

返回话题列表，默认按最近活跃时间倒序。可选查询参数：

- `status=open|closed`：按状态筛选；
- `category_id=<id>`：按分类筛选；`category_id=none` 只看未分类；
- `document_id=<id>`：只返回关联到该文档的话题；
- `q=<关键词>`：搜索标题、说明或任意发言内容；
- `sort=latest|created`：`latest` 最近活跃（默认），`created` 最新发起；
- `page` / `page_size`：分页，默认第 1 页、每页 20 条，`page_size` 上限 100（超限按 100 处理，非法 `page` 回落到第 1 页）。

`status` 只接受 `open` / `closed`，其他值返回 400 `invalid_status`。分页信息在 `data` 里一并返回，列表项在 `items` 中（含 `category`、`document`、`version`，未设置时为 `null`）：

```json
{
  "data": {
    "items": [
      {
      "id": 1,
      "title": "毕业设计要求是否增加中期检查",
      "description": "讨论是否在毕业设计过程中增加一次中期检查。",
      "status": "open",
      "category": { "id": 3, "name": "毕业设计" },
      "document": { "id": 3, "title": "2025-2026学年课程考核分析报告", "status": "deprecated" },
      "version": { "id": 5, "version_number": 1, "filename": "考核分析报告_v1.txt" },
      "creator": { "id": 1, "username": "admin", "name": "管理员", "role": "admin" },
      "created_at": "2026-10-12T02:00:00+00:00",
      "updated_at": "2026-10-12T02:05:00+00:00",
      "statement_count": 3,
      "speaker_count": 2,
      "latest_statement_at": "2026-10-12T02:05:00+00:00"
      }
    ],
    "total": 12,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

### POST /api/qa/topics

任何已登录用户。请求：

```json
{ "title": "话题标题", "description": "话题说明（可选）", "category_id": 3, "document_id": 3, "version_id": 5, "ends_at": "2026-12-31T23:59:59Z" }
```

`category_id` 可选，话题所属分类的 id；分类不存在返回 404 `category_not_found`。`document_id` / `version_id` 可选，用于关联文档及其版本；文档不存在返回 404 `document_not_found`，版本不存在返回 404 `version_not_found`，版本不属于所选文档返回 400 `version_mismatch`；只传 `version_id` 时自动推导所属文档。`ends_at` 可选，是定时结束时间（ISO 8601），必须是未来时间；不填则不自动结束。成功返回 201 和话题详情。标题为空返回 400 `invalid_title`；说明超长返回 400 `invalid_description`；结束时间格式错误或不是未来时间返回 400 `invalid_ends_at`。

### GET /api/qa/topics/{id}

返回话题详情，包含时间线（升序）和意见汇总：

```json
{
  "data": {
    "id": 1,
    "title": "毕业设计要求是否增加中期检查",
    "status": "open",
    "category": { "id": 3, "name": "毕业设计" },
    "document": { "id": 3, "title": "2025-2026学年课程考核分析报告", "status": "deprecated" },
    "version": { "id": 5, "version_number": 1, "filename": "考核分析报告_v1.txt" },
    "ai_summary": {
      "text": "## 讨论概况\n...",
      "generated_at": "2026-10-16T07:30:00+00:00",
      "stale": false
    },
    "conclusion": {
      "text": "经讨论决定：提交截止时间提前到第 16 周。",
      "by": { "id": 2, "username": "teacher", "name": "胡军成", "role": "teacher" },
      "at": "2026-10-16T08:08:00+00:00",
      "shared": true
    },
    "ends_at": null,
    "expired": false,
    "creator": { "id": 1, "username": "admin", "name": "管理员", "role": "admin" },
    "statements": [
      {
        "id": 1,
        "topic_id": 1,
        "content": "建议增加，能提前发现问题。",
        "position": "agree",
        "author": { "id": 2, "username": "teacher", "name": "胡军成", "role": "teacher" },
        "created_at": "2026-10-12T02:01:00+00:00",
        "hidden": false,
        "hidden_by": null,
        "hidden_at": null,
        "hidden_reason": "",
        "parent_id": null,
        "quote_statement_id": null,
        "parent": null,
        "quoted": null
      }
    ],
    "summary": {
      "topic_id": 1,
      "statement_count": 3,
      "speaker_count": 2,
      "positions": { "agree": 3, "disagree": 0, "neutral": 0 },
      "dominant_position": "agree",
      "dominant_count": 3,
      "consensus_reached": true,
      "consensus_position": "agree",
      "summary_text": "初步统一意见：赞成（3/3）",
      "latest_statement_at": "2026-10-12T02:05:00+00:00"
    }
  }
}
```

### GET /api/qa/topics/{id}/summary

只返回话题的意见汇总对象（与详情里的 `summary` 相同），便于单独轮询汇总结果。

### POST /api/qa/topics/{id}/statements

任何已登录用户。请求：

```json
{ "content": "发言内容", "position": "agree", "parent_id": 1, "quote_statement_id": 1 }
```

- `content` 必填且 ≤ 2000 字，否则 400 `invalid_content`。
- `position` 可选，取值 `agree` / `disagree` / `neutral`，不填默认 `neutral`，非法值返回 400 `invalid_position`。
- `parent_id` 可选，表示回复同话题下某条发言；发言不存在或不属于本话题返回 404 `statement_not_found`，参数格式错误返回 400 `invalid_parent`。
- `quote_statement_id` 可选，表示引用同话题下某条发言；只给引用对象而未给回复对象时，自动把被引用发言作为回复对象。校验规则同 `parent_id`。
- 话题已结束时返回 409 `topic_closed`。

成功返回 201 和新发言对象，对象含 `parent_id`、`quote_statement_id`、`parent`、`quoted` 字段（未回复/引用时为 `null`）。

### PATCH /api/qa/topics/{id}/statements/{statement_id}

仅管理员。隐藏（软删除）或恢复某条发言。请求：

```json
{ "hidden": true, "reason": "跑题" }
```

- 其他人调用返回 403 `permission_denied`；
- `hidden` 必填，缺失返回 400 `invalid_hidden`；`reason` 可选且 ≤ 200 字，超长返回 400 `invalid_reason`；
- 重复隐藏返回 409 `already_hidden`，重复恢复返回 409 `not_hidden`；
- 话题不存在、发言不存在或发言不属于该话题，统一返回 404。

成功返回 200 和被隐藏/恢复的发言对象（含 `hidden`、`hidden_by`、`hidden_at`、`hidden_reason`）。隐藏是软删除：普通用户的时间线里不再出现，也不参与规则汇总、AI 摘要和导出；管理员仍能看到原文与操作记录，并可恢复。发言依然不可编辑。

### PATCH /api/qa/topics/{id}

仅管理员或话题发起人。请求：

```json
{ "status": "closed", "ends_at": "2026-12-31T23:59:59Z", "category_id": 3, "document_id": 3, "version_id": 5 }
```

字段均可选：`status` 取值 `open` / `closed`，非法值返回 400 `invalid_status`；`ends_at` 设为 ISO 8601 未来时间可定时结束，设为 `null` 可清除定时；`category_id` 设为分类 id 可调整分类，设为 `null` 可清除分类；`document_id` / `version_id` 可调整或解除文档关联，`document_id` 设为 `null` 会同时清除版本关联。结束时间格式错误或不是未来时间返回 400 `invalid_ends_at`；分类不存在返回 404 `category_not_found`；文档或版本不存在分别返回 404 `document_not_found` / `version_not_found`，版本与文档不匹配返回 400 `version_mismatch`。其他人操作返回 403 `permission_denied`。

### POST /api/qa/topics/{id}/ai-summary

任何已登录用户。按需生成话题的 AI 决策摘要，请求体为空。

- 未配置 `COSMOS_API_KEY` 返回 503 `ai_not_configured`；
- 话题还没有发言返回 400 `no_statements`；
- 调用模型失败返回 502 `ai_failed`，`message` 是可以直接展示的中文原因。

成功返回 200：

```json
{
  "data": {
    "topic_id": 2,
    "summary_text": "## 讨论概况\n...",
    "statement_count": 6,
    "generated_at": "2026-10-16T07:30:00+00:00",
    "stale": false
  }
}
```

说明：摘要会落库到话题上，成功后再打开话题详情可直接从 `ai_summary` 字段读取；重复调用（即「重新生成」）会重新请求模型并覆盖旧内容。`stale` 表示摘要生成之后又有新发言。「是否达成统一意见」的结论始终来自 `GET /api/qa/topics/{id}/summary` 的规则汇总。

### GET /api/qa/topics/{id}/export

任何已登录用户。导出话题讨论为 Markdown 文件，响应带 `Content-Disposition: attachment`，文件名形如 `话题-2-课程考核分析报告的提交时间是否调整.md`。

内容依次为：话题信息、`## 意见汇总（规则）`、`## AI 决策摘要`（未生成时写「（未生成）」）、`## 讨论时间线`（每条发言标注发言人与立场，回复与引用会额外标注被回复/被引用的人）。

### POST /api/qa/topics/{id}/conclusion

仅管理员或话题发起人。补录（或覆盖）话题的最终结论/决议。请求：

```json
{ "text": "经讨论决定：提交截止时间提前到第 16 周。", "share_to_document": true }
```

- `text` 必填且 ≤ 2000 字，否则 400 `invalid_conclusion`；
- `share_to_document` 可选，为 `true` 时把结论回写到关联文档；话题没有关联文档返回 400 `no_linked_document`；
- 其他人操作返回 403 `permission_denied`。

成功返回 200 与新的结论对象（含 `text`、`by`、`at`、`shared`）。重新调用会覆盖上一条结论。

### GET /api/qa/decisions?document_id={id}

任何已登录用户。返回回写到该文档的最终结论，按记录时间倒序。缺少 `document_id` 返回 400 `invalid_document`。

```json
{
  "data": [
    {
      "topic_id": 2,
      "topic_title": "课程考核分析报告的提交时间是否调整",
      "status": "open",
      "conclusion": "经讨论决定：提交截止时间提前到第 16 周。",
      "by": { "id": 2, "username": "teacher", "name": "胡军成", "role": "teacher" },
      "at": "2026-10-16T08:08:00+00:00"
    }
  ]
}
```

### GET /api/qa/categories

返回问答话题分类列表，按排序值升序。列表项字段含 `id`、`name`、`sort_order`、`topic_count`、`created_at`。

### POST /api/qa/categories

仅管理员。请求：`{ "name": "分类名称", "sort_order": 0 }`。名称为空返回 400 `invalid_name`；重名返回 409 `name_exists`。成功返回 201。

### PATCH /api/qa/categories/{id}

仅管理员。可修改 `name` 和 `sort_order`，规则同新建；分类不存在返回 404 `category_not_found`。

### DELETE /api/qa/categories/{id}

仅管理员。分类下还有话题时返回 409 `category_has_topics`；成功返回 204。

### POST /api/qa/topics/{id}/statements/{statement_id}/reports

任何已登录用户。举报一条发言。请求：

```json
{ "reason": "这条发言与主题无关，而且带有嘲讽语气。" }
```

- `reason` 必填且 ≤ 500 字，否则 400 `invalid_reason`；
- 不能举报自己的发言（400 `cannot_report_own`），不能举报已隐藏的发言（400 `statement_hidden`）；
- 同一用户对同一条发言重复举报返回 409 `already_reported`；
- 话题或发言不存在返回 404。

成功返回 201 和举报对象。提交后会通知所有管理员（举报人自己除外）。

### GET /api/qa/reports?status=pending

仅管理员。返回举报队列，默认只返回待处理（`pending`），可选 `resolved` / `dismissed` / `all`。每个举报项除自身字段外，还带 `topic_title` 和被举报发言的快照：

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "status": "pending",
        "reason": "这条发言与主题无关。",
        "topic_id": 2,
        "topic_title": "课程考核分析报告的提交时间是否调整",
        "reporter": { "id": 3, "username": "viewer", "name": "王老师", "role": "teacher" },
        "statement": {
          "id": 7,
          "content": "测试123",
          "hidden": false,
          "author": { "id": 1, "username": "admin", "name": "管理员", "role": "admin" }
        },
        "created_at": "2026-10-16T08:59:32+00:00",
        "handled_by": null,
        "handled_at": null
      }
    ],
    "pending": 1
  }
}
```

非管理员返回 403 `permission_denied`。

### PATCH /api/qa/reports/{report_id}

仅管理员。处理一条举报。请求：

```json
{ "action": "hide" }
```

- `action` 取值 `hide`（隐藏该发言并结案）或 `dismiss`（驳回举报），其他值返回 400 `invalid_action`；
- 举报不存在返回 404，已经处理过返回 409 `report_handled`；
- 可附带 `reason`（≤ 200 字）作为隐藏原因，不填则用举报理由。

处理结果会自动发站内通知：`hide` 会通知举报人（`report_resolved`）和被隐藏发言的作者（`statement_hidden`）；`dismiss` 通知举报人（`report_dismissed`）。

### GET /api/qa/notifications?limit=30

任何已登录用户。返回自己的通知（按时间倒序，默认 30 条，最多 100）和未读数：

```json
{ "data": { "items": [ { "id": 1, "kind": "report_resolved", "message": "...", "read": false, "topic_id": 2, "created_at": "..." } ], "unread": 1 } }
```

### GET /api/qa/notifications/unread-count

任何已登录用户。返回 `{"unread": 1, "pending_reports": 0}`，供顶栏徽标使用；`pending_reports` 只对管理员有意义，非管理员恒为 0。

### POST /api/qa/notifications/read

任何已登录用户。把自己的通知标记为已读：不带参数表示全部标记；传 `{"ids": [1, 2]}` 只标记指定通知。返回 `{"updated": 2}`。

## 问答权限映射

| 接口 | 管理员 | 话题发起人 | 其他教师 |
| --- | --- | --- | --- |
| GET /api/qa/topics | 允许 | 允许 | 允许 |
| POST /api/qa/topics | 允许 | 允许 | 允许 |
| GET /api/qa/topics/{id} | 允许 | 允许 | 允许 |
| GET /api/qa/topics/{id}/summary | 允许 | 允许 | 允许 |
| POST /api/qa/topics/{id}/statements | 允许（话题未结束时） | 允许（话题未结束时） | 允许（话题未结束时） |
| PATCH /api/qa/topics/{id} | 允许 | 允许 | 403 |
| GET /api/qa/categories | 允许 | 允许 | 允许 |
| POST /api/qa/topics/{id}/ai-summary | 允许 | 允许 | 允许 |
| GET /api/qa/topics/{id}/export | 允许 | 允许 | 允许 |
| POST /api/qa/topics/{id}/conclusion | 允许 | 允许 | 403 |
| PATCH /api/qa/topics/{id}/statements/{statement_id} | 允许 | 403 | 403 |
| GET /api/qa/decisions | 允许 | 允许 | 允许 |
| POST /api/qa/topics/{id}/statements/{statement_id}/reports | 允许 | 允许 | 允许 |
| GET /api/qa/reports | 允许 | 403 | 403 |
| PATCH /api/qa/reports/{report_id} | 允许 | 403 | 403 |
| GET /api/qa/notifications | 允许 | 允许 | 允许 |
| GET /api/qa/notifications/unread-count | 允许 | 允许 | 允许 |
| POST /api/qa/notifications/read | 允许 | 允许 | 允许 |
| POST /api/qa/categories | 允许 | 403 | 403 |
| PATCH /api/qa/categories/{id} | 允许 | 403 | 403 |
| DELETE /api/qa/categories/{id} | 允许 | 403 | 403 |

## 表格协作接口

表格协作模块的详细需求、决策和数据模型见 `table-module-requirements.md`，这里给出接口速查。

### GET /api/tables?q=

任何已登录用户。返回表格列表，`q` 可按名称或说明模糊搜索。列表项字段：

```json
{
  "id": 1,
  "name": "2026届毕业设计进度表",
  "description": "跟踪选题与进度",
  "owner": { "id": 2, "username": "teacher", "name": "胡军成", "role": "teacher" },
  "column_count": 4,
  "row_count": 2,
  "version_number": 1,
  "created_at": "2026-10-18T10:00:00+00:00",
  "updated_at": "2026-10-18T10:00:00+00:00"
}
```

### POST /api/tables

任何已登录用户。请求：

```json
{ "name": "2026届毕业设计进度表", "description": "跟踪选题与进度", "columns": ["组号", "题目", "成员", "进度"] }
```

`columns` 可以是字符串数组，也可以是 `[{"name": "组号", "type": "text"}]` 对象数组。至少一列。成功返回 201，`data` 除列表字段外还带 `columns`、`rows`。

### POST /api/tables/import

任何已登录用户。使用 `multipart/form-data` 一次导入创建表格，字段为 `name`、`description`、`file`；`name` 留空时使用文件名去掉扩展名。文件规则与覆盖导入相同。成功返回 201：

```json
{
  "table": { "id": 2, "name": "scores", "row_count": 120, "version_number": 1 },
  "version": { "version_number": 1 },
  "summary": { "sheet_name": "成绩表", "formula_count": 24, "locked_formulas": [] }
}
```

解析、公式检查或数据规模校验失败时不会创建表格。

### GET /api/tables/{id}

任何已登录用户。返回 `columns`、`rows`、`cell_meta` 与列表字段，并额外带 `can_manage`（当前用户是否为创建者或管理员）。

### POST /api/tables/{id}/import

创建者/管理员。使用 `multipart/form-data` 上传字段 `file`，支持 `.xlsx`、`.xls`、`.csv`，读取第一个工作表，最多 2,000 行、30 列、5 MB。成功时整表覆盖，返回：

```json
{
  "table": { "id": 1, "row_count": 120, "column_count": 8, "cell_meta": {} },
  "version": { "version_number": 5, "changelog": "导入 scores.xlsx（成绩表）" },
  "rollback_version": { "version_number": 4, "changelog": "导入 scores.xlsx 前自动快照" },
  "summary": {
    "filename": "scores.xlsx",
    "sheet_name": "成绩表",
    "formula_count": 24,
    "locked_formulas": []
  }
}
```

导入前先保存旧表快照，导入后再保存新版本。解析或公式检查失败时原表不改变。无法计算且没有缓存结果的公式返回 422 `missing_formula_result`；有缓存结果的公式保留原值并锁定。

`.xls` 旧版格式只能稳定取得现有计算结果，不能可靠恢复公式原文；需要继续公式协作时应使用 `.xlsx`。

### PATCH /api/tables/{id}

创建者/管理员。请求 `{"name": "...", "description": "..."}`，两个字段都可选。修改名称/说明会写入一条 `rename` 修改记录。

### DELETE /api/tables/{id}

创建者/管理员。删除表格及其版本、修改记录，返回 204。

### PATCH /api/tables/{id}/cells

任何已登录用户。请求：

```json
{ "row_key": "r1", "column_key": "col2", "value": "在线文档协作平台" }
```

`value` 以 `=` 开头时按公式保存并自动重算，否则按普通文本保存。成功返回 `{"table": ..., "change": ..., "row": ...}`；值未变化时 `change` 为 `null` 且不写记录。`row_key` 不存在返回 404 `row_not_found`，`column_key` 不存在返回 404 `column_not_found`，值超过 5000 字返回 400 `invalid_value`，公式不支持或无法解析返回 400 `invalid_formula`，修改锁定公式返回 409 `cell_locked`。

### POST /api/tables/{id}/rows

任何已登录用户。请求体可为 `{"cells": {"col1": "1"}}` 或空对象。新行的 `row_key` 自动生成，返回 201 和 `{"table", "change", "row"}`。

### DELETE /api/tables/{id}/rows/{row_key}

创建者/管理员。删除前自动保存快照，删除指定行并写入 `row_delete` 记录，返回 `{"table", "change"}`。

### POST /api/tables/{id}/rows/delete

创建者/管理员。请求 `{"row_keys": ["r1", "r3"]}` 批量删除行。删除前自动保存一个快照，删除后写入 `rows_delete` 记录，返回 `{"table", "change", "deleted_count"}`。

### POST /api/tables/{id}/columns

任何已登录用户。请求 `{"name": "备注"}`。列名重复返回 409 `column_exists`。新增列属于结构变化，会自动生成一个新版本。

### PATCH /api/tables/{id}/columns/{column_key}

创建者/管理员。请求可只含 `{"name": "新列名"}`、`{"width": 240}` 或两者都带。`width` 取值 40~600。修改会写入 `column_update` 记录。

### DELETE /api/tables/{id}/columns/{column_key}

创建者/管理员。删除前自动保存快照，删除该列并清掉所有行里对应的单元格数据，写入 `column_delete` 记录。表格只剩一列时返回 400 `cannot_delete_last_column`。

### POST /api/tables/{id}/columns/delete

创建者/管理员。请求 `{"column_keys": ["col1", "col2"]}` 批量删除列。删除前自动保存快照，写入 `columns_delete` 记录；不允许删光所有列。

### GET /api/tables/{id}/changes?kind=&limit=

任何已登录用户。修改记录按时间倒序，`kind` 可选过滤，`limit` 默认不限（上限 500）。每条记录字段：

```json
{
  "id": 1,
  "kind": "cell_update",
  "editor": { "id": 2, "username": "teacher", "name": "胡军成" },
  "row_key": "r1",
  "column_key": "col2",
  "column_name": "题目",
  "old_value": "旧题目",
  "new_value": "在线文档协作平台",
  "detail": {},
  "created_at": "2026-10-18T10:01:00+00:00"
}
```

### GET /api/tables/{id}/versions

任何已登录用户。版本列表按版本号倒序。每项含 `version_number`、`changelog`、`editor`、`created_at`、`column_count`、`row_count`。

### POST /api/tables/{id}/versions

创建者/管理员。请求 `{"changelog": "期中检查前定稿"}`（可省略，默认「手动保存快照」），成功返回 201 和完整快照。

### GET /api/tables/{id}/versions/{vid}

任何已登录用户。返回版本详情，含完整 `columns`、`rows`、`cell_meta` 快照。

### POST /api/tables/{id}/versions/{vid}/rollback

创建者/管理员。把当前表格恢复为该版本快照，并把这次回滚保存为新版本。返回 `{"table", "version"}`。

## 表格协作权限映射

| 接口 | 管理员 | 创建者 | 其他教师 |
| --- | --- | --- | --- |
| GET /api/tables | 允许 | 允许 | 允许 |
| POST /api/tables | 允许 | 允许 | 允许 |
| POST /api/tables/import | 允许 | 允许 | 允许 |
| GET /api/tables/{id} | 允许 | 允许 | 允许 |
| POST /api/tables/{id}/import | 允许 | 允许 | 403 |
| PATCH /api/tables/{id} | 允许 | 允许 | 403 |
| DELETE /api/tables/{id} | 允许 | 允许 | 403 |
| PATCH /api/tables/{id}/cells | 允许 | 允许 | 允许 |
| POST /api/tables/{id}/rows | 允许 | 允许 | 允许 |
| DELETE /api/tables/{id}/rows/{row_key} | 允许 | 允许 | 403 |
| POST /api/tables/{id}/rows/delete | 允许 | 允许 | 403 |
| POST /api/tables/{id}/columns | 允许 | 允许 | 允许 |
| PATCH /api/tables/{id}/columns/{column_key} | 允许 | 允许 | 403 |
| DELETE /api/tables/{id}/columns/{column_key} | 允许 | 允许 | 403 |
| POST /api/tables/{id}/columns/delete | 允许 | 允许 | 403 |
| GET /api/tables/{id}/changes | 允许 | 允许 | 允许 |
| GET /api/tables/{id}/versions | 允许 | 允许 | 允许 |
| POST /api/tables/{id}/versions | 允许 | 允许 | 403 |
| GET /api/tables/{id}/versions/{vid} | 允许 | 允许 | 允许 |
| POST /api/tables/{id}/versions/{vid}/rollback | 允许 | 允许 | 403 |

## 文档 AI 接口

统一走 Cosmos 的 OpenAI 兼容接口，Key 通过 `COSMOS_API_KEY` 环境变量配置。手动问答 / 预审没配 Key 时返回 503 `ai_not_configured`；自动预审没配 Key 时会留下一条 `skipped` 记录。模型调用失败返回 502 `ai_failed`。

### POST /api/documents/{id}/ai/qa

任何已登录用户。请求：

```json
{
  "question": "总学分要求是多少？",
  "version_id": 1,
  "history": [
    {"role": "user", "content": "上一轮问题"},
    {"role": "assistant", "content": "上一轮回答"}
  ]
}
```

`version_id` 省略时使用当前版本；`history` 只保留最近 8 条 user / assistant 消息。成功返回 `document_id`、`version_id`、`version_number`、`question`、`answer`、`model`、`truncated`。文档正文最多读取 `AI_MAX_DOCUMENT_CHARS`（默认 60000）个字符。

### POST /api/documents/{id}/ai/review

管理员或文档负责人。请求：

```json
{
  "version_id": 1,
  "spec_document_ids": [2, 3]
}
```

`spec_document_ids` 可选，最多 3 份，取各规范的当前版本；不传时使用该文档所属分类的 `default_spec_document_ids`，分类也没配置时只做内部一致性与版本变化检查。

成功返回 201 和预审记录。`status` 为 pending / running / done / failed / skipped，
`source` 为 manual / auto。预审记录带版本化模板信息和 `checklist` 快照。

`result.check_results` 按清单逐项给出 `pass`、`fail` 或 `unknown`，并附带
`location`、`evidence`、`explanation`、`suggestion`。后端校验模型返回的规则 ID，
缺失项自动补为 `unknown`，再根据必检项计算整体结论：

- 任一项 `fail`：`risk`；
- 没有失败但存在必检项 `unknown`：`unknown`；
- 其余情况：`pass`。

`result.checklist_summary` 返回总数、通过、不通过和待确认数量。旧格式模型只返回
`issues` 时仍按兼容模式显示，但不会假装已完成逐项检查。

每个 `issues` 项包含 `location` 与 `evidence`，用于说明问题位置和判断依据。
如果同一文档的上一版本曾被人工退回，新预审会自动写入
`previous_review_id`，并把上次问题带入提示词；`previous_issue_checks`
逐项返回 `resolved` / `unresolved` / `unclear`。`previous_review` 摘要同时
返回上次退回意见，供修订版复审页面展示。

### GET /api/documents/{id}/ai/reviews?limit=10

任何已登录用户。按时间倒序返回预审历史，`limit` 上限 30。

### PATCH /api/documents/{id}/ai/reviews/{review_id}/decision

管理员或文档负责人。对已完成的预审做人工确认：

```json
{"decision": "return", "note": "请统一学分说明"}
```

`decision` 只能是 `pass` 或 `return`；`return` 时必须填写 `note`。成功返回更新后的预审记录，含 `human_decision`、`human_note`、`human_reviewer`、`human_reviewed_at`。

### 分类默认规范

管理员通过 `PATCH /api/categories/{id}` 配置：

```json
{"default_spec_document_ids": [2, 3]}
```

最多 3 份，文档必须存在。`GET /api/categories` 会同时返回 `default_spec_document_ids` 和 `default_spec_documents`（含标题）。

### 上传新版本后的自动预审

`POST /api/documents/{id}/versions` 成功后，如果 `AI_AUTO_REVIEW_ENABLED` 为真（默认），会创建一条 `source=auto` 的预审任务，并自动带入该分类的默认规范。生产环境默认在后台线程执行；`AI_AUTO_REVIEW_SYNC=1` 可改为同步执行（测试用）。上传响应本身不受预审耗时影响。

| 接口 | 管理员 | 文档负责人 | 其他教师 |
| --- | --- | --- | --- |
| POST /api/documents/{id}/ai/qa | 允许 | 允许 | 允许 |
| POST /api/documents/{id}/ai/review | 允许 | 允许 | 403 |
| GET /api/documents/{id}/ai/reviews | 允许 | 允许 | 允许 |
| PATCH /api/documents/{id}/ai/reviews/{review_id}/decision | 允许 | 允许 | 403 |
