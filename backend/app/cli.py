import os
import shutil
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

import click
from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from . import db, review_templates
from .models import (
    Document,
    DocumentAiReview,
    DocumentCategory,
    DocumentVersion,
    QaStatement,
    QaTopic,
    QaTopicCategory,
    Table,
    TableVersion,
    User,
)


DEMO_CATEGORIES = [
    "专业培养计划",
    "教学大纲",
    "毕业设计要求",
    "考核分析报告",
    "其他",
]

DEMO_SCENARIO_DIR = (
    Path(__file__).resolve().parent.parent
    / "demo_data"
    / "ai_review_scenario"
)

# 场景围绕数据库课程大纲审核展开，参考文献是分类的默认审核规范。
# 整改稿 v2 只作为上传素材，不加入初始数据，确保可以现场走完整闭环。
DEMO_DOCUMENTS = [
    {
        "title": "2026级数据科学与大数据技术专业培养方案",
        "category": "专业培养计划",
        "owner": "teacher",
        "status": "archived",
        "stored_name": "scenario_program_plan_v1.docx",
        "filename": "2026级数据科学与大数据技术专业培养方案.docx",
        "source_file": "01_2026级数据科学与大数据技术专业培养方案.docx",
        "description": "数据库课程大纲的上位培养依据，规定培养目标、毕业要求与学分结构。",
        "changelog": "2026 级培养方案初始版本",
    },
    {
        "title": "数据科学与大数据技术专业毕业要求指标点（2026版）",
        "category": "专业培养计划",
        "owner": "teacher",
        "status": "active",
        "stored_name": "scenario_indicator_map_v1.docx",
        "filename": "数据科学与大数据技术专业毕业要求指标点_2026版.docx",
        "source_file": "02_数据科学与大数据技术专业毕业要求指标点_2026版.docx",
        "description": "课程目标与毕业要求指标点映射的审核依据。",
        "changelog": "发布 2026 版毕业要求指标点",
    },
    {
        "title": "数据库原理及应用课程教学大纲编写规范（2026版）",
        "category": "教学大纲",
        "owner": "admin",
        "status": "active",
        "stored_name": "scenario_syllabus_spec_v1.docx",
        "filename": "数据库原理及应用课程教学大纲编写规范_2026版.docx",
        "source_file": "03_数据库原理及应用课程教学大纲编写规范_2026版.docx",
        "description": "规定大纲必填章节、学时计算、目标映射和考核比例。",
        "changelog": "发布 2026 版编写规范",
    },
    {
        "title": "数据库原理及应用课程教学大纲（待审核）",
        "category": "教学大纲",
        "owner": "teacher",
        "status": "active",
        "stored_name": "scenario_syllabus_v1.docx",
        "filename": "数据库原理及应用课程教学大纲_待审核_v1.docx",
        "source_file": "04_数据库原理及应用课程教学大纲_待审核_v1.docx",
        "description": "首次提交审核的课程大纲，包含学时、考核比例和团队目标考核缺口。",
        "changelog": "首次提交审核",
    },
    {
        "title": "2025-2026学年第二学期数据库原理及应用课程考核分析报告",
        "category": "考核分析报告",
        "owner": "admin",
        "status": "deprecated",
        "stored_name": "scenario_assessment_report_v1.docx",
        "filename": "数据库原理及应用课程考核分析报告.docx",
        "source_file": "06_数据库原理及应用课程考核分析报告.docx",
        "description": "上一轮课程考核与目标达成情况归档，供新一轮大纲修订参考。",
        "changelog": "上一轮课程考核分析归档",
    },
]

DEMO_ACCOUNTS = [
    ("admin", "管理员", "admin", "admin123"),
    ("teacher", "胡军成", "teacher", "teacher123"),
    ("viewer", "王老师", "teacher", "viewer123"),
]

