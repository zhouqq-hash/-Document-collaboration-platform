from flask import Blueprint, current_app, request
from flask_login import current_user, login_required, login_user, logout_user

from .models import User
from .utils import api_error, api_success

#创建蓝图
bp = Blueprint("auth", __name__, url_prefix="/api/auth")

@bp.get("/config")
def config():
    """Expose only non-secret login UI switches."""
    demo_credentials = []
    if current_app.config.get("SHOW_DEMO_CREDENTIALS"):
        demo_credentials = [
            {"username": "admin", "password": "admin123", "role": "管理员"},
            {"username": "teacher", "password": "teacher123", "role": "负责人"},
            {"username": "viewer", "password": "viewer123", "role": "普通教师"},
        ]
    return api_success({"demo_credentials": demo_credentials})

#登录接口
@bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    user = User.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return api_error("用户名或密码错误", "invalid_credentials", 401)

    login_user(user)
    return api_success(user.to_dict())

#登出接口
@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return "", 204

#当前用户接口
@bp.get("/me")
@login_required
def me():
    return api_success(current_user.to_dict())
