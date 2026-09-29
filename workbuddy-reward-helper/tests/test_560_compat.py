#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_560_compat.py — workbuddy-reward-helper v1.0.1 · WorkBuddy 5.6.0 兼容热修测试

只做合成 fixture 验证（沙箱内必可运行）：
  - 不读取本机真实登录态（不设 HOME 回真实验证的 Part）
  - 不调用任何网络接口
  - 不打印任何真实 token / envelope（fixture 全部为合成数据）

用例组：
  T1  加密主文件 → 报准确错误（含 5.6.0 / $wbEncrypted，不含「未找到可用登录态」误导）
  T2  加密主文件 + 显式开关未开 → 不使用备份（仍报加密错误）
  T3  加密主文件 + 开关开启 + 合法备份（同uid+同域+未过期） → 使用备份（source 标明）
  T4  备份 uid 不同 → 拒绝
  T5  备份 domain 不同 → 拒绝
  T6  备份临过期/已过期 → 拒绝
  T7  备份 token 非明文（也是加密 dict） → 拒绝
  T8  明文主文件（未升级 5.6.0） → 原逻辑回归（正常读取）
  T9  错误信息不含 envelope 值 / 备份 token 本体
  T10 签到/旅行分别报告（main.run_task 互不拖垮，直接验证 all 的两个分支结构）

退出码：0 = 全部通过；1 = 存在失败。
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CRED_PATH = os.path.normpath(os.path.join(HERE, "..", "scripts", "credentials.py"))

spec = importlib.util.spec_from_file_location("credentials_560", CRED_PATH)
credentials = importlib.util.module_from_spec(spec)
spec.loader.exec_module(credentials)

FAKE_UID = "u_test_0000111122223333"
FAKE_DOMAIN = "www.workbuddy.cn"
FAKE_TOKEN_PLAIN = "FAKE_PLAIN_" + "x" * 200          # 主文件明文 token（T8）
FAKE_TOKEN_BACKUP = "FAKE_BACKUP_" + "y" * 200        # 备份明文 token（T3）
FAKE_ENVELOPE = "FAKE_ENVELOPE_BASE64URL_DATA"        # 合成 envelope（非真实）
NOW_MS = int(time.time() * 1000)
FUTURE_EXPIRES = NOW_MS + 30 * 24 * 3600 * 1000       # 30 天后

RESULTS: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    RESULTS.append((name, ok))
    print("  {} {}".format("✅" if ok else "❌", name))


def make_dir() -> str:
    home = tempfile.mkdtemp(prefix="wb560_test_")
    auth_dir = os.path.join(
        home, "Library", "Application Support",
        "CodeBuddyExtension", "Data", "Public", "auth",
    )
    os.makedirs(auth_dir, exist_ok=True)
    return home, auth_dir


def write_encrypted_main(auth_dir: str) -> str:
    fixture = {
        "account": {"uid": FAKE_UID},
        "auth": {
            "accessToken": {"$wbEncrypted": 1, "envelope": FAKE_ENVELOPE},
            "refreshToken": {"$wbEncrypted": 1, "envelope": FAKE_ENVELOPE},
            "domain": FAKE_DOMAIN,
            "expiresAt": NOW_MS + 60 * 24 * 3600 * 1000,
        },
    }
    p = os.path.join(auth_dir, "workbuddy-desktop.info")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(fixture, f)
    return p


def write_backup(auth_dir: str, *, uid=FAKE_UID, domain=FAKE_DOMAIN,
                 token=FAKE_TOKEN_BACKUP, expires=FUTURE_EXPIRES) -> str:
    fixture = {
        "account": {"uid": uid},
        "auth": {
            "accessToken": token,
            "refreshToken": "fake_refresh_backup",
            "domain": domain,
            "expiresAt": expires,
        },
    }
    p = os.path.join(auth_dir, "workbuddy-desktop.2026-08-21T07-23-19-813Z.test.info")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(fixture, f)
    return p


