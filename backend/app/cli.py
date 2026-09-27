from pathlib import Path
from urllib.parse import urlsplit

import click
from flask import current_app
from werkzeug.security import generate_password_hash

from . import db
from .models import Document, DocumentCategory, DocumentVersion, User


def register_commands(app):
    @app.cli.command("seed")
    def seed():
        """Create demo users, categories and one sample document."""
        db.create_all()

        admin = User.query.filter_by(username="admin").first()
        if admin is None:
            admin = User(username="admin", name="管理员", role="admin")
            admin.password_hash = generate_password_hash("admin123")
            db.session.add(admin)

        teacher = User.query.filter_by(username="teacher").first()
        if teacher is None:
            teacher = User(username="teacher", name="胡军成", role="teacher")
            teacher.password_hash = generate_password_hash("teacher123")
            db.session.add(teacher)

        viewer = User.query.filter_by(username="viewer").first()
        if viewer is None:
            viewer = User(username="viewer", name="王老师", role="teacher")
            viewer.password_hash = generate_password_hash("viewer123")
            db.session.add(viewer)

        db.session.flush()

        category_names = [
            "专业培养计划",
            "教学大纲",
            "毕业设计要求",
            "考核分析报告",
            "其他",
        ]
        categories = []
        for order, name in enumerate(category_names):
            category = DocumentCategory.query.filter_by(name=name).first()
            if category is None:
                category = DocumentCategory(name=name, sort_order=order)
                db.session.add(category)
            categories.append(category)

        db.session.flush()

        sample = Document.query.filter_by(
            title="2026级计算机科学与技术专业培养计划"
        ).first()
        if sample is None:
            sample = Document(
                title="2026级计算机科学与技术专业培养计划",
                category=categories[0],
                owner=teacher,
            )
            db.session.add(sample)
            db.session.flush()

            media_dir = Path(app.config["UPLOAD_FOLDER"])
            media_dir.mkdir(parents=True, exist_ok=True)
            stored_name = "sample_program_v1.txt"
            (media_dir / stored_name).write_text(
                "示例文档：这是文档管理模块的样例内容。",
                encoding="utf-8",
            )
            version = DocumentVersion(
                document=sample,
                version_number=1,
                filename="2026级培养计划_v1.txt",
                file_path=stored_name,
                changelog="初始版本",
                uploader=teacher,
            )
            db.session.add(version)

        db.session.commit()
        print("Seed completed.")
        print("Accounts: admin/admin123, teacher/teacher123, viewer/viewer123")

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
