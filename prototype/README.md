# prototype/：业务方向原型

这个目录存放业务方向的静态原型，入口是 `prototype/index.html`（通过后端访问就是 `http://127.0.0.1:5000/`）。

| 路径 | 内容 | 是否需要后端 |
| --- | --- | --- |
| `index.html` | 原型入口页，列出当前演示的原型 | 不需要 |
| `documents/` | 文档管理模块原型，9 个页面（含微信登录与账号设置） | 需要，先启动 `backend/run.py` |
| `taskman/` | 任务看板原型（历史文件，已从入口页撤下） | 不需要，数据存在浏览器 localStorage |

## 原型现状

- `documents/` 是**当前项目范围**（文档管理模块）的原型，已经接入真实 Flask API，浏览器里点一下就会真的请求后端。入口页只展示它。
- `taskman/` 做的是“任务优先级排序”，不接后端，也没有写进文档管理模块的需求。**已经撤出原型入口页，文件先保留在目录里**，等需求方确认是否保留为正式功能；确认不需要时再整体删除。

详细说明见 `documents/README.md`；任务看板的说明保留在 `taskman/README.md`。

## 打开方式

文档管理原型必须先启动后端：

```powershell
.\.venv\Scripts\python.exe backend\run.py
```

然后在浏览器打开 `http://127.0.0.1:5000/`，从入口页进入。

## 视觉规范

原型在 2026-09-27 做过一次整体美化（现代教育风），新增页面请对齐下面这套取值。文档管理模块的取值集中在 `documents/styles.css` 的 `:root`；入口页是独立静态页，在自己的 `<style>` 里内联了一份同样的基线。

| 项目 | 约定 |
| --- | --- |
| 主色 | 沿用 `#2f5f9e`，扩成 `--brand-50 #eef4fb`、`--brand-100 #dce8f6`、`--brand-500 #3b76bf`、`--brand-600 #2f5f9e`、`--brand-700 #1f4473`；点睛暖色 `--accent #e8a33d` 只用于小面积强调 |
| 中性色 | 正文 `#1f2937`、次要文字 `#64748b`、描边 `#e3e8ef`、页面底 `#f4f7fb`、卡片 `#fff` |
| 字体 | 系统字体栈（Segoe UI / Microsoft YaHei），不引外部字体；正文 15px / 行高 1.65，页标题 28px / 600，卡片标题 18px / 600，表头 13px |
| 圆角与阴影 | 圆角 8 / 12 / 16 三档；卡片 `0 1px 2px rgba(15,23,42,.04)`，hover 与浮层 `0 12px 28px rgba(15,23,42,.10)` |
| 间距 | 4 / 8 / 12 / 16 / 20 / 24 / 32 / 48；内容区最大宽 1120px，上下留白 32 / 64px |
| 结构 | 顶栏 `.topbar`（品牌 SVG + `#topbar` 动态区）；页面标题与副标题包在 `<header class="page-head">` 里，左侧有 4px 品牌渐变竖条 |
| 图标 | 只用内联 SVG 或 CSS `mask` + data URI（`--icon-*`），不新增图片文件。动态渲染的区域（退出按钮、下拉箭头、状态徽标、提示块）用稳定选择器补图标 |
| 动效 | 过渡 150–200ms `ease-out`，内容淡入 180ms；必须放在 `prefers-reduced-motion: reduce` 的关闭分支之外 |
| 响应式 | 只做桌面端，1280–1920；不新增断点，但要保证 1280 起不出现横向滚动 |

两条硬约束：

- `documents/app.js` 会拼出 `card`、`table`、`btn btn-primary`、`status-badge status-*`、`search-select*` 等 class，并通过 46 个固定 id 找节点。**这些名字是界面契约，只覆盖样式，不要改名**；改结构前先核对 `app.js`。
- `<td>` 上不要套用 `display: flex` 之类的规则（`.actions` 就是踩过的坑），需要横向排列时用 `td.actions` 显式还原成 `table-cell`。
