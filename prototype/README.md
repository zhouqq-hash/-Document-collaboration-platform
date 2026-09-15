# prototype/：业务方向原型

这个目录存放业务方向的两个静态原型，入口是 `prototype/index.html`（通过后端访问就是 `http://127.0.0.1:5000/`）。

| 路径 | 内容 | 是否需要后端 |
| --- | --- | --- |
| `index.html` | 原型入口页，列出下面两个原型 | 不需要 |
| `documents/` | 文档管理模块原型，7 个页面 | 需要，先启动 `backend/run.py` |
| `taskman/` | 任务看板原型，4 个页面 | 不需要，数据存在浏览器 localStorage |

## 两个原型的关系

- `documents/` 是**当前项目范围**（文档管理模块）的原型，已经接入真实 Flask API，浏览器里点一下就会真的请求后端。
- `taskman/` 是**独立原型**，做的是“任务优先级排序”这件事，只用来演示前端交互和算法，不接后端，也还没写进文档管理模块的需求里。

详细说明分别见 `documents/README.md` 和 `taskman/README.md`。

## 打开方式

文档管理原型必须先启动后端：

```powershell
.\.venv\Scripts\python.exe backend\run.py
```

然后在浏览器打开 `http://127.0.0.1:5000/`，从入口页进入。

任务看板原型不依赖后端，可以直接双击 `prototype/taskman/index.html` 打开（样式使用 Bootstrap CDN，离线时会退化成无样式的页面，功能仍然可用）。
