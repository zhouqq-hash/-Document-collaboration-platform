# 表格协作模块需求与接口规范

> 状态：已定稿并实现；文件导入与常用公式重算补充于 2026-10-23。对应 `project-division.md` 的 W4 ~ W6「表格协作」阶段。

## 1. 范围

本期交付五块能力：

1. 表格创建：登录用户可新建表格，自定义列名，创建时自动生成 v1 快照。
2. 行内编辑：打开表格后点击单元格直接编辑，失焦自动保存，支持键盘导航（方向键移动、Enter 下移、Tab 右移）与当前格高亮，所有登录用户可协作编辑、新增行、新增列。
3. 修改记录：每次单元格修改、增删行列、改信息、回滚都写入审计日志，记录操作人、时间、旧值、新值。
4. 版本回滚：以「整表快照」为粒度，创建者/管理员可保存快照、预览历史版本、一键回滚。
5. 文件导入：创建者/管理员可把本地 `.xlsx` / `.xls` / `.csv` 覆盖导入为新表格；常用公式自动重算，无法计算但有原结果的公式保留结果并锁定。

## 2. 已确认决策

| 决策点 | 结论 | 理由 |
| --- | --- | --- |
| 新建方式 | 提供「从空白创建」和「导入 Excel / CSV」两种方式；空白方式逐列添加，导入方式一步创建并生成 v1 | 避免逗号手写列名，也避免先建空表再进入详情导出的多余步骤 |
| 回滚粒度 | 整表快照回滚（`project-division.md` 风险 #3 的简单方案） | 实现稳定、语义清晰；操作日志保留每一次改动，满足审计需要 |
| 版本产生时机 | 创建表格（v1）、新增列（结构变化自动快照）、删除行/列前自动快照、手动保存快照、执行回滚（回滚本身存为新版本） | 单元格编辑只进修改记录；删除操作先存快照，保证删错可回滚撤销 |
| 行内编辑保存方式 | 失焦（blur）自动保存，Enter 提交、Esc 放弃 | 原型场景下交互最直接，减少按钮噪音 |
| 交互能力 | 键盘导航、当前格高亮、整行/整列多选、右键菜单删除、列拖宽与重命名、删除后一键撤销、常用公式 | 保留轻量电子表格手感；不追求完整 Excel 引擎，不支持宏、外部链接、跨工作表引用 |
| 导入范围 | `.xlsx` / `.xls` / `.csv`，第一个工作表，最多 2,000 行数据、30 列、5 MB | 覆盖老师已有表格迁移到平台的主要场景，同时限制浏览器与服务端计算压力 |
| 导入公式 | 支持四则运算、单元格/区域引用及 `SUM`、`AVERAGE`、`COUNT`、`MIN`、`MAX`、`IF`、`ROUND` 等常用函数；编辑输入后自动重算 | 让导入结果继续参与协作，而不是退化成只读截图 |
| 不支持公式 | 保留文件中的原始计算结果并锁定单元格，醒目提示；没有可用结果时拒绝整次导入 | 避免公式失效后显示过期数字且用户误以为仍在计算 |
| 导入覆盖 | 整表覆盖；导入前自动保存快照，导入后再保存新版本，可从版本历史回滚 | 语义简单、可恢复；旧文件版本清晰可追溯 |
| 数据模型 | 表格行列和公式元数据以 JSON 存于 `tables` 表，快照存于 `table_versions`，审计日志存于 `table_changes` | 与现有 SQLite + SQLAlchemy 结构一致，迁移简单 |
| 权限 | 查看/编辑单元格/增删行列：所有登录用户；导入、修改表格信息、删除表格、保存快照、回滚：仅创建者或管理员 | 导入会整表覆盖，属于高影响管理操作，沿用版本管理权限 |

`.xls` 是旧版二进制格式，当前解析库只能稳定读取计算结果，无法可靠恢复公式原文；需要公式继续协作时应另存为 `.xlsx`。

## 3. 数据模型

