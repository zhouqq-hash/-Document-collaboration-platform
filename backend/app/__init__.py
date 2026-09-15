from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

from .config import BASE_DIR, Config


db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def create_app(config=None):
    app = Flask(__name__)
#加载配置
    if isinstance(config, dict):
        app.config.from_mapping(config)
    else:
        app.config.from_object(config or Config)
        Path(BASE_DIR / "instance").mkdir(parents=True, exist_ok=True)
#准备上传目录和其他路径
    upload_folder = Path(app.config.get("UPLOAD_FOLDER", Config.UPLOAD_FOLDER))
    upload_folder.mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = str(upload_folder)
    migrations_dir = str(Path(__file__).resolve().parent.parent / "db_migrations")
    prototype_dir = Path(__file__).resolve().parent.parent.parent / "prototype"
#绑定 Flask 扩展
    db.init_app(app)
    migrate.init_app(app, db, directory=migrations_dir)
    login_manager.init_app(app)
#登录用户加载函数
    from .models import User
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))
#未登录时的统一响应
    @login_manager.unauthorized_handler
    def unauthorized():
        return (
            jsonify(
                {
                    "error": {
                        "code": "unauthorized",
                        "message": "请先登录",
                    }
                }
            ),
            401,
        )
#注册业务模块
    from . import auth, cli, documents

    app.register_blueprint(auth.bp)
    app.register_blueprint(documents.bp)
    cli.register_commands(app)
#健康检查接口
    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})
#托管前端原型（静态文件）
    @app.get("/")
    def prototype_index():
        return send_from_directory(prototype_dir, "index.html")

    @app.get("/<path:filename>")
    def prototype_static(filename):
        return send_from_directory(prototype_dir, filename)

    return app