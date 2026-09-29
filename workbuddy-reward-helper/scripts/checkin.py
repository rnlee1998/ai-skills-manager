#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
checkin.py — WorkBuddy 积分助手 · Buddy加油站每日签到模块（Phase 2）

迁移自 workbuddy-checkin/scripts/checkin.sh（已真实验证成功），由 bash+curl+字符串解析
重构为 Python 结构化实现。**只迁移签到逻辑，不改动原 workbuddy-checkin 项目。**

职责（本模块只做这几件事）：
  1. 通过 credentials.py 获取登录态（access_token）——不重复实现登录态读取，不复制 decrypt-token.js
  2. 调用签到相关接口（checkin-status / daily-checkin）
  3. 判断签到状态（含幂等 code=10001）
  4. 返回结构化结果（绝不含 access_token / refresh_token / 完整响应敏感字段）

接口（继承原 checkin.sh，host 为 copilot.tencent.com）：
  - POST /billing/meter/checkin-status   查签到状态（body {}）
  - POST /billing/meter/daily-checkin    执行签到（body {}）
  - 认证：Authorization: Bearer <accessToken>

幂等规则（必须保留，来自原实现与 CHANGELOG 实测结论）：
  - v5.3.8 实测 checkin-status 的 today_checked_in 字段不可靠（签到成功后仍可能为 false），
    因此这里仅用它做"快速短路"，真正的幂等兜底放在 daily-checkin 返回 code=10001。
  - code=10001 表示"今日已签到"，**不视为失败**，返回 already_checked。

返回结构（统一，可直接被上层/自动化消费）：
  成功：  {"task":"checkin","status":"success","credit":100,"streak_days":5}
  已签到：{"task":"checkin","status":"already_checked","message":"今日已签到"}
  失败：  {"task":"checkin","status":"failed","reason":"..."}

安全（继承 Phase 1）：
  - access_token 仅在内存中使用，绝不打印 / 写日志 / 落盘 / 上传第三方
  - 本模块只调用 copilot.tencent.com 的 WorkBuddy 服务端接口
"""

from __future__ import annotations

import os
import sys

# 允许以脚本方式或直接 import 运行时找到同目录的 credentials / http_client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import credentials  # noqa: E402
import http_client  # noqa: E402

CHECKIN_HOST = "https://copilot.tencent.com"
STATUS_PATH = "/billing/meter/checkin-status"
CHECKIN_PATH = "/billing/meter/daily-checkin"

CODE_SUCCESS = 0
CODE_ALREADY_CHECKED = 10001


def _result(status: str, **fields) -> dict:
    out = {"task": "checkin", "status": status}
    out.update(fields)
    return out


def run_checkin(timeout: int = http_client.DEFAULT_TIMEOUT) -> dict:
    """执行一次签到流程，返回统一结构化结果（不含任何敏感信息）。"""

    # 1. 获取登录态（统一走 credentials.py）
    try:
        cred = credentials.load_credentials()
    except credentials.CredentialError as e:
        return _result("failed", reason="登录态读取失败：" + str(e))
    token = cred["access_token"]  # 仅内存使用，绝不打印/落盘

    # 2. 查询签到状态（today_checked_in 不可靠，仅作快速短路 + 401 探测）
    try:
        st_code, st_body = http_client.post_json(
            CHECKIN_HOST + STATUS_PATH, body={}, token=token, timeout=timeout
        )
    except http_client.HttpTransportError as e:
        return _result("failed", reason="查询签到状态失败（网络异常）：" + str(e))

    if st_code == 401:
        return _result(
            "failed",
            reason="令牌已过期（401），请打开 WorkBuddy 桌面端刷新登录态后重试",
        )

    today_checked = (st_body.get("data") or {}).get("today_checked_in")
    if today_checked is True:
        # 快速短路：明确已签到则不再发起签到请求
        return _result("already_checked", message="今日已签到")

    # 3. 执行签到
    try:
        c_code, c_body = http_client.post_json(
            CHECKIN_HOST + CHECKIN_PATH, body={}, token=token, timeout=timeout
        )
    except http_client.HttpTransportError as e:
        return _result("failed", reason="签到请求失败（网络异常）：" + str(e))

    if c_code == 401:
        return _result(
            "failed",
            reason="令牌已过期（401），请打开 WorkBuddy 桌面端刷新登录态后重试",
        )

    code = c_body.get("code")
    data = c_body.get("data") or {}

    if code == CODE_SUCCESS:
        return _result(
            "success",
            credit=data.get("credit"),
            streak_days=data.get("streak_days"),
        )
    if code == CODE_ALREADY_CHECKED:
        # 幂等：今日已签到，不视为失败
        return _result("already_checked", message="今日已签到")

    return _result(
        "failed",
        reason="签到未成功：code={} msg={}".format(code, c_body.get("msg")),
    )


if __name__ == "__main__":
    # 以结构化 JSON 输出结果（不含 token），供上层/自动化读取。
    import json

    print(json.dumps(run_checkin(), ensure_ascii=False))