# 问答模块演示数据：一个已经形成初步统一意见，一个还在讨论中
DEMO_QA_TOPICS = [
    {
        "title": "毕业设计要求是否增加中期检查",
        "description": "讨论是否在毕业设计过程中增加一次中期检查，以及检查的时间点。",
        "category": "毕业设计",
        "creator": "admin",
        "status": "open",
        "statements": [
            ("teacher", "agree", "建议增加，能提前发现问题，避免最后集中返工。"),
            ("other", "agree", "同意，中期检查放在第 8 周比较合适。"),
            ("viewer", "agree", "支持，对过程管理有帮助。"),
        ],
    },
    {
        "title": "课程考核分析报告的提交时间是否调整",
        "description": "讨论本学年课程考核分析报告的提交截止时间是否需要提前。",
        "category": "课程考核",
        "document": "2025-2026学年第二学期数据库原理及应用课程考核分析报告",
        "creator": "teacher",
        "status": "open",
        "statements": [
            ("teacher", "agree", "建议提前到第 16 周，给后续汇总留时间。"),
            ("other", "disagree", "第 18 周更稳妥，教师期末工作已经很多。"),
            ("viewer", "neutral", "两种方案都行，最终以教务安排为准。"),
        ],
    },
]

DEMO_QA_CATEGORIES = [
    "教学安排",
    "课程考核",
    "毕业设计",
    "其他",
]

DEMO_QA_STATEMENT_USERS = {
    "admin": "admin",
    "teacher": "teacher",
    "other": "viewer",
    "viewer": "viewer",
}

# 表格协作模块演示数据：一张带示例行列的进度表，方便直接演示行内编辑与回滚
DEMO_TABLES = [
    {
        "name": "2026届毕业设计进度表",
        "description": "用于跟踪各组毕业设计选题与进度的协作表格。",
        "owner": "teacher",
        "columns": ["组号", "题目", "成员", "进度"],
        "rows": [
            {"cells": {"组号": "1", "题目": "在线文档协作平台", "成员": "张三、李四", "进度": "需求分析"}},
            {"cells": {"组号": "2", "题目": "教学问答系统", "成员": "王五", "进度": "原型设计"}},
        ],
    },
]


def _save_demo_file(app, stored_name, content):
    """演示文件也走存储抽象层。

    直接写本地目录的话，切到 COS 后示例文档的 file_path 指向的对象并不在桶里，
    下载就会 500 —— 演示数据必须和真实上传走同一条存储路径。
    """
    app.extensions["storage"].save(
        FileStorage(stream=BytesIO(content), filename=stored_name),
        stored_name,
    )