def run_case(case) -> tuple[object, str]:
    """在隔离 HOME + 指定 env 下调用 load_credentials，返回 (cred 或 None, 错误文本)。"""
    home, auth_dir = make_dir()
    old_home, old_env = os.environ.get("HOME"), os.environ.get(credentials.ENV_ALLOW_BACKUP)
    try:
        os.environ["HOME"] = home
        os.environ.pop(credentials.ENV_ALLOW_BACKUP, None)
        case(auth_dir)
        try:
            cred = credentials.load_credentials()
            return cred, ""
        except credentials.CredentialError as e:
            return None, str(e)
    finally:
        if old_home is not None:
            os.environ["HOME"] = old_home
        if old_env is not None:
            os.environ[credentials.ENV_ALLOW_BACKUP] = old_env
        else:
            os.environ.pop(credentials.ENV_ALLOW_BACKUP, None)
        shutil.rmtree(home, ignore_errors=True)


def t1_encrypted_error():
    cred, err = run_case(write_encrypted_main)
    check("T1 加密主文件 → CredentialError（非返回凭据）", cred is None)
    check("T1 错误含「5.6.0」", "5.6.0" in err)
    check("T1 错误含「$wbEncrypted」", "$wbEncrypted" in err)
    check("T1 错误不含误导文案「均未命中」", "均未命中" not in err)


def t2_no_env_no_backup():
    def setup(auth_dir):
        write_encrypted_main(auth_dir)
        write_backup(auth_dir)  # 备份存在但未开开关
    cred, err = run_case(setup)
    check("T2 未设 WB_REWARD_ALLOW_BACKUP → 不使用备份", cred is None)
    check("T2 仍报加密格式错误（等待 Skill 更新）", "5.6.0" in err)


def t3_backup_with_env():
    def setup(auth_dir):
        write_encrypted_main(auth_dir)
        write_backup(auth_dir)
    home, auth_dir = make_dir()
    old_home, old_env = os.environ.get("HOME"), os.environ.get(credentials.ENV_ALLOW_BACKUP)
    try:
        os.environ["HOME"] = home
        os.environ[credentials.ENV_ALLOW_BACKUP] = "1"
        write_encrypted_main(auth_dir)
        write_backup(auth_dir)
        cred = credentials.load_credentials()
        check("T3 开关开启 + 合法备份 → 返回凭据", cred is not None)
        if cred:
            check("T3 source 标明来自明文备份",
                   cred.get("source") == credentials.SOURCE_BACKUP_INFO)
            check("T3 token 为备份明文", cred.get("access_token") == FAKE_TOKEN_BACKUP)
            check("T3 uid 正确", cred.get("uid") == FAKE_UID)
    finally:
        if old_home is not None:
            os.environ["HOME"] = old_home
        if old_env is not None:
            os.environ[credentials.ENV_ALLOW_BACKUP] = old_env
        else:
            os.environ.pop(credentials.ENV_ALLOW_BACKUP, None)
        shutil.rmtree(home, ignore_errors=True)


def t4_wrong_uid():
    def setup(auth_dir):
        write_encrypted_main(auth_dir)
        write_backup(auth_dir, uid="u_OTHER_999999")
    cred, _ = run_case(setup)
    check("T4 备份 uid 不同 → 拒绝", cred is None)


def t5_wrong_domain():
    def setup(auth_dir):
        write_encrypted_main(auth_dir)
        write_backup(auth_dir, domain="www.codebuddy.cn")
    cred, _ = run_case(setup)
    check("T5 备份 domain 不同 → 拒绝", cred is None)


def t6_expired_backup():
    def setup(auth_dir):
        write_encrypted_main(auth_dir)
        write_backup(auth_dir, expires=NOW_MS - 1000)  # 已过期
    cred, _ = run_case(setup)
    check("T6 备份已过期 → 拒绝", cred is None)

    def setup2(auth_dir):
        write_encrypted_main(auth_dir)
        # 临过期（剩余 10 分钟 < 1 小时下限）
        write_backup(auth_dir, expires=NOW_MS + 10 * 60 * 1000)
    cred2, _ = run_case(setup2)
    check("T6 备份临过期(<1h) → 拒绝", cred2 is None)


