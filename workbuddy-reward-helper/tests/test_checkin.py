#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_checkin.py — workbuddy-reward-helper Phase 2 签到模块测试

严格边界（本阶段不做）：
  - 不真实调用任何接口（http_client.post_json 全部 Mock）
  - 不真实领取积分
  - 不真实读取登录态（credentials.load_credentials 全部 Mock，用假 token）
  - 不修改原 workbuddy-checkin / travel_auto 项目

测试内容：
  测试1 · 结构 / 导入链：checkin.py 能导入 credentials.py 与 http_client.py，调用链正常
  测试2 · Mock 接口：
    情况A 未签到 → daily-checkin 返回 code=0      → 期望 success（credit/streak_days 正确）
    情况B 已签到 → daily-checkin 返回 code=10001  → 期望 already_checked（不视为失败）
    情况C 接口异常 → 传输层抛错                    → 期望 failed
    附加  业务错误 code=其他 / 401 过期 / today_checked_in 快速短路
  所有用例额外校验：返回结果中绝不含 token。

退出码：0 = 全部通过；1 = 存在失败项。
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, SCRIPTS)

import credentials  # noqa: E402
import http_client  # noqa: E402
import checkin  # noqa: E402

FAKE_TOKEN = "FAKE_TOKEN_for_mock_only_DO_NOT_USE"
_passed: list[str] = []
_failed: list[str] = []


def check(name: str, cond: bool) -> None:
    (_passed if cond else _failed).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name)


def fake_credentials() -> dict:
    return {
        "access_token": FAKE_TOKEN,
        "uid": "user_mock_0001",
        "source": "workbuddy-desktop.info",
    }


def run_with_mock(post_json_impl) -> dict:
    """在 Mock 环境下执行一次 run_checkin，结束后还原被替换的函数。"""
    orig_load = credentials.load_credentials
    orig_post = http_client.post_json
    credentials.load_credentials = lambda: fake_credentials()
    http_client.post_json = post_json_impl
    try:
        return checkin.run_checkin()
    finally:
        credentials.load_credentials = orig_load
        http_client.post_json = orig_post


def no_token_leak(result: dict) -> bool:
    return FAKE_TOKEN not in json.dumps(result, ensure_ascii=False)


def main() -> int:
    print("=" * 64)
    print("workbuddy-reward-helper · checkin.py 测试（Phase 2，全 Mock，不真实请求）")
    print("=" * 64)

    # ---------------- 测试1：结构 / 导入链 ----------------
    print("测试1 · 模块导入与调用链")
    check("checkin.py 可导入", checkin is not None)
    check("checkin.run_checkin 可调用", callable(getattr(checkin, "run_checkin", None)))
    check("checkin 引用 credentials 模块", hasattr(checkin, "credentials"))
    check("checkin 引用 http_client 模块", hasattr(checkin, "http_client"))
    check("credentials.load_credentials 存在", callable(getattr(credentials, "load_credentials", None)))
    check("http_client.post_json 存在", callable(getattr(http_client, "post_json", None)))
    print()

    # ---------------- 测试2：Mock 接口 ----------------
    print("测试2 · Mock 接口（不真实请求、不真实领取）")

    # 情况A：未签到 → 签到成功 code=0
    def post_a(url, body=None, token=None, **kw):
        if url.endswith("checkin-status"):
            return 200, {"code": 0, "data": {"today_checked_in": False}}
        return 200, {"code": 0, "data": {"credit": 100, "streak_days": 5}}

    ra = run_with_mock(post_a)
    print("  情况A 返回：" + json.dumps(ra, ensure_ascii=False))
    check("情况A status==success", ra.get("status") == "success")
    check("情况A credit==100", ra.get("credit") == 100)
    check("情况A streak_days==5", ra.get("streak_days") == 5)
    check("情况A task==checkin", ra.get("task") == "checkin")
    check("情况A 不含 token", no_token_leak(ra))
    print()

    # 情况B：已签到 → daily-checkin 返回 code=10001 → already_checked（不视为失败）
    def post_b(url, body=None, token=None, **kw):
        if url.endswith("checkin-status"):
            return 200, {"code": 0, "data": {"today_checked_in": False}}
        return 200, {"code": 10001, "msg": "今天已签到"}

    rb = run_with_mock(post_b)
    print("  情况B 返回：" + json.dumps(rb, ensure_ascii=False))
    check("情况B status==already_checked", rb.get("status") == "already_checked")
    check("情况B 含 message", bool(rb.get("message")))
    check("情况B 不含 token", no_token_leak(rb))
    print()

    # 情况C：接口异常（传输层抛错）→ failed
    def post_c(url, body=None, token=None, **kw):
        raise http_client.HttpTransportError("模拟网络异常（超时/连接失败）")

    rc = run_with_mock(post_c)
    print("  情况C 返回：" + json.dumps(rc, ensure_ascii=False))
    check("情况C status==failed", rc.get("status") == "failed")
    check("情况C 含 reason", bool(rc.get("reason")))
    check("情况C 不含 token", no_token_leak(rc))
    print()

    # 附加C2：业务错误 code=其他 → failed
    def post_c2(url, body=None, token=None, **kw):
        if url.endswith("checkin-status"):
            return 200, {"code": 0, "data": {"today_checked_in": False}}
        return 200, {"code": 500, "msg": "系统繁忙"}

    rc2 = run_with_mock(post_c2)
    print("  附加C2(业务错误) 返回：" + json.dumps(rc2, ensure_ascii=False))
    check("附加C2 status==failed", rc2.get("status") == "failed")
    check("附加C2 reason 含 code", "code=" in str(rc2.get("reason")))
    print()

    # 附加D：401 令牌过期 → failed 且提示刷新
    def post_d(url, body=None, token=None, **kw):
        return 401, {}

    rd = run_with_mock(post_d)
    print("  附加D(401) 返回：" + json.dumps(rd, ensure_ascii=False))
    check("附加D status==failed", rd.get("status") == "failed")
    check("附加D reason 提示过期/401", ("401" in str(rd.get("reason"))) or ("过期" in str(rd.get("reason"))))
    print()

    # 附加E：today_checked_in=True 快速短路 → already_checked（且不再请求 daily-checkin）
    calls = {"daily": 0}

    def post_e(url, body=None, token=None, **kw):
        if url.endswith("checkin-status"):
            return 200, {"code": 0, "data": {"today_checked_in": True}}
        calls["daily"] += 1
        return 200, {"code": 0, "data": {"credit": 100, "streak_days": 5}}

    re_ = run_with_mock(post_e)
    print("  附加E(快速短路) 返回：" + json.dumps(re_, ensure_ascii=False))
    check("附加E status==already_checked", re_.get("status") == "already_checked")
    check("附加E 未发起 daily-checkin", calls["daily"] == 0)
    print()

    print("=" * 64)
    print("结果：通过 {} 项，失败 {} 项".format(len(_passed), len(_failed)))
    if _failed:
        print("失败项：")
        for n in _failed:
            print("  - " + n)
    print("=" * 64)
    return 0 if not _failed else 1


if __name__ == "__main__":
    sys.exit(main())
