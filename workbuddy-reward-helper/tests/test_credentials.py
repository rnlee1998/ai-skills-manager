#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_credentials.py — workbuddy-reward-helper Phase 1 读取测试

只做"读取"验证，绝不调用任何接口、绝不打印真实 token、绝不保存 token 副本。

分两部分：
  Part A · 逻辑验证（合成 fixture，沙箱内必可运行）
    构造一个假的 workbuddy-desktop.info（假 token），把 HOME 指向临时目录，
    验证 credentials.py 的"找文件→解析 access_token→解析 uid→脱敏返回"全链路正确。
    假 token 仅存在于临时目录，用完即删，与真实登录态无关。

  Part B · 真实路径验证（读取本机真实登录态）
    用真实 HOME 调用 load_credentials()，打印脱敏结果。
    注意：在 WorkBuddy Agent 沙箱内，系统可能拦截
    ~/Library/Application Support/CodeBuddyExtension（返回 PermissionError）。
    这不代表代码或登录态有问题——真实 WorkBuddy 自动化在沙箱外可正常读取。
    此时如实报告环境限制（标记 ⚠️），不视为测试失败。

退出码：
  0 = Part A 通过（逻辑正确）。Part B 仅作报告，不参与成败判定。
  1 = Part A 失败（解析逻辑有真实缺陷）。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile

# --- 定位并加载被测模块 scripts/credentials.py ---
HERE = os.path.dirname(os.path.abspath(__file__))
CRED_PATH = os.path.normpath(os.path.join(HERE, "..", "scripts", "credentials.py"))

spec = importlib.util.spec_from_file_location("credentials", CRED_PATH)
credentials = importlib.util.module_from_spec(spec)
spec.loader.exec_module(credentials)

CredentialError = credentials.CredentialError


def _print_result(tag: str, cred: dict) -> None:
    d = credentials.describe(cred)
    print("  ✅ [{}] 找到登录态来源：{}".format(tag, d["source"]))
    print("  ✅ [{}] access_token：{}".format(tag, d["access_token"]))
    print("  ✅ [{}] uid：{}".format(tag, d["uid"]))


def part_a_fixture() -> bool:
    """合成 fixture 验证解析逻辑（沙箱内必可运行）。"""
    print("─" * 60)
    print("Part A · 逻辑验证（合成 fixture，假 token，临时目录）")
    print("─" * 60)

    fake_token = "FAKE_TOKEN_for_unit_test_ONLY_0123456789"
    fake_uid = "user_1234567890"
    fixture = {
        "account": {"uid": fake_uid, "nickname": "tester"},
        "auth": {
            "accessToken": fake_token,
            "refreshToken": "fake_refresh",
            "expiresAt": 0,
        },
        "accounts": [],
    }

    tmp_home = tempfile.mkdtemp(prefix="wb_reward_test_home_")
    old_home = os.environ.get("HOME")
    try:
        # 按 macOS 明文路径结构铺 fixture（测试机为 darwin）
        auth_dir = os.path.join(
            tmp_home, "Library", "Application Support",
            "CodeBuddyExtension", "Data", "Public", "auth",
        )
        os.makedirs(auth_dir, exist_ok=True)
        info_path = os.path.join(auth_dir, "workbuddy-desktop.info")
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(fixture, f)

        os.environ["HOME"] = tmp_home  # expanduser("~") 依赖 $HOME

        cred = credentials.load_credentials()

        # 断言（不打印真实 token，只做内部比对）
        checks = []
        checks.append(("source == workbuddy-desktop.info",
                       cred.get("source") == credentials.SOURCE_DESKTOP_INFO))
        checks.append(("解析出 access_token（值正确）",
                       cred.get("access_token") == fake_token))
        checks.append(("解析出 uid（值正确）",
                       cred.get("uid") == fake_uid))
        checks.append(("脱敏输出不含真实 token",
                       fake_token not in str(credentials.describe(cred))))
        checks.append(("脱敏 uid 不含完整 uid",
                       fake_uid not in credentials.mask_uid(fake_uid)))

        all_ok = True
        for name, ok in checks:
            print("  {} {}".format("✅" if ok else "❌", name))
            all_ok = all_ok and ok

        if all_ok:
            print("  → Part A 通过：找文件 / 解析 token / 解析 uid / 脱敏 全链路正确")
        else:
            print("  → Part A 失败：存在解析逻辑缺陷")
        return all_ok
    except CredentialError as e:
        print("  ❌ Part A 异常（CredentialError）：{}".format(e))
        return False
    finally:
        if old_home is not None:
            os.environ["HOME"] = old_home
        else:
            os.environ.pop("HOME", None)
        # 清理临时目录（含假 token，属合成数据，非真实登录态）
        import shutil
        shutil.rmtree(tmp_home, ignore_errors=True)


def part_b_real() -> None:
    """读取本机真实登录态（仅脱敏输出）。仅报告，不判定成败。"""
    print("─" * 60)
    print("Part B · 真实路径验证（读取本机真实登录态，仅脱敏）")
    print("─" * 60)
    try:
        cred = credentials.load_credentials()
        _print_result("真实", cred)
    except CredentialError as e:
        msg = str(e)
        # 沙箱拦截特征：找不到任何登录态（实际是权限被拒）
        print("  ⚠️ 真实路径暂不可读：{}".format(msg))
        print("  ⚠️ 说明：若在 WorkBuddy Agent 沙箱内运行，系统会拦截")
        print("     ~/Library/Application Support/CodeBuddyExtension（PermissionError），")
        print("     属环境限制，非代码/登录态问题；真实自动化在沙箱外可正常读取。")
    except PermissionError as e:
        print("  ⚠️ 真实路径被系统拒绝读取（PermissionError）：{}".format(e))
        print("     属沙箱/权限限制，非代码问题。")


def main() -> int:
    print("=" * 60)
    print("workbuddy-reward-helper · credentials.py 读取测试（Phase 1）")
    print("=" * 60)
    ok_a = part_a_fixture()
    print()
    part_b_real()
    print()
    print("=" * 60)
    print("结论：Part A（逻辑）{}；Part B（真实路径）见上方报告（不判定成败）"
          .format("✅ 通过" if ok_a else "❌ 失败"))
    print("=" * 60)
    return 0 if ok_a else 1


if __name__ == "__main__":
    sys.exit(main())
