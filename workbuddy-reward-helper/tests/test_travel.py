#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_travel.py — workbuddy-reward-helper Phase 3 Buddy旅行模块测试

严格边界（本阶段不做）：
  - 不真实调用任何旅行接口（http_client 全部 Mock）
  - 不真实派遣猫猫、不真实领取奖励
  - 不真实读取登录态（credentials.load_credentials 全部 Mock，用假 token / 假 uid）
  - 不修改原 workbuddy-travel-auto / workbuddy-checkin 项目

测试内容：
  测试1 · 依赖检查：travel.py 只依赖 credentials.py / http_client.py（标准库除外）
  测试2 · Mock 状态机：
    情况A idle（未达上限）     → 调用 depart     → departed + record_id
    情况B traveling            → 不重复派遣      → traveling（且零次 depart/claim）
    情况C arrived              → 调用 claim      → claimed + reward_credit
    情况D idle + 达上限        → 正确返回已完成  → daily_limit_reached（零次 depart）
    情况E 接口异常（传输层）   → failed
    附加  401 过期 / 业务错误 / 未知状态 / headers 带 X-User-Id
  所有用例额外校验：返回结果中绝不含 token、uid、Authorization。

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
import travel  # noqa: E402

FAKE_TOKEN = "FAKE_TRAVEL_TOKEN_for_mock_only"
FAKE_UID = "user_mock_0002"

_passed: list[str] = []
_failed: list[str] = []


def check(name: str, cond: bool) -> None:
    (_passed if cond else _failed).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name)


def fake_credentials() -> dict:
    return {
        "access_token": FAKE_TOKEN,
        "uid": FAKE_UID,
        "source": "workbuddy-desktop.info",
    }


class Recorder:
    """Mock http_client.get_json / post_json，记录调用并按脚本回放。"""

    def __init__(self, get_impl, post_impl):
        self.get_impl = get_impl
        self.post_impl = post_impl
        self.calls = []  # (method, url, kwargs) 记录，不含 token 值以外的敏感信息

    def get_json(self, url, **kw):
        self.calls.append(("GET", url, {"uid_header": kw.get("extra_headers", {}).get("X-User-Id")}))
        return self.get_impl(url, **kw)

    def post_json(self, url, body=None, **kw):
        self.calls.append(("POST", url, {"body": body, "uid_header": kw.get("extra_headers", {}).get("X-User-Id")}))
        return self.post_impl(url, body, **kw)


def run_with_mock(get_impl, post_impl) -> tuple[dict, Recorder]:
    """在 Mock 环境下执行一次 run_travel，返回 (结果, 调用记录器)。"""
    rec = Recorder(get_impl, post_impl)
    orig_load = credentials.load_credentials
    orig_get = http_client.get_json
    orig_post = http_client.post_json
    credentials.load_credentials = lambda: fake_credentials()
    http_client.get_json = rec.get_json
    http_client.post_json = rec.post_json
    try:
        return travel.run_travel(), rec
    finally:
        credentials.load_credentials = orig_load
        http_client.get_json = orig_get
        http_client.post_json = orig_post


def no_leak(result: dict) -> bool:
    s = json.dumps(result, ensure_ascii=False)
    return FAKE_TOKEN not in s and FAKE_UID not in s and "Authorization" not in s


def count_calls(rec: Recorder, method: str, path: str) -> int:
    return sum(
        1 for m, url, _ in rec.calls
        if m == method and url.endswith(path)
    )