| 表 | 字段 | 说明 |
| --- | --- | --- |
| `tables` | `name`、`description`、`owner_id`、`columns`(JSON)、`rows`(JSON)、`cell_meta`(JSON)、`row_seq`、`version_number`、时间戳 | 当前表格状态；`cell_meta` 保存公式、锁定和警告 |
| `table_versions` | `table_id`、`version_number`、`snapshot`(JSON：`{columns, rows, cell_meta}`)、`changelog`、`editor_id`、`created_at` | 版本快照，整表回滚的最小单元 |
| `table_changes` | `table_id`、`editor_id`、`kind`、`row_key`、`column_key`、`column_name`、`old_value`、`new_value`、`detail`(JSON)、`created_at` | 修改记录（审计日志） |

- `columns` 形如 `[{"key": "col1", "name": "组号", "type": "text"}]`。
- `rows` 形如 `[{"row_key": "r1", "cells": {"col1": "1", "col2": "..."}}]`。
- `cell_meta` 形如 `{"r1:col3": {"formula": "=B2*C2", "locked": false}}`；锁定单元格还会带 `warning`。
- `row_key` 用 `r + 自增序号` 生成，删除行后不会复用，保证历史记录可追溯。
- `kind` 取值：`cell_update` / `row_add` / `row_delete` / `rows_delete` / `column_add` / `column_update` / `column_delete` / `columns_delete` / `rename` / `rollback` / `import`。

## 4. 接口清单

全部要求登录（未登录返回 401 `unauthorized`）。

| 方法 | 路径 | 说明 | 权限 |
| --- | --- | --- | --- |
| GET | `/api/tables?q=` | 表格列表，`q` 按名称/说明模糊搜索 | 登录用户 |
| POST | `/api/tables` | 新建表格 | 登录用户 |
| POST | `/api/tables/import` | 使用 multipart 字段 `name`、`description`、`file` 一步导入创建表格 | 登录用户 |
| GET | `/api/tables/{id}` | 表格详情（含行列和 `can_manage`） | 登录用户 |
| POST | `/api/tables/{id}/import` | 使用 multipart 字段 `file` 导入并整表覆盖 | 创建者/管理员 |
| PATCH | `/api/tables/{id}` | 修改名称/说明 | 创建者/管理员 |
| DELETE | `/api/tables/{id}` | 删除表格 | 创建者/管理员 |
| PATCH | `/api/tables/{id}/cells` | 行内编辑一个单元格 | 登录用户 |
| POST | `/api/tables/{id}/rows` | 新增一行 | 登录用户 |
| DELETE | `/api/tables/{id}/rows/{row_key}` | 删除一行 | 创建者/管理员 |
| POST | `/api/tables/{id}/rows/delete` | 批量删除行（删除前自动快照） | 创建者/管理员 |
| POST | `/api/tables/{id}/columns` | 新增一列（自动生成新版本） | 登录用户 |
| PATCH | `/api/tables/{id}/columns/{column_key}` | 重命名列 / 调整列宽 | 创建者/管理员 |
| DELETE | `/api/tables/{id}/columns/{column_key}` | 删除列及其数据（删除前自动快照） | 创建者/管理员 |
| POST | `/api/tables/{id}/columns/delete` | 批量删除列（删除前自动快照） | 创建者/管理员 |
| GET | `/api/tables/{id}/changes?kind=&limit=` | 修改记录（按时间倒序） | 登录用户 |
| GET | `/api/tables/{id}/versions` | 版本列表（按版本号倒序） | 登录用户 |
| POST | `/api/tables/{id}/versions` | 手动保存快照 | 创建者/管理员 |
| GET | `/api/tables/{id}/versions/{vid}` | 版本详情（含完整快照） | 登录用户 |
| POST | `/api/tables/{id}/versions/{vid}/rollback` | 回滚到指定版本 | 创建者/管理员 |

## 5. 关键请求/响应示例

### POST /api/tables

```json
{ "name": "2026届毕业设计进度表", "description": "跟踪选题与进度", "columns": ["组号", "题目", "进度"] }
```

返回 201，`data` 含 `id`、`columns`、`rows`、`version_number: 1` 等。

