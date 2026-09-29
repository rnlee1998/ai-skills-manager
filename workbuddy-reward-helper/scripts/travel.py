#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
travel.py — WorkBuddy 积分助手 · Buddy旅行（派猫猫）模块（Phase 3）

迁移自 workbuddy-travel-auto/travel_auto.py（已真实验证成功，2026-08-23 验收报告
证明 depart→claim 同单闭环），由"自带登录态读取 + 自带 HTTP 封装"重构为
复用本项目的 credentials.py + http_client.py。**不改动原 workbuddy-travel-auto 项目，
不重新设计业务流程。**

职责（Buddy旅行完整状态机，单次执行、不做长时间轮询）：
  1. 查询旅行状态（GET /activity/growth/buddy/travel/status）
  2. 按状态决策（幂等，先领后派）：
       state = arrived   → POST /activity/growth/buddy/travel/claim {}（领取奖励）
       state = idle      → daily_limit_reached=false → POST depart {"location_id":1}（固定咖啡馆）
                           daily_limit_reached=true  → 返回今日旅行次数已完成，不派遣
       state = traveling → 返回旅行中，不重复派遣
       未知 state        → failed
  3. 返回结构化结果（绝不含 token / 完整请求头 / 敏感用户信息）

接口契约（继承自 travel_auto.py，host 为 www.workbuddy.cn）：
  - GET  /activity/growth/buddy/travel/status
  - POST /activity/growth/buddy/travel/depart   body {"location_id": 1}
  - POST /activity/growth/buddy/travel/claim    body {}
  - 认证：Authorization: Bearer <access_token> + X-User-Id: <uid> + User-Agent: WorkBuddy/5.3.14

幂等规则（继承原实现）：
  - traveling 绝不 depart；arrived 只 claim 一次；idle 且达上限不派遣
  - token 失效（401）→ failed（不重试，待人工刷新登录态）
  - 网络异常 / 业务错误 → failed（等下一次调度）

返回结构：
  派遣成功：{"task":"travel","status":"departed","record_id":xxx, ...}
  领取成功：{"task":"travel","status":"claimed","reward_credit":7, ...}
  旅行中：  {"task":"travel","status":"traveling", ...}
  达上限：  {"task":"travel","status":"daily_limit_reached", ...}
  失败：    {"task":"travel","status":"failed","reason":"..."}

安全（继承 Phase 1/2）：
  - token 仅内存使用，绝不打印 / 写日志 / 落盘 / 上传第三方
"""

from __future__ import annotations

import os
import sys

# 允许以脚本方式或直接 import 运行时找到同目录的 credentials / http_client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import credentials  # noqa: E402
import http_client  # noqa: E402

TRAVEL_HOST = "https://www.workbuddy.cn"
STATUS_PATH = "/activity/growth/buddy/travel/status"
DEPART_PATH = "/activity/growth/buddy/travel/depart"
CLAIM_PATH = "/activity/growth/buddy/travel/claim"

LOCATION_ID = 1  # 固定咖啡馆（与原 travel_auto.py 一致）
TRAVEL_UA = "WorkBuddy/5.3.14"  # 旅行接口要求的 UA（与原实现一致）

STATE_IDLE = "idle"
STATE_TRAVELING = "traveling"
STATE_ARRIVED = "arrived"


def _result(status: str, **fields) -> dict:
    out = {"task": "travel", "status": status}
    out.update(fields)
    return out


def _travel_headers(uid: str) -> dict:
    """旅行接口专用 headers：X-User-Id（uid 由 credentials.py 统一提供）。"""
    return {"X-User-Id": uid}


def run_travel(timeout: int = http_client.DEFAULT_TIMEOUT) -> dict:
    """执行一次旅行状态机（单次检查+决策），返回统一结构化结果。"""

    # 1. 获取登录态（统一走 credentials.py，含 uid）
    try:
        cred = credentials.load_credentials()
    except credentials.CredentialError as e:
        return _result("failed", reason="登录态读取失败：" + str(e))
    token = cred["access_token"]  # 仅内存使用，绝不打印/落盘
    uid = cred.get("uid", "")
    headers = _travel_headers(uid)

    # 2. 查询旅行状态
    try:
        st_code, st_body = http_client.get_json(
            TRAVEL_HOST + STATUS_PATH, token=token,
            extra_headers=headers, timeout=timeout, user_agent=TRAVEL_UA,
        )
    except http_client.HttpTransportError as e:
        return _result("failed", reason="查询旅行状态失败（网络异常）：" + str(e))

    if st_code == 401:
        return _result(
            "failed",
            reason="令牌已失效（401），请打开 WorkBuddy 桌面端刷新登录态后重试",
        )
    if st_body.get("code") != 0:
        return _result(
            "failed",
            reason="状态接口业务错误：code={} msg={}".format(
                st_body.get("code"), st_body.get("msg")
            ),
        )

    d = st_body.get("data") or {}
    state = d.get("state")
    daily_limit_reached = bool(d.get("daily_limit_reached"))
    arrive_at = d.get("arrive_at")

    # 3. 状态机（保持原 travel_auto.py 决策，不重新设计）
    if state == STATE_ARRIVED:
        # 到达 → 领取奖励
        try:
            c_code, c_body = http_client.post_json(
                TRAVEL_HOST + CLAIM_PATH, body={}, token=token,
                extra_headers=headers, timeout=timeout, user_agent=TRAVEL_UA,
            )
        except http_client.HttpTransportError as e:
            return _result("failed", reason="claim 失败（网络异常）：" + str(e))
        if c_code == 401:
            return _result("failed", reason="claim 返回 401（令牌失效），停止本轮")
        if c_body.get("code") != 0:
            return _result(
                "failed",
                reason="claim 业务错误：code={} msg={}".format(
                    c_body.get("code"), c_body.get("msg")
                ),
            )
        cd = c_body.get("data") or {}
        return _result(
            "claimed",
            reward_credit=cd.get("reward_credit"),
            record_id=cd.get("record_id"),
        )

    if state == STATE_IDLE:
        if daily_limit_reached:
            # 今日已达派遣上限：不派遣
            return _result("daily_limit_reached", message="今日旅行次数已完成")
        # 未达上限 → 派遣（固定咖啡馆）
        try:
            d_code, d_body = http_client.post_json(
                TRAVEL_HOST + DEPART_PATH, body={"location_id": LOCATION_ID},
                token=token, extra_headers=headers,
                timeout=timeout, user_agent=TRAVEL_UA,
            )
        except http_client.HttpTransportError as e:
            return _result("failed", reason="depart 失败（网络异常）：" + str(e))
        if d_code == 401:
            return _result("failed", reason="depart 返回 401（令牌失效），停止本轮")
        if d_body.get("code") != 0:
            return _result(
                "failed",
                reason="depart 业务错误：code={} msg={}".format(
                    d_body.get("code"), d_body.get("msg")
                ),
            )
        dd = d_body.get("data") or {}
        loc = dd.get("location") or {}
        return _result(
            "departed",
            record_id=dd.get("record_id"),
            location=loc.get("name"),
            arrive_at=dd.get("arrive_at"),
        )

    if state == STATE_TRAVELING:
        # 旅行中：不重复派遣
        return _result("traveling", arrive_at=arrive_at)

    # 未知状态
    return _result(
        "failed",
        reason="未知旅行状态：state={}".format(state),
    )


if __name__ == "__main__":
    # 以结构化 JSON 输出结果（不含 token / 敏感信息），供上层/自动化读取。
    import json

    print(json.dumps(run_travel(), ensure_ascii=False))
