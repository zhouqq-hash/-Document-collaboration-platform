import os

from app import create_app


app = create_app()


if __name__ == "__main__":
    # 真机联调（内网穿透 / 手机访问局域网 IP）时用环境变量改监听地址：
    #   $env:DOC_COLLAB_HOST = "0.0.0.0"
    host = os.environ.get("DOC_COLLAB_HOST", "127.0.0.1")
    port = int(os.environ.get("DOC_COLLAB_PORT", "5000"))
    app.run(host=host, port=port, debug=True)