def t7_encrypted_backup():
    def setup(auth_dir):
        write_encrypted_main(auth_dir)
        write_backup(auth_dir, token={"$wbEncrypted": 1, "envelope": FAKE_ENVELOPE})
    cred, _ = run_case(setup)
    check("T7 备份 token 也是加密 dict → 拒绝", cred is None)


def t8_plaintext_regression():
    def setup(auth_dir):
        fixture = {
            "account": {"uid": FAKE_UID},
            "auth": {"accessToken": FAKE_TOKEN_PLAIN, "domain": FAKE_DOMAIN,
                     "expiresAt": FUTURE_EXPIRES},
        }
        with open(os.path.join(auth_dir, "workbuddy-desktop.info"), "w",
                  encoding="utf-8") as f:
            json.dump(fixture, f)
    cred, _ = run_case(setup)
    check("T8 未加密主文件 → 原逻辑正常读取", cred is not None)
    if cred:
        check("T8 source 仍为 workbuddy-desktop.info",
               cred.get("source") == credentials.SOURCE_DESKTOP_INFO)
        check("T8 token 正确", cred.get("access_token") == FAKE_TOKEN_PLAIN)


def t9_no_sensitive_leak():
    def setup(auth_dir):
        write_encrypted_main(auth_dir)
        write_backup(auth_dir)
    cred, err = run_case(setup)
    check("T9 错误信息不含 envelope 合成值", FAKE_ENVELOPE not in err)
    check("T9 错误信息不含备份 token 本体", FAKE_TOKEN_BACKUP not in err)


def t10_modules_independent():
    # all 分支：checkin 失败不应阻止 travel 输出（结构层面验证，不发请求）
    main_path = os.path.normpath(os.path.join(HERE, "..", "scripts", "main.py"))
    mspec = importlib.util.spec_from_file_location("main_560", main_path)
    main_mod = importlib.util.module_from_spec(mspec)
    mspec.loader.exec_module(main_mod)
    src_ok = True
    try:
        src = open(CRED_PATH, encoding="utf-8").read()
        # checkin/travel 各自捕获 CredentialError 并返回 failed（而非向上抛崩）
        for mod_file in ("checkin.py", "travel.py"):
            ms = open(os.path.normpath(os.path.join(HERE, "..", "scripts", mod_file)),
                      encoding="utf-8").read()
            if "except credentials.CredentialError" not in ms:
                src_ok = False
    except OSError:
        src_ok = False
    check("T10 checkin/travel 各自捕获凭据错误（模块互不拖垮）", src_ok)
    check("T10 main.all 分别输出两个模块结果（键存在）",
           "run_checkin()" in open(os.path.normpath(os.path.join(
               HERE, "..", "scripts", "main.py")), encoding="utf-8").read()
           and "run_travel()" in open(os.path.normpath(os.path.join(
               HERE, "..", "scripts", "main.py")), encoding="utf-8").read())


def main() -> int:
    print("=" * 60)
    print("workbuddy-reward-helper v1.0.1 · 5.6.0 兼容热修测试（全 Mock）")
    print("=" * 60)
    for fn in (t1_encrypted_error, t2_no_env_no_backup, t3_backup_with_env,
               t4_wrong_uid, t5_wrong_domain, t6_expired_backup,
               t7_encrypted_backup, t8_plaintext_regression,
               t9_no_sensitive_leak, t10_modules_independent):
        fn()
    failed = [n for n, ok in RESULTS if not ok]
    print()
    print("结果：{} 项断言，{} 通过，{} 失败".format(
        len(RESULTS), len(RESULTS) - len(failed), len(failed)))
    if failed:
        for n in failed:
            print("  ❌ 失败：{}".format(n))
    print("=" * 60)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
