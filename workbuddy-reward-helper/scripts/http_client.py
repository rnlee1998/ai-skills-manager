#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
http_client.py — WorkBuddy 积分助手 · 统一 HTTP 客户端

职责：
  - 统一封装带鉴权的 JSON 请求（method / headers / timeout / 错误处理）
  - 供 checkin.py（Buddy加油站签到）与后续 travel.py（Buddy旅行）共用，避免重复

设计：
  - 基于标准库 urllib，无第三方依赖
  - 返回 (http_status, parsed_json)；传输层失败（DNS/连接/超时）抛 HttpTransportError
  - HTTP 错误状态（4xx/5xx）不抛异常，仍尝试解析响应体后原样返回状态码与解析结果，
    由调用方按业务码（如 401 / code=10001）判断
  - 响应体非 JSON 时返回 {"__non_json__": true} 标记，不保留原始报文（避免夹带敏感信息）

安全：
  - token 仅作为请求头在内存中传递，绝不打印、不写日志、不落盘
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

DEFAULT_TIMEOUT = 15
DEFAULT_UA = "WorkBuddy/5.3.14"


class HttpTransportError(RuntimeError):
    """网络传输层失败（未收到 HTTP 响应：DNS/连接/超时/重置等）。"""


def _parse_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except Exception:
        return {"__non_json__": True}


def request_json(
    method: str,
    url: str,
    body: dict | None = None,
    token: str | None = None,
    extra_headers: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_UA,
) -> tuple[int, dict]:
    """
    发起一次 JSON 请求。
    返回 (http_status, parsed_json)。
    传输层失败抛 HttpTransportError。
    """
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": user_agent,
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    if extra_headers:
        headers.update(extra_headers)

    payload = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, _parse_json(raw)
    except urllib.error.HTTPError as e:
        # 服务器返回了 HTTP 错误状态：仍尝试解析错误体（可能含业务码），不抛异常
        try:
            raw = e.read().decode("utf-8", "replace")
            return e.code, _parse_json(raw)
        except Exception:
            return e.code, {}
    except Exception as e:
        # DNS/连接/超时/SSL 等传输层失败
        raise HttpTransportError(str(e))


def post_json(url: str, body: dict | None = None, **kwargs) -> tuple[int, dict]:
    return request_json("POST", url, body=body, **kwargs)


def get_json(url: str, **kwargs) -> tuple[int, dict]:
    return request_json("GET", url, body=None, **kwargs)
