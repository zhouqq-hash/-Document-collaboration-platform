"""调用 Cosmos 模型推理平台（OpenAI 兼容接口）。

平台所有模型共用 ``{COSMOS_API_BASE}/chat/completions`` 一个出口，用请求体里的
``model`` 字段区分调用哪个模型。这个模块只负责两件事：读配置、发一次请求，
再把平台返回的错误码翻译成能直接给用户看的中文提示。

配置优先级：Flask 的 ``app.config`` > 环境变量 > 默认值，所以 Web 请求和独立脚本
都能直接复用。
"""
import os

import requests
from flask import current_app, has_app_context


class AIError(Exception):
    """调用大模型失败。message 是可以直接展示给用户的中文说明。"""


DEFAULT_API_BASE = "https://api.siliconflow.cn/v1"
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4-Flash"

# 手册附录 B 的错误码 -> 处理建议
_STATUS_HINTS = {
    401: "API Key 无效或缺失，请检查 COSMOS_API_KEY",
    402: "账户余额不足，请先充值",
    403: "这个 Key 没有授权调用该模型，请在「调用管理」里扩大生效模型",
    404: "模型路由不存在，请核对 COSMOS_MODEL，或用 /v1/models 查看可用模型",
    429: "超出每日 token 配额，请调整配额或次日再试",
    503: "没有可用的后端服务，请确认模型已运行",
}


def _setting(name, default=None):
    """先读 Flask 配置，再读环境变量，最后回落到默认值。"""
    if has_app_context():
        value = current_app.config.get(name)
        if value not in (None, ""):
            return value
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _api_base():
    base = _setting("COSMOS_API_BASE", DEFAULT_API_BASE) or DEFAULT_API_BASE
    return base.rstrip("/")


def _api_key():
    key = _setting("COSMOS_API_KEY", "")
    if not key:
        raise AIError("没有配置 COSMOS_API_KEY，无法调用大模型")
    return key


def is_configured():
    """是否配了 API Key。没配时调用会直接报错，界面据此做降级提示。"""
    return bool(_setting("COSMOS_API_KEY", ""))


def _timeout(name, fallback):
    try:
        return int(_setting(name, fallback))
    except (TypeError, ValueError):
        return int(fallback)


def _headers():
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


def _error_message(response):
    """把平台的 OpenAI 风格错误转成中文提示。"""
    hint = _STATUS_HINTS.get(response.status_code, "调用大模型失败")
    detail = ""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            detail = error.get("message") or ""
        elif isinstance(error, str):
            detail = error
    suffix = f"（{detail}）" if detail else ""
    return f"{hint}，HTTP {response.status_code}{suffix}"


def list_models(timeout=None):
    """GET /v1/models：快速验证 Key 是否有效，返回 Key 可用的模型名列表。"""
    wait = timeout or _timeout("COSMOS_QA_TIMEOUT", 120)
    try:
        response = requests.get(
            f"{_api_base()}/models", headers=_headers(), timeout=wait
        )
    except requests.Timeout as exc:
        raise AIError(f"请求超时（{wait} 秒），请稍后重试") from exc
    except requests.RequestException as exc:
        raise AIError(f"连接模型平台失败：{exc}") from exc

    if response.status_code != 200:
        raise AIError(_error_message(response))

    try:
        payload = response.json()
        return [
            item["id"]
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        ]
    except (ValueError, TypeError, AttributeError) as exc:
        raise AIError("模型列表返回内容无法解析") from exc


def chat(messages, *, model=None, temperature=0.7, max_tokens=None, timeout=None):
    """发一次对话请求，返回模型回复的纯文本。

    ``messages`` 是 OpenAI 格式的消息列表，例如
    ``[{"role": "user", "content": "这份文件讲了什么？"}]``。
    """
    if not messages:
        raise AIError("messages 不能为空")

    payload = {
        "model": model or _setting("COSMOS_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)

    wait = timeout or _timeout("COSMOS_QA_TIMEOUT", 120)

    try:
        response = requests.post(
            f"{_api_base()}/chat/completions",
            json=payload,
            headers=_headers(),
            timeout=wait,
        )
    except requests.Timeout as exc:
        raise AIError(f"调用大模型超时（{wait} 秒），请稍后重试") from exc
    except requests.RequestException as exc:
        raise AIError(f"连接模型平台失败：{exc}") from exc

    if response.status_code != 200:
        raise AIError(_error_message(response))

    try:
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AIError("大模型返回内容无法解析") from exc