def seed_demo_data(app):
    """写入演示账号、分类和文档。已存在的记录不重复创建，可以反复执行。"""
    db.create_all()

    users = {}
    for username, name, role, password in DEMO_ACCOUNTS:
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(username=username, name=name, role=role)
            user.password_hash = generate_password_hash(password)
            db.session.add(user)
        users[username] = user

    db.session.flush()

    categories = {}
    for order, name in enumerate(DEMO_CATEGORIES):
        category = DocumentCategory.query.filter_by(name=name).first()
        if category is None:
            category = DocumentCategory(name=name, sort_order=order)
            db.session.add(category)
        category.review_template_key = (
            "syllabus_v1" if name == "教学大纲"
            else review_templates.GENERIC_TEMPLATE_KEY
        )
        categories[name] = category

    qa_categories = {}
    for order, name in enumerate(DEMO_QA_CATEGORIES):
        category = QaTopicCategory.query.filter_by(name=name).first()
        if category is None:
            category = QaTopicCategory(name=name, sort_order=order)
            db.session.add(category)
        qa_categories[name] = category

    db.session.flush()

    demo_documents = {}
    for spec in DEMO_DOCUMENTS:
        document = Document.query.filter_by(title=spec["title"]).first()
        if document is None:
            owner = users[spec["owner"]]
            document = Document(
                title=spec["title"],
                category=categories[spec["category"]],
                owner=owner,
                status=spec["status"],
            )
            document.description = spec["description"]
            db.session.add(document)
            db.session.flush()

            content = (DEMO_SCENARIO_DIR / spec["source_file"]).read_bytes()
            _save_demo_file(app, spec["stored_name"], content)
            db.session.add(
                DocumentVersion(
                    document=document,
                    version_number=1,
                    filename=spec["filename"],
                    file_path=spec["stored_name"],
                    changelog=spec["changelog"],
                    uploader=owner,
                )
            )
        else:
            document.description = spec["description"]
        demo_documents[spec["title"]] = document

    syllabus_category = categories["教学大纲"]
    spec_document = demo_documents[
        "数据库原理及应用课程教学大纲编写规范（2026版）"
    ]
    indicator_document = demo_documents[
        "数据科学与大数据技术专业毕业要求指标点（2026版）"
    ]
    syllabus_category.default_spec_document_ids = [
        indicator_document.id,
        spec_document.id,
    ]

    for spec in DEMO_QA_TOPICS:
        topic = QaTopic.query.filter_by(title=spec["title"]).first()
        if topic is None:
            topic = QaTopic(
                title=spec["title"],
                description=spec["description"],
                creator=users[spec["creator"]],
                category=qa_categories[spec["category"]],
                document=demo_documents.get(spec.get("document")),
                status=spec["status"],
            )
            db.session.add(topic)
            db.session.flush()

            for username_key, position, content in spec["statements"]:
                db.session.add(
                    QaStatement(
                        topic=topic,
                        author=users[DEMO_QA_STATEMENT_USERS[username_key]],
                        position=position,
                        content=content,
                    )
                )
        else:
            if topic.category_id is None:
                topic.category = qa_categories[spec["category"]]
            if topic.document_id is None:
                topic.document = demo_documents.get(spec.get("document"))

    for spec in DEMO_TABLES:
        table = Table.query.filter_by(name=spec["name"]).first()
        if table is None:
            columns = [
                {"key": f"col{index + 1}", "name": name, "type": "text"}
                for index, name in enumerate(spec["columns"])
            ]
            rows = []
            for index, row_spec in enumerate(spec["rows"]):
                cells = {}
                for col_index, name in enumerate(spec["columns"]):
                    cells[f"col{col_index + 1}"] = row_spec["cells"].get(name, "")
                rows.append({"row_key": f"r{index + 1}", "cells": cells})
            table = Table(
                name=spec["name"],
                description=spec["description"],
                owner=users[spec["owner"]],
                columns=columns,
                rows=rows,
                row_seq=len(rows),
                version_number=1,
            )
            db.session.add(table)
            db.session.flush()
            db.session.add(
                TableVersion(
                    table=table,
                    version_number=1,
                    snapshot={"columns": columns, "rows": rows},
                    changelog="创建表格",
                    editor=users[spec["owner"]],
                )
            )

    db.session.commit()


def register_commands(app):
    @app.cli.command("seed")
    def seed():
        """Create demo users, categories and sample documents (idempotent)."""
        seed_demo_data(app)
        print("Seed completed.")
        print("Accounts: admin/admin123, teacher/teacher123, viewer/viewer123")
        print("Documents: 5 scenario documents (program, indicators, spec, draft, report)")
        print("AI review: draft starts unreviewed; revised v2 is ready for upload")
        print("Q&A topics: 2 (one consensus reached, one under discussion)")
        print("Tables: 1 (graduation project progress)")

    @app.cli.command("demo-reset")
    @click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
    @click.option(
        "--keep-media",
        is_flag=True,
        help="Reset the database only and keep uploaded files.",
    )
    def demo_reset(yes, keep_media):
        """Reset the demo environment: wipe the database and uploads, then seed again.

        测试同学跑完一轮后执行这条命令，下一轮就能从同样的初始状态开始。
        """
        if not yes:
            click.confirm(
                "This will erase the database and uploaded files. Continue?",
                abort=True,
            )

        media_dir = Path(app.config["UPLOAD_FOLDER"])
        removed = 0
        if not keep_media and media_dir.exists():
            for item in sorted(media_dir.iterdir()):
                if item.name == ".gitkeep":
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                removed += 1

        db.session.remove()
        db.drop_all()
        db.create_all()
        seed_demo_data(app)

        print("Demo environment reset. Database and demo data are back to the initial state.")
        if not keep_media:
            print(f"Removed {removed} item(s) from {media_dir}")
        if str(app.config.get("STORAGE_BACKEND") or "local").lower() == "cos":
            print(
                "Note: files already stored in COS are not deleted; "
                "the five scenario objects are overwritten."
            )
        print("Accounts: admin/admin123, teacher/teacher123, viewer/viewer123")
        print("Documents: 5 database-course review scenario documents")
        print("AI review: draft intentionally starts unreviewed")
        print("Q&A topics: 2 (one consensus reached, one under discussion)")
        print("Tables: 1 (graduation project progress)")

    @app.cli.command("wechat-check")
    def wechat_check():
        """检查微信登录配置（不联网），列出参数和需要注意的问题。"""
        from . import wechat

        report = wechat.config_report()
        print("微信登录配置自检")
        print(f"  模式         : {report['mode']}")
        print(f"  AppID        : {report['app_id'] or '（未配置）'}")
        print(
            "  AppSecret    : "
            f"{'已配置' if report['app_secret_configured'] else '未配置'}"
        )
        print(
            f"  授权方式     : {report['authorize_mode']}"
            f"（scope: {report['scope'] or '按模式默认'}）"
        )
        print(f"  回调地址     : {report['redirect_uri'] or '（未配置）'}")
        print(f"  演示模式     : {'开启' if report['mock_enabled'] else '关闭'}")
        if report.get("entry_url"):
            print(f"  微信里打开   : {report['entry_url']}")
        if report["authorize_url"]:
            print(f"  授权地址示例 : {report['authorize_url']}")

        for note in report["notes"]:
            print(f"  提示：{note}")

        if report["problems"]:
            print(f"发现 {len(report['problems'])} 个需要处理的问题：")
            for problem in report["problems"]:
                print(f"  [问题] {problem}")
            # Click 不会拿返回值当退出码，必须显式抛出 SystemExit
            raise SystemExit(1)

        print("没有发现配置问题。")

    @app.cli.command("wechat-tunnel")
    @click.option(
        "--url",
        "public_url",
        default="",
        help="已知的公网地址；cloudflared 这类没有本地查询接口的隧道直接粘进来",
    )
    def wechat_tunnel(public_url):
        """检测本机的 ngrok / cpolar 隧道，打印联调要填的三处地址。"""
        from . import wechat

        target = (public_url or "").strip()
        if target and not target.startswith(("http://", "https://")):
            target = "https://" + target
        target = target.rstrip("/")

        if target:
            forward_to = ""
        else:
            tunnel = wechat.detect_local_tunnel()
            if tunnel is None:
                print(
                    "没有在本机 4040 端口检测到隧道 API（ngrok / cpolar 默认开在这里）。"
                )
                print("请先启动内网穿透，例如：")
                print("  cloudflared tunnel --url http://localhost:5000   # 免注册，地址看它自己的输出")
                print("  ngrok http 5000")
                print("  cpolar http 5000")
                print("拿到地址后可以直接带参数重跑：")
                print("  python -m flask --app backend\\run.py wechat-tunnel --url https://你的地址")
                raise SystemExit(1)
            target = tunnel["public_url"]
            forward_to = tunnel["addr"] or "（未提供）"

        redirect_uri = f"{target}/api/auth/wechat/callback"
        entry_url = f"{target}/documents/index.html"
        host = urlsplit(target).hostname or ""
        current = (current_app.config.get("WECHAT_REDIRECT_URI") or "").strip()

        print("本次使用的公网地址")
        print(f"  公网地址     : {target}")
        if forward_to:
            print(f"  转发目标     : {forward_to}")
        if target.startswith("http://"):
            print("  [提醒] 这是 http 地址，建议换成 https，微信对 http 回调不友好。")
        print()
        print("1) 在 PowerShell 里设置，然后重启后端：")
        print(f'   $env:WECHAT_REDIRECT_URI = "{redirect_uri}"')
        print('   $env:WECHAT_AUTHORIZE_MODE = "mp"    # 测试号 / 公众号；开放平台网站应用填 open')
        print()
        print("2) 微信后台（测试号：网页服务 → 网页账号 → 网页授权获取用户基本信息 → 修改）里的域名：")
        print(f"   {host}")
        print("   只填域名，不带 http://、不带路径和端口。")
        print()
        print("3) 在微信里打开这个地址，再点页面上的「微信登录」：")
        print(f"   {entry_url}")

        if current and current != redirect_uri:
            print()
            print("[提醒] 当前 WECHAT_REDIRECT_URI 和检测到的隧道不一致，微信会报 redirect_uri 参数错误：")
            print(f"  现在：{current}")
            print(f"  应为：{redirect_uri}")

    @app.cli.command("wechat-log")
    @click.option("--lines", default=30, show_default=True, help="显示最后多少行")
    def wechat_log(lines):
        """打印最近的微信登录事件，排查「登录失败」用。"""
        from . import wechat

        path = wechat.event_log_path()
        if not path.exists():
            print(f"还没有事件日志：{path}")
            print("先在微信 / 页面里走一次登录，再回来执行本命令。")
            raise SystemExit(1)

        print(f"事件日志：{path}")
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in content[-int(lines) :]:
            print(f"  {line}")
        print()
        print("怎么看：")
        print("  callback ... session_state=-      → 回调时 session 里没有 state（域名/浏览器不一致，或换过设备）")
        print("  callback-state-mismatch           → state 对不上，重新从登录页点一次")
        print("  callback-wechat-api-error         → 微信侧报错，看后面的 errcode（40029 code 已用过、40001 AppSecret 不对）")
        print("  callback-login                    → 登录/绑定成功，user_id 就是登录进去的账号")

    @app.cli.command("wechat-token-test")
    def wechat_token_test():
        """用配置里的 AppID / AppSecret 换一次 access_token，验证凭据是否配对。"""
        from . import wechat

        if wechat.current_mode() != "live":
            print("当前不是真实模式（没配 WECHAT_APP_ID / WECHAT_APP_SECRET），不用测凭据。")
            raise SystemExit(1)

        print(f"用 AppID {wechat.config_report()['app_id']} 向微信换取 access_token ...")
        result = wechat.check_credentials()
        if result["ok"]:
            print(f"凭据正常：拿到 access_token {result['token']}（有效期 {result.get('expires_in')} 秒）")
            print("说明 AppID / AppSecret 是配对的，登录失败多半出在域名、state 或 code 复用上。")
            return

        print(f"凭据有问题：{result['reason']}")
        print("常见 errcode 对照：")
        print("  40001 invalid credential  → AppSecret 复制错了，或者和 AppID 不是同一个账号")
        print("  40013 invalid appid      → AppID 不合法 / 复制时多了空格")
        print("  40164 invalid ip         → 公众号后台配了 IP 白名单，当前出口 IP 不在里面")
        print("  45009 api freq out of limit → 调用太频繁，等一会儿再试")
        raise SystemExit(1)

    @app.cli.command("bootstrap-admin")
    @click.option(
        "--username",
        default=lambda: os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "admin"),
        show_default=True,
    )
    @click.option("--name", default="系统管理员", show_default=True)
    @click.option("--password", default=lambda: os.environ.get("BOOTSTRAP_ADMIN_PASSWORD"))
    def bootstrap_admin(username, name, password):
        """Create the first administrator without loading public demo data."""
        username = (username or "").strip()
        password = password or ""
        if not username:
            raise click.ClickException(
                "需要 BOOTSTRAP_ADMIN_USERNAME"
            )

        existing = User.query.filter_by(username=username).first()
        if existing is not None:
            if existing.role != "admin":
                raise click.ClickException(
                    f"账号 {username} 已存在，但不是管理员"
                )
            print(f"管理员 {username} 已存在，未修改密码。")
            return
        if not password:
            raise click.ClickException("首次创建需要 BOOTSTRAP_ADMIN_PASSWORD")
        if len(password) < 12:
            raise click.ClickException("管理员密码至少需要 12 个字符")

        user = User(username=username, name=(name or "系统管理员").strip())
        user.role = "admin"
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"已创建管理员 {username}。")

    @app.cli.command("create-user")
    @click.option("--username", required=True)
    @click.option("--name", required=True)
    @click.option(
        "--password",
        help="不填时安全交互输入，避免密码进入 Shell 历史。",
    )
    @click.option(
        "--role",
        type=click.Choice(["teacher", "admin"]),
        default="teacher",
        show_default=True,
    )
    def create_user(username, name, password, role):
        """Provision a teacher or administrator account."""
        username = username.strip()
        name = name.strip()
        if not username or not name:
            raise click.ClickException("工号和姓名不能为空")
        password = password or click.prompt(
            "Password",
            hide_input=True,
            confirmation_prompt=True,
        )
        if len(password) < 12:
            raise click.ClickException("密码至少需要 12 个字符")
        if User.query.filter_by(username=username).first() is not None:
            raise click.ClickException(f"账号 {username} 已存在")

        user = User(username=username, name=name, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"已创建{('管理员' if role == 'admin' else '教师')}账号 {username}。")

    @app.cli.command("doctor")
    @click.option(
        "--strict",
        is_flag=True,
        help="发现阻塞级问题时返回非零退出码。",
    )
    def doctor(strict):
        """检查密钥、持久化、数据库、存储、管理员和 AI 降级配置。"""
        from .operations import run_doctor

        checks = run_doctor(app)
        labels = {"ok": "[正常]", "warning": "[提醒]", "error": "[阻塞]"}
        for item in checks:
            print(
                f"{labels.get(item['level'], '[信息]')} "
                f"{item['name']}：{item['message']}"
            )
        errors = sum(item["level"] == "error" for item in checks)
        warnings = sum(item["level"] == "warning" for item in checks)
        print(f"\n自检完成：{len(checks)} 项，阻塞 {errors}，提醒 {warnings}。")
        if strict and errors:
            raise SystemExit(1)

    @app.cli.command("backup")
    @click.option("--output", type=click.Path(dir_okay=False, path_type=Path))
    @click.option("--force", is_flag=True, help="覆盖已存在的输出文件。")
    def backup(output, force):
        """备份数据库和本地文件，并写入可校验的 manifest。"""
        from .operations import create_backup

        result = create_backup(app, output=output, overwrite=force)
        print(f"备份完成：{result['path']}")
        print(f"数据库：{result['database']['kind']}")
        if result["media"].get("included"):
            print(f"本地文件：{result['media'].get('file_count', 0)} 个")
        if result["media"].get("warning"):
            print(f"[提醒] {result['media']['warning']}")

    @app.cli.command("restore")
    @click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
    @click.option("--yes", is_flag=True, help="跳过确认。")
    def restore(path, yes):
        """恢复备份；恢复前自动再备份一次当前数据。"""
        from .operations import create_backup, inspect_backup, restore_backup

        inspected = inspect_backup(path)
        if not yes:
            click.confirm(
                f"将用 {path} 覆盖当前数据库和本地文件，继续？",
                abort=True,
            )

        safety = create_backup(
            app,
            output=Path(app.config["BACKUP_FOLDER"])
            / f"pre-restore-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.zip",
        )
        restore_backup(app, inspected["path"])
        print(f"恢复完成：{inspected['path']}")
        print(f"恢复前快照：{safety['path']}")
        if not (inspected["manifest"].get("media") or {}).get("included"):
            print("[提醒] 该备份不包含对象存储文件，请同步恢复 COS 对象。")

    @app.cli.command("recover-reviews")
    @click.option("--older-than", default=15, show_default=True, type=int)
    def recover_reviews(older_than):
        """把进程重启后遗留的预审任务标记为失败，允许人工兜底。"""
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=max(older_than, 1)
        )
        reviews = DocumentAiReview.query.filter(
            DocumentAiReview.status.in_(("pending", "running"))
        ).all()
        recovered = 0
        for review in reviews:
            timestamp = review.started_at or review.created_at
            if timestamp is None or timestamp >= cutoff:
                continue
            review.status = "failed"
            review.error_message = (
                "预审任务在进程重启或超时后中断；可重试或由负责人人工兜底"
            )
            review.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            recovered += 1
        db.session.commit()
        print(f"已恢复 {recovered} 条中断的预审任务。")
