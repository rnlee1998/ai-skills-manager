#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_main.py — workbuddy-reward-helper Phase 4 统一入口测试

严格边界：
  - 不真实调用任何接口（checkin/travel 的网络层全部 Mock）
  - 不真实签到 / 派遣 / 领取
  - 不创建自动化任务
  - 日志断言仅检查摘要内容，绝不包含 token

测试内容：
  测试1 · 子命令路由：checkin / travel / all 分别调用对应模块；未知命令报错
  测试2 · all：先签到后旅行，汇总结构正确，两任务结果都落日志
  测试3 · status：只读查询，不触发任何领取/派遣（零次 daily-checkin/depart/claim）
  测试4 · 结果日志：logs/result.log 追加摘要，无 token / 无响应原文
  测试5 · help：正常输出用法
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, SCRIPTS)

import checkin  # noqa: E402
import credentials  # noqa: E402
import http_client  # noqa: E402
import main as main_mod  # noqa: E402
import travel  # noqa: E402

FAKE_TOKEN = "FAKE_MAIN_TOKEN_for_mock_only"

_passed: list[str] = []
_failed: list[str] = []


def check(name: str, cond: bool) -> None:
    (_passed if cond else _failed).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name)


class Env:
    """Mock 环境：替换登录态 + HTTP 层，并把日志指到临时目录。"""

    def __init__(self, get_impl=None, post_impl=None):
        self.calls = []
        self._orig = {}
        self.get_impl = get_impl or (lambda url, **kw: (200, {"code": 0, "data": {}}))
        self.post_impl = post_impl or (lambda url, body=None, **kw: (200, {"code": 0, "data": {}}))
        self.tmp_log = None

    def __enter__(self):
        self._orig["load"] = credentials.load_credentials
        self._orig["get"] = http_client.get_json
        self._orig["post"] = http_client.post_json
        self._orig["log_file"] = main_mod.LOG_FILE
        self._orig["log_dir"] = main_mod.LOG_DIR
        credentials.load_credentials = lambda: {
            "access_token": FAKE_TOKEN, "uid": "user_mock_0003",
            "source": "workbuddy-desktop.info"}
        http_client.get_json = self._get
        http_client.post_json = self._post
        # 日志重定向到临时目录，避免污染真实 logs/
        self.tmp_log = tempfile.mkdtemp(prefix="wb_reward_main_test_")
        main_mod.LOG_DIR = self.tmp_log
        main_mod.LOG_FILE = os.path.join(self.tmp_log, "result.log")
        return self

    def __exit__(self, *exc):
        credentials.load_credentials = self._orig["load"]
        http_client.get_json = self._orig["get"]
        http_client.post_json = self._orig["post"]
        main_mod.LOG_DIR = self._orig["log_dir"]
        main_mod.LOG_FILE = self._orig["log_file"]
        return False

    def _get(self, url, **kw):
        self.calls.append(("GET", url))
        return self.get_impl(url, **kw)

    def _post(self, url, body=None, **kw):
        self.calls.append(("POST", url, body))
        return self.post_impl(url, body, **kw)

    def count(self, method: str, path: str) -> int:
        return sum(1 for m, u, *_ in self.calls if m == method and u.endswith(path))

    def log_text(self) -> str:
        try:
            with open(main_mod.LOG_FILE, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""


def default_post(url, body=None, **kw):
    """默认 Mock：签到侧返回成功，旅行侧按 idle 未达上限 → depart 成功。"""
    if url.endswith("daily-checkin"):
        return 200, {"code": 0, "data": {"credit": 100, "streak_days": 5}}
    if url.endswith("checkin-status"):
        return 200, {"code": 0, "data": {"today_checked_in": False, "streak_days": 5}}
    if url.endswith("travel/depart"):
        return 200, {"code": 0, "data": {
            "state": "traveling", "record_id": 3540861,
            "location": {"id": 1, "name": "咖啡馆"},
            "depart_at": 1, "arrive_at": 2}}
    if url.endswith("travel/claim"):
        return 200, {"code": 0, "data": {"reward_credit": 7, "record_id": 1}}
    return 200, {"code": 0, "data": {}}


def default_get(url, **kw):
    return 200, {"code": 0, "data": {
        "state": "idle", "daily_limit_reached": False, "arrive_at": 0}}


def main() -> int:
    print("=" * 64)
    print("workbuddy-reward-helper · main.py 统一入口测试（Phase 4，全 Mock）")
    print("=" * 64)

    # ---------------- 测试1：子命令路由 ----------------
    print("测试1 · 子命令路由")
    with Env(default_get, default_post) as env:
        r1 = main_mod.run_task("checkin")
        check("checkin 子命令返回签到结果", r1.get("task") == "checkin" and r1.get("status") == "success")
        check("checkin 只调用签到接口（无 travel 请求）",
              env.count("GET", "travel/status") == 0 and env.count("POST", "travel/depart") == 0)

    with Env(default_get, default_post) as env:
        r2 = main_mod.run_task("travel")
        check("travel 子命令返回旅行结果", r2.get("task") == "travel" and r2.get("status") == "departed")
        check("travel 只调用旅行接口（无签到请求）", env.count("POST", "daily-checkin") == 0)

    try:
        main_mod.run_task("badcmd")
        check("未知任务抛 ValueError", False)
    except ValueError:
        check("未知任务抛 ValueError", True)
    print()

    # ---------------- 测试2：all ----------------
    print("测试2 · all（先签到后旅行，汇总结构）")
    with Env(default_get, default_post) as env:
        r3 = main_mod.run_task("all")
        check("all 返回汇总结构（checkin+travel 两键）",
              set(r3.keys()) == {"checkin", "travel"})
        check("all.checkin.status==success", r3["checkin"].get("status") == "success")
        check("all.travel.status==departed", r3["travel"].get("status") == "departed")
        check("all 签到与旅行接口都被调用",
              env.count("POST", "daily-checkin") == 1 and env.count("POST", "travel/depart") == 1)
        log = env.log_text()
        check("all 写入两行结果日志", log.count("\n") == 2)
        check("日志含 checkin success", "checkin success" in log)
        check("日志含 credit=100", "credit=100" in log)
        check("日志含 travel departed", "travel departed" in log)
        check("日志不含 token", FAKE_TOKEN not in log)
    print()

    # ---------------- 测试3：status（只读） ----------------
    print("测试3 · status（只读查询，零动作）")
    with Env(default_get, default_post) as env:
        r4 = main_mod.run_task("status")
        check("status 返回 checkin_status + travel_status",
              set(r4.keys()) == {"checkin_status", "travel_status"})
        check("status.checkin_status.ok", r4["checkin_status"].get("status") == "ok")
        check("status.travel_status.ok 且 state=idle", r4["travel_status"].get("state") == "idle")
        check("status 零次 daily-checkin", env.count("POST", "daily-checkin") == 0)
        check("status 零次 depart", env.count("POST", "travel/depart") == 0)
        check("status 零次 claim", env.count("POST", "travel/claim") == 0)
        check("status 不写结果日志", env.log_text() == "")
        s = json.dumps(r4, ensure_ascii=False)
        check("status 结果不含 token", FAKE_TOKEN not in s)
    print()

    # ---------------- 测试4：help / main() ----------------
    print("测试4 · help 与 main() 入口")
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc_help = main_mod.main(["main.py", "help"])
    check("help 退出码 0 且输出用法", rc_help == 0 and "用法" in buf.getvalue())

    with Env(default_get, default_post):
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            rc_all = main_mod.main(["main.py", "all"])
        try:
            json.loads(buf2.getvalue())
            ok_json = True
        except json.JSONDecodeError:
            ok_json = False
        check("main all 退出码 0 且输出合法 JSON", rc_all == 0 and ok_json)

    with Env(default_get, default_post):
        buf3 = io.StringIO()
        with contextlib.redirect_stdout(buf3):
            rc_bad = main_mod.main(["main.py", "nonsense"])
        check("未知子命令退出码 1 且输出 failed JSON", rc_bad == 1 and '"failed"' in buf3.getvalue())
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