def main() -> int:
    print("=" * 64)
    print("workbuddy-reward-helper · travel.py 测试（Phase 3，全 Mock，不真实请求）")
    print("=" * 64)

    # ---------------- 测试1：依赖检查 ----------------
    print("测试1 · 依赖检查（travel.py 只依赖 credentials / http_client）")
    import ast

    src = open(os.path.join(SCRIPTS, "travel.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    local_imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                local_imports.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            local_imports.add(node.module.split(".")[0])
    stdlib_or_builtin = set(sys.stdlib_module_names) | {"__future__"}
    project_deps = local_imports - stdlib_or_builtin
    check("仅依赖 credentials / http_client（标准库除外）",
          project_deps <= {"credentials", "http_client"}),
    check("依赖集合实际为: {}".format(sorted(project_deps)),
          project_deps == {"credentials", "http_client"})
    check("travel.run_travel 可调用", callable(getattr(travel, "run_travel", None)))
    print()

    # ---------------- 测试2：Mock 状态机 ----------------
    print("测试2 · Mock 状态机（不派遣猫猫、不领取奖励）")

    # 情况A：idle 未达上限 → 调用 depart → departed
    def get_a(url, **kw):
        return 200, {"code": 0, "data": {
            "state": "idle", "daily_limit_reached": False, "arrive_at": 0}}

    def post_a(url, body=None, **kw):
        if url.endswith("travel/depart"):
            return 200, {"code": 0, "data": {
                "state": "traveling", "record_id": 2237800,
                "location": {"id": 1, "name": "咖啡馆", "duration_hours": 2},
                "depart_at": 1787444560, "arrive_at": 1787451760}}
        return 200, {"code": 0, "data": {}}

    ra, rec_a = run_with_mock(get_a, post_a)
    print("  情况A 返回：" + json.dumps(ra, ensure_ascii=False))
    check("情况A status==departed", ra.get("status") == "departed")
    check("情况A record_id==2237800", ra.get("record_id") == 2237800)
    check("情况A 调用过 depart", count_calls(rec_a, "POST", "travel/depart") == 1)
    check("情况A 未调用 claim", count_calls(rec_a, "POST", "travel/claim") == 0)
    check("情况A depart body location_id=1",
          any(c[2].get("body") == {"location_id": 1} for c in rec_a.calls if c[1].endswith("travel/depart")))
    check("情况A 不含 token/uid/Authorization", no_leak(ra))
    print()

    # 情况B：traveling → 不重复派遣
    def get_b(url, **kw):
        return 200, {"code": 0, "data": {
            "state": "traveling", "daily_limit_reached": True, "arrive_at": 1788495803}}

    def post_b(url, body=None, **kw):
        return 200, {"code": 0, "data": {}}

    rb, rec_b = run_with_mock(get_b, post_b)
    print("  情况B 返回：" + json.dumps(rb, ensure_ascii=False))
    check("情况B status==traveling", rb.get("status") == "traveling")
    check("情况B 携带 arrive_at", rb.get("arrive_at") == 1788495803)
    check("情况B 零次 depart", count_calls(rec_b, "POST", "travel/depart") == 0)
    check("情况B 零次 claim", count_calls(rec_b, "POST", "travel/claim") == 0)
    check("情况B 不含 token/uid/Authorization", no_leak(rb))
    print()

    # 情况C：arrived → 调用 claim → claimed
    def get_c(url, **kw):
        return 200, {"code": 0, "data": {
            "state": "arrived", "daily_limit_reached": True, "arrive_at": 1788405777}}

    def post_c(url, body=None, **kw):
        if url.endswith("travel/claim"):
            return 200, {"code": 0, "data": {
                "reward_credit": 7, "record_id": 2237800, "state": "idle"}}
        return 200, {"code": 0, "data": {}}

    rc, rec_c = run_with_mock(get_c, post_c)
    print("  情况C 返回：" + json.dumps(rc, ensure_ascii=False))
    check("情况C status==claimed", rc.get("status") == "claimed")
    check("情况C reward_credit==7", rc.get("reward_credit") == 7)
    check("情况C record_id==2237800", rc.get("record_id") == 2237800)
    check("情况C 调用过 claim", count_calls(rec_c, "POST", "travel/claim") == 1)
    check("情况C 零次 depart", count_calls(rec_c, "POST", "travel/depart") == 0)
    check("情况C 不含 token/uid/Authorization", no_leak(rc))
    print()

    # 情况D：idle + daily_limit_reached → 正确返回已完成（零次 depart）
    def get_d(url, **kw):
        return 200, {"code": 0, "data": {
            "state": "idle", "daily_limit_reached": True, "arrive_at": 0}}

    def post_d(url, body=None, **kw):
        return 200, {"code": 0, "data": {}}

    rd, rec_d = run_with_mock(get_d, post_d)
    print("  情况D 返回：" + json.dumps(rd, ensure_ascii=False))
    check("情况D status==daily_limit_reached", rd.get("status") == "daily_limit_reached")
    check("情况D 含 message=今日旅行次数已完成", rd.get("message") == "今日旅行次数已完成")
    check("情况D 零次 depart", count_calls(rec_d, "POST", "travel/depart") == 0)
    check("情况D 零次 claim", count_calls(rec_d, "POST", "travel/claim") == 0)
    check("情况D 不含 token/uid/Authorization", no_leak(rd))
    print()

    # 情况E：接口异常（传输层抛错）→ failed
    def get_e(url, **kw):
        raise http_client.HttpTransportError("模拟网络异常（超时/连接失败）")

    def post_e(url, body=None, **kw):
        return 200, {"code": 0, "data": {}}

    re_, _ = run_with_mock(get_e, post_e)
    print("  情况E 返回：" + json.dumps(re_, ensure_ascii=False))
    check("情况E status==failed", re_.get("status") == "failed")
    check("情况E 含 reason", bool(re_.get("reason")))
    check("情况E 不含 token/uid/Authorization", no_leak(re_))
    print()

    # 附加F：401 令牌失效 → failed（不重试）
    def get_f(url, **kw):
        return 401, {}

    rf, _ = run_with_mock(get_f, lambda url, body=None, **kw: (200, {"code": 0}))
    print("  附加F(401) 返回：" + json.dumps(rf, ensure_ascii=False))
    check("附加F status==failed", rf.get("status") == "failed")
    check("附加F reason 提示 401/失效", ("401" in str(rf.get("reason"))) or ("失效" in str(rf.get("reason"))))
    print()

    # 附加G：状态接口业务错误 → failed
    def get_g(url, **kw):
        return 200, {"code": 500, "msg": "活动不存在"}

    rg, _ = run_with_mock(get_g, lambda url, body=None, **kw: (200, {"code": 0}))
    print("  附加G(业务错误) 返回：" + json.dumps(rg, ensure_ascii=False))
    check("附加G status==failed", rg.get("status") == "failed")
    check("附加G reason 含 code", "code=" in str(rg.get("reason")))
    print()

    # 附加H：未知状态 → failed
    def get_h(url, **kw):
        return 200, {"code": 0, "data": {"state": "weird_state", "daily_limit_reached": False}}

    rh, _ = run_with_mock(get_h, lambda url, body=None, **kw: (200, {"code": 0}))
    print("  附加H(未知状态) 返回：" + json.dumps(rh, ensure_ascii=False))
    check("附加H status==failed", rh.get("status") == "failed")
    print()

    # 附加I：请求头携带 X-User-Id（credentials 提供的 uid）
    _, rec_i = run_with_mock(get_a, post_a)
    uid_headers = [c[2].get("uid_header") for c in rec_i.calls]
    check("附加I 请求均携带 X-User-Id=credentials.uid",
          all(h == FAKE_UID for h in uid_headers) and len(uid_headers) > 0)
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
