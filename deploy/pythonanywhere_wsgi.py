# PythonAnywhere 的 WSGI 配置模板
#
# 用法：把本文件的内容复制到 PythonAnywhere 的 WSGI 配置文件里
#   /var/www/<你的用户名>_pythonanywhere_com_wsgi.py
# 然后改两处：
#   1) PROJECT_ROOT 改成仓库在你账号里的位置
#   2) SECRET_KEY 换成你自己的一串随机字符
#
# 这个文件本身只是模板，真实密钥写在你账号的 /var/www/ 下，不会进仓库。

import os
import sys

# 仓库位置（PythonAnywhere 上的绝对路径）
PROJECT_ROOT = os.path.expanduser("~/doc-collab")
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

# 生产环境密钥：必须在 import app 之前设置（config.py 在导入时读取）
os.environ.setdefault("SECRET_KEY", "在这里填一串你自己的随机字符串")
# 微信走演示模式：不配 WECHAT_APP_ID 就是演示模式，免费版外网受限，真机联调走不通。
# AI 问答/自动预审需要外网，免费版也用不了，保持默认即可。

# 让 `from app import create_app` 能找到包，等同于本地 `python backend/run.py`
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app import create_app  # noqa: E402

# PythonAnywhere 认 application 这个变量名
application = create_app()
