# Django 五天冲刺计划（附省 token 用法）

目标：五天内把 Django 学到“能对着 Flask 项目说清两者差别、能自己写一个小 app”的程度。
定位：Django 只做对照学习，不重复实现本项目（见 `docs/django-vs-flask.md`）。

## 0. 先看这三条，比计划本身重要

1. **一个话题一个会话，学完就丢。** 会话越长，每条消息都要把之前的全部内容重新发一遍，越聊越贵。别在一个会话里从 Django 一路问到 Flask 和部署。
2. **一次问清，不要挤牙膏。** 一条消息里给全：环境 + 文件路径 + 完整报错 + 期望结果 + 已试过什么。来回十轮比一次问透贵十倍。
3. **结论落到本地文件。** 今天想通的东西写成几行笔记，明天直接看文件（免费），不要让我重新推导一遍（收费）。本文件和 `docs/worklog-*.md` 就是干这个的。

## 1. 起点状态（2026-09-18）

| 项 | 情况 |
| --- | --- |
| 虚拟环境 | `.django-learning/`，Django 已装 |
| 教程项目 | `djangotutorial/`（`mysite` + `polls`） |
| 进度 | 约官方教程 Part 1–3 完成；Part 4 的 `vote`/`results` 仍是占位；`tests.py` 为空 |
| 环境变量提示 | 用 `.django-learning\Scripts\python.exe` 跑 `manage.py`，不要用系统 python |

## 2. 五天计划

### Day 1：把 polls 收尾到 Part 4

- `detail.html` 加 `<form action="{% url 'polls:vote' question.id %}" method="post">`，处理 `csrf_token`。
- `vote` 视图真正写库：`Choice.objects.get` → `votes += 1` → `save()` → `redirect` 到 results。
- `results` 视图用 `render` 返回真实数据，不再返回字符串。
- `detail` 去掉多余写法（现在同时用了 `try/except` 和 `get_object_or_404`，留后者）。
- 收尾标准：`manage.py check` 无错，四个页面在浏览器里都通。

### Day 2：Part 5 测试 + Part 6 静态文件

- 给 `was_published_recently()` 写测试，覆盖“未来时间”和“一天前”两种边界。
- 用 `self.client.get(...)` 测 index 视图；写完跑 `manage.py test polls`，要求全绿。
- 加一个最小 `static/polls/style.css`，理解 `{% static %}` 和 `STATICFILES_DIRS`。
- 收尾标准：测试全绿，样式真的生效。

### Day 3：Part 7 后台

- `admin.py` 里加 `list_display`、`list_filter`、`search_fields`、`admin.site.register` 的自定义。
- 重点理解：“Flask 里要自己搭的后台，Django 自带”到底自带到什么程度。
- 顺手看 Part 8（装包复用 app），看懂即可，不用实操。

### Day 4：对照练习（最关键的一天）

新建 `django-practice/`（**不要动本项目代码**），只搬本项目文档模块的三样东西：

1. `DocumentCategory` / `Document` / `DocumentVersion` 三个模型，含外键。
2. 在 Django Admin 里能增删改。
3. 一个 JSON 列表接口（用 `JsonResponse`）+ 一个文件上传接口。

这一天做完，你就能回答“同一个业务，Flask 怎么写、Django 怎么写”了。前三天是读书，这一天才是学会。

### Day 5：复盘 + 沉淀

- 把踩到的坑和想通的点补进 `docs/django-vs-flask.md`（比如迁移、Admin、`urls.py` 分层、ORM 查询写法）。
- 用一页纸回答：Django 帮你省了什么、约束了你什么、为什么本项目最终还是选 Flask。
- 收尾标准：`manage.py test` 全绿 + 一页对照笔记。

## 3. 卡住时的提问模板（直接抄）

```text
环境：.django-learning，Django 版本 x.y
文件：djangotutorial/polls/views.py 第 N 行
现象：（完整贴出报错，包含最后几行 traceback）
期望：应该显示 xxx
已试过：xxx
```

一条消息只问一个问题，问“怎么修”而不是“为什么不行”。

## 4. 零成本的教材（优先用这些）

| 资源 | 用法 |
| --- | --- |
| Django 官方教程（中文） | `docs.djangoproject.com/zh-hans/5.x/intro/tutorial01/`，共 8 篇，按顺序做 |
| `manage.py help` | 忘了命令就查它，比问人快 |
| `manage.py check` | 每次改完模型/配置先跑一遍 |
| `manage.py shell` | 直接试 ORM 查询，比猜快 |
| 报错的 traceback 最后三行 | 大部分问题自己就能定位 |

## 5. 每天收尾五行

写进 `docs/worklog-YYYY-MM-DD.md`，方便随时把会话丢掉：

```text
今天做了什么：
产出文件：
报错与结论：
明天第一件事：
待确认：
```

## 6. 什么时候值得花 token 找人

值得：看了二十分钟还是不懂的报错、概念对照（“Flask 的 x 在 Django 里叫什么”）、一次性的脚手架或检查清单、方案取舍。

不值得：改写报错、查文档在哪一页、问某个函数下一行怎么写——这些查官方文档更快也更省。
