#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
askill - 本地 Skill 管理工具
=============================
统一管理本机多个 AI 应用的 skill，让它们共享同一个仓库目录，
避免重复下载、版本分叉。

核心约定
--------
- 仓库（唯一真相源）: 本仓库根目录（由脚本位置自动推导，克隆到任意盘符均正确）
- 各应用侧只保留 junction 链接指向仓库，不存实体副本
- 开箱即用：克隆后直接 `python _scripts/askill.py link` 即可，无需任何配置

用法
----
    python _scripts/askill.py status              # 体检：查看各应用链接状态与 skill 清单
    python _scripts/askill.py list                # 列出仓库内所有 skill
    python _scripts/askill.py link                # 给已安装的应用建立/修复链接
    python _scripts/askill.py link --app trae-cn  # 只处理指定应用
    python _scripts/askill.py unlink --app trae-cn# 断开指定应用链接（还原为独立目录）
    python _scripts/askill.py sync <路径>          # 把某个 skill 目录归集进仓库
    python _scripts/askill.py here <路径>          # 把某个 skill 移动到仓库并原地留链接
    python _scripts/askill.py verify              # 校验链接有效性（能读能写）
    python _scripts/askill.py doctor              # 深度诊断：查分叉、冗余副本、孤儿文件
"""

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys

# ---------------------------------------------------------------- 配置

# 仓库根目录 = 本脚本所在目录(_scripts)的上层。
# 这样无论从哪台机器、克隆到哪个盘符，仓库位置都自动正确，无需改代码、无需配置。
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DEFAULT = os.path.dirname(SCRIPT_DIR)

META_DIRNAME = "_app_meta"
BACKUP_DIRNAME = "_backup"
SCRIPTS_DIRNAME = "_scripts"


def _default_apps():
    """默认应用注册表：基于当前用户主目录(~)推导，跨机器/跨用户名自动适配。

    需要换盘符或自定义路径时，用 askill_config.json 的 "apps" 字段覆盖即可。
    """
    home = os.path.expanduser("~")
    return {
        "workbuddy": os.path.join(home, ".workbuddy", "skills"),
        "trae-cn":   os.path.join(home, ".trae-cn", "skills"),
        "trae":      os.path.join(home, ".trae", "skills"),
        "codebuddy": os.path.join(home, ".codebuddy", "skills"),
        "claude":    os.path.join(home, ".claude", "skills"),
        "cursor":    os.path.join(home, ".cursor", "skills"),
        "codex":     os.path.join(home, ".codex", "skills"),
        "qwen":      os.path.join(home, ".qwen", "skills"),
        "iflow":     os.path.join(home, ".iflow", "skills"),
        "agents":    os.path.join(home, ".agents", "skills"),
        "gemini":    os.path.join(home, ".gemini", "skills"),
        "windsurf":  os.path.join(home, ".windsurf", "skills"),
        "roo":       os.path.join(home, ".roo", "skills"),
        "kilo":      os.path.join(home, ".kilocode", "skills"),
        "continue":  os.path.join(home, ".continue", "skills"),
        "cline":     os.path.join(home, ".cline", "skills"),
    }


APPS = _default_apps()
# 兼容旧引用：REPO 默认值等于自动推导的仓库根（随后 _load_overrides 可能覆盖）。
REPO = REPO_DEFAULT

# 不视为 skill 的仓库顶层项（内部目录一律以 _ 开头；git 仓库的 .git 也排除）
RESERVED = {SCRIPTS_DIRNAME, BACKUP_DIRNAME, META_DIRNAME, "scripts", "git"}


# ---------------------------------------------------------------- 配置覆盖层

def _expand(p):
    """展开 ~ 与环境变量，使路径可移植到其它机器"""
    try:
        p = os.path.expanduser(os.path.expandvars(p))
    except Exception:
        pass
    return p


def _load_overrides():
    """从环境变量 / 同目录 askill_config.json 覆盖 REPO 与 APPS。

    覆盖优先级：环境变量 ASKILL_REPO > askill_config.json["repo"] > 自动推导的仓库根。
    config 文件固定位于仓库根的 askill_config.json（由脚本位置推导，跨机器有效）。
    APPS 采用合并语义：config 里的键覆盖同名项，新增键追加，未提及项保留默认。
    """
    global REPO, APPS
    cfg_path = os.path.join(REPO_DEFAULT, "askill_config.json")
    cfg = {}
    if os.path.isfile(cfg_path):
        try:
            with io.open(cfg_path, encoding="utf-8", errors="replace") as f:
                cfg = json.load(f) or {}
        except Exception:
            cfg = {}
    repo = os.environ.get("ASKILL_REPO") or cfg.get("repo") or REPO_DEFAULT
    REPO = _expand(repo)
    apps = cfg.get("apps") or {}
    if isinstance(apps, dict) and apps:
        merged = dict(APPS)
        for k, v in apps.items():
            merged[k] = _expand(v)
        APPS = merged


_load_overrides()


def is_reserved(name):
    """内部目录判定：显式名单 + 任何以 _ 或 . 开头的项（顺带排除 .git 等）"""
    return name in RESERVED or name.startswith("_") or name.startswith(".")

# ---------------------------------------------------------------- 输出


def emit(lines):
    """统一用 UTF-8 写一处，避免 GBK 控制台炸掉"""
    text = "\n".join(str(x) for x in lines)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        print(text)
    except Exception:
        pass
    # 同时落盘一份，供无法回显的终端读取
    dump = os.path.join(os.environ.get("TEMP", "."), "askill_out.txt")
    try:
        with io.open(dump, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def ok(msg):
    return "  [OK]   %s" % msg


def warn(msg):
    return "  [WARN] %s" % msg


def bad(msg):
    return "  [FAIL] %s" % msg


# ---------------------------------------------------------------- 链接工具


def link_type(path):
    """返回 'junction' / 'symlink' / 'dir' / 'missing'

    注意（Python on Windows 的坑）:
    - os.path.islink() 对 junction 返回 False（只认 symlink）
    - os.stat() 会跟随 junction，把 ReparsePoint 属性规范化掉
    必须用 os.lstat() 才能看到 FILE_ATTRIBUTE_REPARSE_POINT(0x400)
    """
    if not os.path.exists(path):
        return "missing"
    # symlink：islink 直判
    if os.path.islink(path):
        return "symlink"
    # junction：必须用 lstat 看 ReparsePoint
    try:
        lst = os.lstat(path)
        attrs = getattr(lst, "st_file_attributes", 0)
        if attrs & 0x400:  # FILE_ATTRIBUTE_REPARSE_POINT
            return "junction"
    except Exception:
        pass
    # 兼容低版本 Python 无 st_file_attributes 的情况：用 os.readlink 探测
    try:
        os.readlink(path)
        return "junction"
    except (OSError, ValueError):
        pass
    return "dir"


def link_target(path):
    """读取链接目标（junction / symlink 通用）"""
    lt = link_type(path)
    if lt == "missing":
        return None
    # Python 3.8+ 的 os.readlink 支持 junction
    try:
        t = os.readlink(path)
        # readlink 对 junction 可能返回 \\?\ 前缀，去掉
        if t.startswith("\\\\?\\"):
            t = t[4:]
        return t
    except (OSError, ValueError):
        pass
    # 回退：用 PowerShell 读
    cmd = ("powershell -NoProfile -Command "
           "\"(Get-Item -LiteralPath '%s' -Force).Target\"" % path)
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=15)
        t = (p.stdout or "").strip()
        if t.startswith("\\\\?\\"):
            t = t[4:]
        return t or None
    except Exception:
        return None


def is_healthy_link(path):
    """链接存在 且 指向仓库"""
    lt = link_type(path)
    if lt not in ("junction", "symlink"):
        return False
    tgt = link_target(path)
    if not tgt:
        return False
    return os.path.normcase(os.path.normpath(tgt)) == os.path.normcase(os.path.normpath(REPO))


def make_link(link_path, target):
    """建链接：junction 优先，失败退 symlink。返回 (类型, 说明)"""
    parent = os.path.dirname(link_path)
    if parent and not os.path.exists(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except Exception as e:
            return None, "无法创建父目录: %s" % e

    for kind, flag in (("junction", "/J"), ("symlink", "/D")):
        cmd = 'cmd /c mklink %s "%s" "%s"' % (flag, link_path, target)
        try:
            subprocess.run(cmd, shell=True, capture_output=True, timeout=20)
        except Exception:
            pass
        if os.path.exists(link_path):
            try:
                os.listdir(link_path)  # 验证可读
                return kind, "成功"
            except Exception as e:
                return kind, "已创建但不可读: %s" % e
    return None, "mklink 失败（两种方式均未成功）"


def remove_path(path):
    """删除目录或链接。链接只删链接本身，不跟随。"""
    lt = link_type(path)
    if lt == "missing":
        return True
    if lt in ("junction", "symlink"):
        # 链接：直接 rmdir 删链接本身
        try:
            os.rmdir(path)
            return True
        except Exception:
            try:
                subprocess.run('cmd /c rd "%s"' % path, shell=True,
                               capture_output=True, timeout=20)
                return not os.path.exists(path)
            except Exception as e:
                return "ERR: %s" % e
    # 实体目录：逐文件删（规避本机 rename 限制）
    for dirpath, dirnames, filenames in os.walk(path, topdown=False):
        for fn in filenames:
            try:
                os.remove(os.path.join(dirpath, fn))
            except Exception:
                pass
        for dn in dirnames:
            try:
                os.rmdir(os.path.join(dirpath, dn))
            except Exception:
                pass
    try:
        os.rmdir(path)
        return True
    except Exception as e:
        return "ERR: %s" % e


# ---------------------------------------------------------------- 仓库工具


def repo_skills():
    """返回仓库内所有 skill 目录名（排序）"""
    if not os.path.isdir(REPO):
        return []
    return sorted(
        d for d in os.listdir(REPO)
        if os.path.isdir(os.path.join(REPO, d)) and not is_reserved(d)
    )


def dir_stats(path):
    """返回 (文件数, 总字节)"""
    n = 0
    b = 0
    for dirpath, _, filenames in os.walk(path):
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            n += 1
            try:
                b += os.path.getsize(fp)
            except Exception:
                pass
    return n, b


def has_skill_md(path):
    return os.path.isfile(os.path.join(path, "SKILL.md"))


def read_frontmatter(path):
    """粗略提取 SKILL.md 的 name / description"""
    sk = os.path.join(path, "SKILL.md")
    if not os.path.isfile(sk):
        return None
    try:
        with io.open(sk, encoding="utf-8", errors="replace") as f:
            head = f.read(4000)
    except Exception:
        return None
    if not head.startswith("---"):
        return None
    end = head.find("\n---", 3)
    if end < 0:
        return None
    fm = head[3:end]
    out = {}
    for line in fm.splitlines():
        line = line.strip()
        for key in ("name", "description"):
            if line.startswith(key + ":"):
                out[key] = line[len(key) + 1:].strip().strip('"').strip("'")
    return out or None


def fmt_bytes(b):
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return "%.1f %s" % (b, unit) if unit != "B" else "%d B" % b
        b /= 1024.0
    return "%.1f TB" % b


# ---------------------------------------------------------------- 命令


def cmd_status(args):
    """体检：各应用链接状态 + 仓库概况"""
    lines = []
    lines.append("=" * 68)
    lines.append("  本地 Skill 共享状态")
    lines.append("=" * 68)
    lines.append("")
    lines.append("仓库: %s" % REPO)
    if not os.path.isdir(REPO):
        lines.append(bad("仓库不存在！请先运行: python askill.py init"))
        emit(lines)
        return 1

    skills = repo_skills()
    total_files = 0
    total_bytes = 0
    for s in skills:
        n, b = dir_stats(os.path.join(REPO, s))
        total_files += n
        total_bytes += b
    lines.append("     skill 数: %d   文件数: %d   总大小: %s"
                 % (len(skills), total_files, fmt_bytes(total_bytes)))
    lines.append("")
    lines.append("-" * 68)
    lines.append("  各应用链接状态")
    lines.append("-" * 68)

    for name, path in APPS.items():
        lt = link_type(path)
        if lt == "missing":
            lines.append("  %-10s 未安装（目录不存在）" % name)
            continue
        if lt == "dir":
            # 实体目录：看里面有没有 skill
            sub = [d for d in os.listdir(path)
                   if os.path.isdir(os.path.join(path, d))
                   and not is_reserved(d)]
            if sub:
                lines.append(warn("%-10s 实体目录（有 %d 个副本，未共享！）"
                                  % (name, len(sub))))
            else:
                lines.append(warn("%-10s 实体目录（空，可转链接）" % name))
            continue
        if is_healthy_link(path):
            lines.append(ok("%-10s %s -> 仓库" % (name, lt)))
        else:
            tgt = link_target(path) or "?"
            lines.append(bad("%-10s %s 指向错误: %s" % (name, lt, tgt)))

    lines.append("")
    lines.append("提示: 运行 'python askill.py link' 修复/建立所有链接")
    emit(lines)
    return 0


def cmd_list(args):
    """列出仓库内 skill"""
    lines = []
    skills = repo_skills()
    lines.append("仓库内 skill（%d 个）: %s" % (len(skills), REPO))
    lines.append("")
    lines.append("%-32s %8s %8s  %s" % ("名称", "文件数", "大小", "描述"))
    lines.append("-" * 100)
    for s in skills:
        p = os.path.join(REPO, s)
        n, b = dir_stats(p)
        fm = read_frontmatter(p)
        desc = ""
        if fm and fm.get("description"):
            desc = fm["description"][:46]
        flag = "" if has_skill_md(p) else "  <无 SKILL.md>"
        lines.append("%-32s %8d %8s  %s%s"
                     % (s[:32], n, fmt_bytes(b), desc, flag))
    emit(lines)
    return 0


def cmd_link(args):
    """建立/修复链接"""
    targets = [args.app] if args.app else list(APPS.keys())
    lines = []
    lines.append("建立/修复应用链接")
    lines.append("")

    if not os.path.isdir(REPO):
        lines.append(bad("仓库不存在: %s" % REPO))
        emit(lines)
        return 1

    touched = 0
    for name in targets:
        if name not in APPS:
            lines.append(bad("未知应用: %s（可用: %s）"
                             % (name, ", ".join(APPS))))
            continue
        path = APPS[name]
        lt = link_type(path)

        # 目录不存在时：若该应用已安装（其父目录存在）则新建链接；否则跳过。
        # 这样 `link` 默认只对"本机已装的应用"生效，不会在未装应用上乱建目录。
        if lt == "missing":
            parent = os.path.dirname(path)
            if args.app or os.path.isdir(parent):
                kind, msg = make_link(path, REPO)
                if is_healthy_link(path):
                    lines.append(ok("%-10s 新建 %s 链接" % (name, kind or "?")))
                    touched += 1
                else:
                    lines.append(bad("%-10s 新建链接失败: %s" % (name, msg)))
            else:
                lines.append("  [SKIP] %-10s 未安装（%s 不存在）" % (name, parent))
            continue

        if is_healthy_link(path):
            lines.append(ok("%-10s 链接正常" % name))
            continue

        if lt == "dir":
            # 实体目录：先归集内容，再替换为链接
            subs = [d for d in os.listdir(path)
                    if os.path.isdir(os.path.join(path, d))
                    and not is_reserved(d)]
            if subs:
                lines.append("  %-10s 实体目录含 %d 个 skill，正在归集..."
                             % (name, len(subs)))
                for s in subs:
                    src = os.path.join(path, s)
                    dst = os.path.join(REPO, s)
                    if os.path.exists(dst):
                        # 同名：保留较大的
                        sn, sb = dir_stats(src)
                        dn, db = dir_stats(dst)
                        if sb > db:
                            lines.append("      同名 %s：源更大(%s>%s)，替换仓库版"
                                         % (s, fmt_bytes(sb), fmt_bytes(db)))
                            remove_path(dst)
                            shutil.copytree(src, dst)
                        else:
                            lines.append("      同名 %s：仓库版更大，保留仓库版"
                                         % s)
                        remove_path(src)
                    else:
                        shutil.copytree(src, dst)
                        remove_path(src)
                        lines.append("      归集 %s" % s)
            # 归档元数据（非目录文件）
            meta_files = [f for f in os.listdir(path)
                          if os.path.isfile(os.path.join(path, f))]
            if meta_files:
                md = os.path.join(REPO, META_DIRNAME, "%s_skills_meta" % name)
                os.makedirs(md, exist_ok=True)
                for f in meta_files:
                    try:
                        shutil.copy2(os.path.join(path, f),
                                     os.path.join(md, f))
                    except Exception:
                        pass
                lines.append("      归档 %d 个元数据文件" % len(meta_files))
            r = remove_path(path)
            lines.append("      清空实体目录: %s"
                         % ("OK" if r is True else r))

        # 建/重建链接
        kind, msg = make_link(path, REPO)
        if is_healthy_link(path):
            lines.append(ok("%-10s 建立 %s 链接" % (name, kind)))
            touched += 1
        else:
            lines.append(bad("%-10s 建链接失败: %s" % (name, msg)))

    lines.append("")
    lines.append("处理完成，共 %d 个应用。" % touched)
    emit(lines)
    return 0


def cmd_unlink(args):
    """断开链接，还原为空目录（仓库内容不动）"""
    if not args.app:
        emit([bad("请用 --app 指定要断开的应用")])
        return 1
    name, path = args.app, APPS.get(args.app)
    if not path:
        emit([bad("未知应用: %s" % name)])
        return 1

    lines = []
    if not is_healthy_link(path):
        lines.append(warn("%s 当前不是指向仓库的链接，无需断开" % name))
        emit(lines)
        return 0

    r = remove_path(path)
    if r is True:
        os.makedirs(path, exist_ok=True)
        lines.append(ok("%s 已断开链接（仓库内容未受影响）" % name))
    else:
        lines.append(bad("%s 断开失败: %s" % (name, r)))
    emit(lines)
    return 0


def _collect_one(src_dir, lines, move=False):
    """把单个 skill 目录归集进仓库。move=True 时原地留链接。

    注意：move 模式下给源位置建的链接指向 REPO/<skill名>（单个 skill），
    而不是 REPO 根——否则源位置会看到仓库里全部 skill，语义就错了。
    """
    name = os.path.basename(os.path.normpath(src_dir))
    if not os.path.isdir(src_dir):
        lines.append(bad("不是目录: %s" % src_dir))
        return False
    if not has_skill_md(src_dir):
        lines.append(warn("%s 下没有 SKILL.md（仍会归集，但可能不是合法 skill）"
                          % name))
    dst = os.path.join(REPO, name)

    def relink():
        """给源位置建立指向仓库内该 skill 的链接"""
        kind, msg = make_link(src_dir, dst)
        if link_type(src_dir) in ("junction", "symlink") \
                and has_skill_md(src_dir):
            lines.append(ok("  原地留 %s 链接 -> %s" % (kind, name)))
            return True
        lines.append(bad("  留链接失败: %s" % msg))
        return False

    # 已经在仓库里（且源就是仓库路径）
    if os.path.normcase(os.path.normpath(src_dir)) == os.path.normcase(os.path.normpath(dst)):
        lines.append(ok("%s 已在仓库中" % name))
        return True

    if os.path.exists(dst):
        sn, sb = dir_stats(src_dir)
        dn, db = dir_stats(dst)
        if sb > db:
            lines.append("  同名冲突 %s：源 %s > 仓库 %s，替换仓库版"
                         % (name, fmt_bytes(sb), fmt_bytes(db)))
            remove_path(dst)
            shutil.copytree(src_dir, dst)
            lines.append(ok("  已用源版本更新仓库"))
        else:
            lines.append("  同名冲突 %s：仓库版 %s >= 源 %s，保留仓库版"
                         % (name, fmt_bytes(db), fmt_bytes(sb)))
        # 无论保留哪版，move 模式下都要给源位置留链接
        if move:
            remove_path(src_dir)
            relink()
        return True

    shutil.copytree(src_dir, dst)
    sn, sb = dir_stats(dst)
    lines.append(ok("归集 %s（%d 文件, %s）" % (name, sn, fmt_bytes(sb))))

    if move:
        r = remove_path(src_dir)
        if r is True:
            relink()
        else:
            lines.append(bad("  清理源目录失败: %s" % r))
    return True


def cmd_sync(args):
    """把 skill 目录复制归集进仓库（源保留）"""
    lines = ["归集 skill 到仓库", ""]
    src = os.path.abspath(args.path)
    _collect_one(src, lines, move=False)
    emit(lines)
    return 0


def cmd_here(args):
    """把 skill 移动到仓库，并在原位置留链接"""
    lines = ["移动到仓库并留链接", ""]
    src = os.path.abspath(args.path)
    _collect_one(src, lines, move=True)
    emit(lines)
    return 0


def cmd_verify(args):
    """校验链接有效性（读写双向）"""
    lines = ["链接有效性校验", ""]
    probe = "_askill_probe.tmp"
    all_ok = True

    for name, path in APPS.items():
        if link_type(path) == "missing":
            continue
        if not is_healthy_link(path):
            lines.append(bad("%-10s 非有效链接" % name))
            all_ok = False
            continue
        # 读校验
        skills = [d for d in os.listdir(path)
                  if os.path.isdir(os.path.join(path, d))
                  and not is_reserved(d)]
        sample = skills[0] if skills else None
        readable = False
        if sample:
            readable = has_skill_md(os.path.join(path, sample))
        # 写校验
        writable = False
        try:
            pf = os.path.join(path, probe)
            with open(pf, "w") as f:
                f.write("x")
            repo_pf = os.path.join(REPO, probe)
            writable = os.path.exists(repo_pf)
            if writable:
                os.remove(repo_pf)
            elif os.path.exists(pf):
                os.remove(pf)
        except Exception:
            pass

        status = "SKILL.md可读=%s 写回仓库=%s" % (readable, writable)
        if readable and writable:
            lines.append(ok("%-10s %s" % (name, status)))
        else:
            lines.append(bad("%-10s %s" % (name, status)))
            all_ok = False

    lines.append("")
    lines.append("结论: %s" % ("全部通过" if all_ok else "存在问题，请检查"))
    emit(lines)
    return 0 if all_ok else 1


def cmd_doctor(args):
    """深度诊断"""
    lines = ["深度诊断", ""]
    issues = 0

    # 1) 各应用是否有实体副本
    lines.append("--- 1. 实体副本检测 ---")
    for name, path in APPS.items():
        lt = link_type(path)
        if lt == "dir":
            subs = [d for d in os.listdir(path)
                    if os.path.isdir(os.path.join(path, d))
                    and not is_reserved(d)]
            if subs:
                lines.append(warn("%-10s 有 %d 个实体副本: %s"
                                  % (name, len(subs), ", ".join(subs[:5]))))
                issues += 1
            else:
                lines.append(ok("%-10s 空目录" % name))
        elif lt in ("junction", "symlink"):
            if is_healthy_link(path):
                lines.append(ok("%-10s 链接正常" % name))
            else:
                lines.append(bad("%-10s 链接异常" % name))
                issues += 1
        else:
            lines.append("  [SKIP] %-10s 未安装" % name)

    # 2) 仓库 skill 合法性
    lines.append("")
    lines.append("--- 2. 仓库 skill 合法性 ---")
    bad_skills = []
    for s in repo_skills():
        p = os.path.join(REPO, s)
        if not has_skill_md(p):
            bad_skills.append(s)
        else:
            fm = read_frontmatter(p)
            if not fm or not fm.get("name"):
                bad_skills.append("%s(缺 frontmatter)" % s)
    if bad_skills:
        for b in bad_skills:
            lines.append(warn("%s" % b))
        issues += len(bad_skills)
    else:
        lines.append(ok("全部 %d 个 skill 均有合法 SKILL.md" % len(repo_skills())))

    # 3) 备份目录
    lines.append("")
    lines.append("--- 3. 备份 ---")
    bk = os.path.join(REPO, BACKUP_DIRNAME)
    if os.path.isdir(bk):
        subs = os.listdir(bk)
        lines.append(ok("备份目录存在，%d 个备份: %s"
                        % (len(subs), ", ".join(subs[:3]))))
    else:
        lines.append(warn("无备份目录"))

    # 4) 空目录/孤儿
    lines.append("")
    lines.append("--- 4. 仓库整洁度 ---")
    empty = []
    for s in repo_skills():
        n, _ = dir_stats(os.path.join(REPO, s))
        if n == 0:
            empty.append(s)
    if empty:
        for e in empty:
            lines.append(warn("空 skill 目录: %s" % e))
        issues += len(empty)
    else:
        lines.append(ok("无空 skill 目录"))

    lines.append("")
    lines.append("=" * 68)
    lines.append("诊断结论: %s" % ("发现 %d 个问题" % issues if issues else "一切正常"))
    emit(lines)
    return 0 if issues == 0 else 1


def cmd_init(args):
    """初始化仓库骨架"""
    lines = ["初始化仓库", ""]
    for d, desc in ((REPO, "仓库根"),
                    (os.path.join(REPO, SCRIPTS_DIRNAME), "脚本"),
                    (os.path.join(REPO, BACKUP_DIRNAME), "备份"),
                    (os.path.join(REPO, META_DIRNAME), "应用元数据归档")):
        if os.path.isdir(d):
            lines.append(ok("%s 已存在: %s" % (desc, d)))
        else:
            os.makedirs(d, exist_ok=True)
            lines.append(ok("创建%s: %s" % (desc, d)))
    lines.append("")
    lines.append("下一步: python askill.py link")
    emit(lines)
    return 0


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(
        prog="askill",
        description="本地 Skill 管理 — 让多个 AI 应用共享同一个 skill 仓库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("status", help="体检：应用链接状态 + 仓库概况")
    sub.add_parser("list", help="列出仓库内所有 skill")
    sub.add_parser("init", help="初始化仓库骨架")
    sub.add_parser("verify", help="校验链接有效性")
    sub.add_parser("doctor", help="深度诊断")

    p = sub.add_parser("link", help="建立/修复应用链接")
    p.add_argument("--app", help="只处理指定应用（如 trae-cn）")

    p = sub.add_parser("unlink", help="断开应用链接")
    p.add_argument("--app", required=True, help="要断开的应用")

    p = sub.add_parser("sync", help="把 skill 复制归集进仓库")
    p.add_argument("path", help="skill 目录路径")

    p = sub.add_parser("here", help="把 skill 移入仓库并原地留链接")
    p.add_argument("path", help="skill 目录路径")

    args = ap.parse_args()

    handlers = {
        "status": cmd_status,
        "list": cmd_list,
        "init": cmd_init,
        "link": cmd_link,
        "unlink": cmd_unlink,
        "sync": cmd_sync,
        "here": cmd_here,
        "verify": cmd_verify,
        "doctor": cmd_doctor,
    }

    if not args.cmd:
        ap.print_help()
        return 0
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
