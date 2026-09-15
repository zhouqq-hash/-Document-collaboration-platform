from flask import jsonify


def api_success(data=None, status=200):
    return jsonify({"data": data}), status


def api_error(message, code="bad_request", status=400):
    return jsonify({"error": {"code": code, "message": message}}), status
