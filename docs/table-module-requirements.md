# 表格协作模块需求与接口规范

> 状态：已定稿并实现（2026-10-18）。对应 `project-division.md` 的 W4 ~ W6「表格协作」阶段。

## 1. 范围

本期交付四块能力：

1. 表格创建：登录用户可新建表格，自定义列名，创建时自动生成 v1 快照。
2. 行内编辑：打开表格后点击单元格直接编辑，失焦自动保存，支持键盘导航（方向键移动、Enter 下移、Tab 右移）与当前格高亮，所有登录用户可协作编辑、新增行、新增列。
3. 修改记录：每次单元格修改、增删行列、改信息、回滚都写入审计日志，记录操作人、时间、旧值、新值。
4. 版本回滚：以「整表快照」为粒度，创建者/管理员可保存快照、预览历史版本、一键回滚。

## 2. 已确认决策

| 决策点 | 结论 | 理由 |
| --- | --- | --- |
| 回滚粒度 | 整表快照回滚（`project-division.md` 风险 #3 的简单方案） | 实现稳定、语义清晰；操作日志保留每一次改动，满足审计需要 |
| 版本产生时机 | 创建表格（v1）、新增列（结构变化自动快照）、删除行/列前自动快照、手动保存快照、执行回滚（回滚本身存为新版本） | 单元格编辑只进修改记录；删除操作先存快照，保证删错可回滚撤销 |
| 行内编辑保存方式 | 失焦（blur）自动保存，Enter 提交、Esc 放弃 | 原型场景下交互最直接，减少按钮噪音 |
| 交互能力 | 键盘导航、当前格高亮、整行/整列多选、右键菜单删除、列拖宽与重命名、删除后一键撤销 | 用「轻量电子表格」手感替代完整 Excel 引擎，删除不设二次确认、靠撤销兜底，公式、单元格引用、合并单元格、多 sheet 明确不做 |
| 数据模型 | 表格行列以 JSON 存于 `tables` 表，快照存于 `table_versions`，审计日志存于 `table_changes` | 与现有 SQLite + SQLAlchemy 结构一致，迁移简单 |
| 权限 | 查看/编辑单元格/增删行列：所有登录用户；修改表格信息、删除表格、保存快照、回滚：仅创建者或管理员 | 满足「多人协作编辑 + 创建者掌控版本」的定位 |

## 3. 数据模型

| 表 | 字段 | 说明 |
| --- | --- | --- |
| `tables` | `name`、`description`、`owner_id`、`columns`(JSON)、`rows`(JSON)、`row_seq`、`version_number`、时间戳 | 当前表格状态 |
| `table_versions` | `table_id`、`version_number`、`snapshot`(JSON：`{columns, rows}`)、`changelog`、`editor_id`、`created_at` | 版本快照，整表回滚的最小单元 |
| `table_changes` | `table_id`、`editor_id`、`kind`、`row_key`、`column_key`、`column_name`、`old_value`、`new_value`、`detail`(JSON)、`created_at` | 修改记录（审计日志） |

- `columns` 形如 `[{"key": "col1", "name": "组号", "type": "text"}]`。
- `rows` 形如 `[{"row_key": "r1", "cells": {"col1": "1", "col2": "..."}}]`。
- `row_key` 用 `r + 自增序号` 生成，删除行后不会复用，保证历史记录可追溯。
- `kind` 取值：`cell_update` / `row_add` / `row_delete` / `rows_delete` / `column_add` / `column_update` / `column_delete` / `columns_delete` / `rename` / `rollback`。

## 4. 接口清单

全部要求登录（未登录返回 401 `unauthorized`）。

| 方法 | 路径 | 说明 | 权限 |
| --- | --- | --- | --- |
| GET | `/api/tables?q=` | 表格列表，`q` 按名称/说明模糊搜索 | 登录用户 |
| POST | `/api/tables` | 新建表格 | 登录用户 |
| GET | `/api/tables/{id}` | 表格详情（含行列和 `can_manage`） | 登录用户 |
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

### POST /api/tables/{id}/versions/{vid}/rollback

把表格行列恢复为该版本的快照，并自动创建一个新版本（changelog 为「回滚到版本 N」）。返回 `data.table` 和 `data.version`。

## 6. 错误码

| 状态 | code | 场景 |
| --- | --- | --- |
| 400 | `invalid_name` / `invalid_description` / `invalid_columns` / `invalid_row` / `invalid_value` | 入参不合法或过长 |
| 403 | `permission_denied` | 非创建者/管理员执行管理类操作 |
| 404 | `table_not_found` / `row_not_found` / `column_not_found` / `version_not_found` | 资源不存在 |
| 409 | `column_exists` | 列名重复 |

## 7. 验收标准

- 新建表格后能立即看到 v1 版本和空表格；填列名后打开可逐格编辑并自动保存。
- 两个不同账号先后编辑同一单元格，修改记录里能看到两个操作人和各自的旧值/新值。
- 新增列后版本号 +1；保存快照、回滚快照后版本号继续递增，历史不被覆盖。
- 回滚后表格内容与目标快照一致，同时修改记录多出一条 `rollback`。
- 非创建者执行「编辑信息 / 保存快照 / 回滚 / 删除表格」返回 403。
- 后端 `pytest` 全绿，前端在浏览器里走通「创建 → 编辑 → 看记录 → 快照 → 改坏 → 回滚」。
