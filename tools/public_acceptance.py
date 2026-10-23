"""Two-phase acceptance check for a deployed document collaboration service.

Example:
  1. Run ``--phase create`` before restarting the service.
  2. Restart the deployed service.
  3. Run ``--phase verify --cleanup`` after it becomes ready.
"""

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

import requests


def _arg_or_env(value, name):
    resolved = value or os.environ.get(name, "")
    if not resolved:
        raise SystemExit(f"缺少 {name}")
    return resolved


def _password(env_name, prompt):
    value = os.environ.get(env_name, "")
    return value or getpass.getpass(prompt)


def _check_response(response, expected, action):
    if response.status_code not in expected:
        detail = response.text[:1000]
        raise RuntimeError(
            f"{action}失败：HTTP {response.status_code} {detail}"
        )
    if not response.content:
        return None
    return response.json()


def _data(response, expected, action):
    payload = _check_response(response, expected, action)
    return payload.get("data") if payload else None


def login(base_url, username, password):
    session = requests.Session()
    response = session.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password},
        timeout=20,
    )
    _data(response, {200}, f"账号 {username} 登录")
    if base_url.startswith("https://"):
        cookie = response.headers.get("Set-Cookie", "")
        for expected in ("Secure", "HttpOnly", "SameSite=Lax"):
            if expected.lower() not in cookie.lower():
                raise RuntimeError(f"HTTPS 登录 Cookie 缺少 {expected}")
    return session


def public_checks(base_url):
    health = requests.get(f"{base_url}/api/health", timeout=20)
    _check_response(health, {200}, "存活检查")
    ready = requests.get(f"{base_url}/api/ready", timeout=30)
    ready_payload = _check_response(ready, {200}, "就绪检查")
    if ready_payload.get("status") != "ready":
        raise RuntimeError("就绪检查未返回 ready")

    config = _data(
        requests.get(f"{base_url}/api/auth/config", timeout=20),
        {200},
        "登录配置",
    )
    if config["demo_credentials"]:
        raise RuntimeError("公网登录页仍暴露演示凭据")


def load_state(path):
    state_path = Path(path)
    if not state_path.exists():
        raise SystemExit(f"验收状态文件不存在：{state_path}")
    return json.loads(state_path.read_text(encoding="utf-8"))


def create_marker(base_url, admin, marker, state_path):
    existing = _data(
        admin.get(f"{base_url}/api/tables", params={"q": marker}, timeout=20),
        {200},
        "查询验收表格",
    )
    if any(item["name"] == marker for item in existing):
        raise RuntimeError(f"验收标记已存在：{marker}")

    table = _data(
        admin.post(
            f"{base_url}/api/tables",
            json={
                "name": marker,
                "description": "公网持久化验收标记，可安全删除",
                "columns": ["验收项", "结果"],
            },
            timeout=20,
        ),
        {201},
        "创建验收表格",
    )
    row = _data(
        admin.post(
            f"{base_url}/api/tables/{table['id']}/rows",
            json={"cells": {"col1": "重启检查", "col2": marker}},
            timeout=20,
        ),
        {201},
        "写入验收数据",
    )
    state = {
        "base_url": base_url,
        "marker": marker,
        "table_id": table["id"],
        "row_key": row["row"]["row_key"],
    }
    output = Path(state_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已创建持久化标记：table_id={table['id']} marker={marker}")
    print("现在重启部署服务，再执行 verify。")


def verify_marker(base_url, admin, teacher, state):
    table_id = state["table_id"]
    table = _data(
        admin.get(f"{base_url}/api/tables/{table_id}", timeout=20),
        {200},
        "读取重启后的验收表格",
    )
    assert table["name"] == state["marker"]
    row = next(
        item
        for item in table["rows"]
        if item["row_key"] == state["row_key"]
    )
    if row["cells"]["col2"] != state["marker"]:
        raise RuntimeError("重启后验收表格内容不一致")

    denied = teacher.patch(
        f"{base_url}/api/tables/{table_id}",
        json={"name": state["marker"] + "-越权"},
        timeout=20,
    )
    _check_response(denied, {403}, "普通教师修改表格")
    if denied.json()["error"]["code"] != "permission_denied":
        raise RuntimeError("越权修改返回了错误的错误码")

    denied_delete = teacher.delete(
        f"{base_url}/api/tables/{table_id}", timeout=20
    )
    _check_response(denied_delete, {403}, "普通教师删除表格")
    print("重启后数据仍存在，普通教师越权修改/删除均被 403 拦截。")


def cleanup_marker(base_url, admin, state):
    response = admin.delete(
        f"{base_url}/api/tables/{state['table_id']}", timeout=20
    )
    _check_response(response, {204}, "清理验收表格")
    Path(state["state_path"]).unlink(missing_ok=True)
    print("验收表格已清理。")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--phase", choices=("create", "verify"), required=True)
    parser.add_argument("--marker", default="public-persistence-smoke")
    parser.add_argument(
        "--state",
        default="testdata/public-acceptance.json",
    )
    parser.add_argument("--admin-user", default="")
    parser.add_argument("--teacher-user", default="")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    public_checks(base_url)
    admin = login(
        base_url,
        _arg_or_env(args.admin_user, "ACCEPTANCE_ADMIN_USER"),
        _password("ACCEPTANCE_ADMIN_PASSWORD", "管理员密码："),
    )

    if args.phase == "create":
        create_marker(base_url, admin, args.marker, args.state)
        return

    state = load_state(args.state)
    if state["base_url"] != base_url:
        raise SystemExit("验收状态文件对应的公网地址不一致")
    teacher = login(
        base_url,
        _arg_or_env(args.teacher_user, "ACCEPTANCE_TEACHER_USER"),
        _password("ACCEPTANCE_TEACHER_PASSWORD", "教师密码："),
    )
    verify_marker(base_url, admin, teacher, state)
    if args.cleanup:
        state["state_path"] = args.state
        cleanup_marker(base_url, admin, state)


if __name__ == "__main__":
    try:
        main()
    except (requests.RequestException, RuntimeError, AssertionError) as exc:
        print(f"验收失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc
