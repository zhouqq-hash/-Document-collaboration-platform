# 文档管理模块前后端接口规范

## 通用约定

- Base URL：`/api`。
- 请求和响应默认使用 JSON。
- 文件上传使用 `multipart/form-data`。
- 时间字段使用 ISO 8601 字符串。
- 单个上传文件大小上限：50 MB。

## 通用响应格式

成功：

```json
{ "data": {} }
```

失败：

```json
{ "error": { "code": "permission_denied", "message": "没有权限执行此操作" } }
```

常见 HTTP 状态码：200、201、204、400、401、403、404。

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

返回分类列表，包含每个分类的文档数量。

### POST /api/categories

仅管理员。请求：

```json
{ "name": "新分类", "sort_order": 10 }
```

### PATCH /api/categories/{id}

仅管理员。修改分类名称或排序，字段可选：

```json
{ "name": "新名称", "sort_order": 5 }
```

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

### GET /api/documents/{id}

返回文档详情和当前版本信息。

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

返回该文档全部版本，按版本号倒序。

### POST /api/documents/{id}/versions

仅管理员或文档负责人。使用 multipart：

```text
changelog, file
```

成功返回新版本对象，版本号自动递增。

### GET /api/documents/{id}/versions/{version_id}/download

下载指定版本文件，返回文件流。

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
| GET 版本/下载 | 允许 | 允许 | 允许 |
