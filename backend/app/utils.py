from flask import jsonify


def api_success(data=None, status=200):
    return jsonify({"data": data}), status


def api_error(message, code="bad_request", status=400):
    return jsonify({"error": {"code": code, "message": message}}), status


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
