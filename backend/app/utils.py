from flask import g, has_request_context, jsonify


def api_success(data=None, status=200):
    return jsonify({"data": data}), status


def api_error(message, code="bad_request", status=400):
    error = {"code": code, "message": message}
    if has_request_context():
        request_id = getattr(g, "request_id", "")
        if request_id:
            error["request_id"] = request_id
    return jsonify({"error": error}), status


def format_size_limit(limit_bytes):
    """把字节上限转成可读文案（如 50 MB / 1 KB），用于超限提示。"""
    try:
        limit = int(limit_bytes)
    except (TypeError, ValueError):
        return ""
    if limit <= 0:
        return ""
    if limit % (1024 * 1024) == 0:
        return f"{limit // (1024 * 1024)} MB"
    if limit % 1024 == 0:
        return f"{limit // 1024} KB"
    return f"{limit} B"
