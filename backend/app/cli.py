from pathlib import Path

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
        print("Accounts: admin/admin123, teacher/teacher123")
