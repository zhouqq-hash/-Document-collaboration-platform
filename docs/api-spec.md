# 文档管理模块前后端接口规范

## 通用约定

- Base URL：`/api`。
- 请求和响应默认使用 JSON。
- 文件上传使用 `multipart/form-data`。
- 时间字段使用 ISO 8601 字符串。

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
{ "username": "admin", "password": "123456" }
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

返回当前登录用户，未登录返回 401。

## 分类接口

### GET /api/categories

返回分类列表，包含每个分类的文档数量。

### POST /api/categories

仅管理员。请求：

```json
{ "name": "新分类", "sort_order": 10 }
```

## 文档接口

### GET /api/documents?category_id=1

返回文档列表，可带分类筛选参数。

### POST /api/documents

仅管理员，创建文档并上传首个版本。使用 multipart：

```text
title, category_id, owner_id, changelog, file
```

### GET /api/documents/{id}

返回文档详情和当前版本信息。

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
| GET /api/categories | 允许 | 允许 | 允许 |
| POST /api/categories | 允许 | 403 | 403 |
| GET /api/documents | 允许 | 允许 | 允许 |
| POST /api/documents | 允许 | 403 | 403 |
| POST /api/documents/{id}/versions | 允许 | 允许（仅本人负责） | 403 |
| GET 版本/下载 | 允许 | 允许 | 允许 |