### POST /api/tables/import

使用 `multipart/form-data`，字段为 `name`、`description`（可选）和 `file`。文件规则与覆盖导入相同；成功直接创建表格并返回 201，`data.table` 为完整表格，`data.summary` 包含公式和锁定统计。文件名可作为默认表格名称，解析失败不会创建空表。

### PATCH /api/tables/{id}/cells

```json
{ "row_key": "r1", "column_key": "col2", "value": "在线文档协作平台" }
```

返回 `data`：

```json
{
  "table": { "id": 1, "row_count": 1, "version_number": 1, "...": "..." },
  "change": {
    "kind": "cell_update",
    "editor": { "username": "teacher", "name": "胡军成" },
    "column_name": "题目",
    "old_value": "旧题目",
    "new_value": "在线文档协作平台",
    "created_at": "2026-10-18T12:00:00+00:00"
  },
  "row": { "row_key": "r1", "cells": { "col2": "在线文档协作平台" } }
}
```

旧值和新值相同时不写修改记录，`change` 为 `null`。
值以 `=` 开头时按公式保存并重算；公式结果作为单元格显示值存入 `cells`，公式原文存入 `cell_meta`。

### POST /api/tables/{id}/import

请求使用 `multipart/form-data`，字段名为 `file`。成功返回：

```json
{
  "table": { "id": 1, "row_count": 120, "column_count": 8, "cell_meta": {} },
  "version": { "version_number": 5, "changelog": "导入 scores.xlsx（成绩表）" },
  "rollback_version": { "version_number": 4, "changelog": "导入 scores.xlsx 前自动快照" },
  "summary": {
    "filename": "scores.xlsx",
    "sheet_name": "成绩表",
    "row_count": 120,
    "column_count": 8,
    "formula_count": 24,
    "locked_formulas": []
  }
}
```

导入失败不会覆盖原表，也不会新增版本。

### POST /api/tables/{id}/versions/{vid}/rollback

把表格行列恢复为该版本的快照，并自动创建一个新版本（changelog 为「回滚到版本 N」）。返回 `data.table` 和 `data.version`。

## 6. 错误码

| 状态 | code | 场景 |
| --- | --- | --- |
| 400 | `invalid_name` / `invalid_description` / `invalid_columns` / `invalid_row` / `invalid_value` / `invalid_formula` / `invalid_file_type` / `missing_file` | 入参、公式或文件类型不合法 |
| 403 | `permission_denied` | 非创建者/管理员执行管理类操作 |
| 404 | `table_not_found` / `row_not_found` / `column_not_found` / `version_not_found` | 资源不存在 |
| 409 | `column_exists` / `cell_locked` | 列名重复或尝试修改锁定公式 |
| 413 | `file_too_large` | 导入文件超过 5 MB |
| 422 | `empty_import` / `too_many_rows` / `too_many_columns` / `invalid_excel` / `invalid_csv` / `missing_formula_result` / `external_links` | 文件内容、规模或公式结果不满足导入要求 |

## 7. 验收标准

- 新建表格后能立即看到 v1 版本和空表格；填列名后打开可逐格编辑并自动保存。
- 两个不同账号先后编辑同一单元格，修改记录里能看到两个操作人和各自的旧值/新值。
- 新增列后版本号 +1；保存快照、回滚快照后版本号继续递增，历史不被覆盖。
- 回滚后表格内容与目标快照一致，同时修改记录多出一条 `rollback`。
- 非创建者执行「编辑信息 / 保存快照 / 回滚 / 删除表格」返回 403。
- 创建者导入含常用公式的 XLSX 后，公式结果可见；修改输入单元格后相关公式自动重算。
- 无法计算但文件含原结果的公式保留原值并锁定；没有原结果时整次导入失败且原表、版本号均不变。
- 导入前自动保存旧版本，覆盖后可一键回滚；非创建者导入返回 403。
- 后端 `pytest` 全绿，前端在浏览器里走通「创建 → 编辑 → 看记录 → 快照 → 改坏 → 回滚」。
