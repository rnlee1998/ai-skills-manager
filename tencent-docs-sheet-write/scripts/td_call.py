# -*- coding: utf-8 -*-
"""腾讯文档批量调用器 —— 绕开 PowerShell 吞双引号 / 中文编码问题。

【为什么需要它】
在 Windows PowerShell 里把 JSON 当命令行参数传给 tencentdocs.py，双引号会被吞掉。
实测：传入 {"search_key":"量化策略"}，脚本收到的是 {search_key:閲忓寲绛栫暐}
      —— 引号没了 + 中文 GBK 乱码，直接报 ERROR:bad_args_json。

本脚本从 JSON 作业文件读调用清单，用 subprocess(list) 传参
（Windows 下走 CreateProcessW + list2cmdline），双引号与中文都能保真。

【用法】
  1) 写作业文件 jobs.json（UTF-8）：
     [
       {"tool": "manage.search_file", "args": {"search_key": "量化策略"}},
       {"tool": "sheet.get_cell_data",
        "args": {"file_id": "xxx", "sheet_id": "yyy",
                 "start_row": 0, "start_col": 0, "end_row": 50, "end_col": 15,
                 "return_csv": true}},
       {"raw": ["tdoc_init"]}          // 需要跑顶层子命令时用 raw
     ]
  2) python td_call.py jobs.json [输出前缀，默认 jobs 同目录下的 _td_out]
  3) 读 <前缀>.txt 看逐条结果；
     若某条返回 csv_data，会自动另存为 <前缀>_<序号>.csv（真换行，便于 Read）

【自动处理的两件事】
  - 剥离 jsonrpc 外壳，直接给内层结果（不然整个返回是一行超长 JSON，Read 会截断）
  - csv_data 落成真正的多行文件（否则 \n 是转义字符，整张表挤在一行）
"""
import glob
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def find_plugin_dir():
    """定位 tencent-docs 插件里的 tencentdocs.py 所在目录。"""
    env = os.environ.get("TENCENT_DOCS_SKILL_DIR")
    if env and os.path.isfile(os.path.join(env, "tencentdocs.py")):
        return env
    pats = [
        os.path.join(os.path.expanduser("~"), ".workbuddy", "plugins", "cache",
                     "**", "tencent-docs-plugin", "*", "skills", "tencent-docs"),
        os.path.join(os.path.expanduser("~"), ".workbuddy", "plugins", "cache",
                     "**", "skills", "tencent-docs"),
        os.path.join(os.path.expanduser("~"), ".codebuddy", "plugins", "cache",
                     "**", "skills", "tencent-docs"),
    ]
    for p in pats:
        for d in glob.glob(p, recursive=True):
            if os.path.isfile(os.path.join(d, "tencentdocs.py")):
                return d
    raise SystemExit("找不到 tencent-docs 插件的 tencentdocs.py，"
                     "请设环境变量 TENCENT_DOCS_SKILL_DIR 指向该目录")


def unwrap(raw):
    """拆开 jsonrpc 外壳，返回内层 dict（失败返回 None）。"""
    try:
        resp = json.loads(raw)
        txt = resp["result"]["content"][0]["text"]
        return json.loads(txt)
    except Exception:
        return None


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    jobs_path = os.path.abspath(sys.argv[1])
    out_base = (sys.argv[2] if len(sys.argv) > 2
                else os.path.join(os.path.dirname(jobs_path), "_td_out"))

    base_dir = find_plugin_dir()
    py = os.environ.get("TENCENT_DOCS_PYTHON") or sys.executable

    # ⚠️ 必须给子进程强制 UTF-8。否则 Windows 下 tencentdocs.py 的 stdout 是 GBK，
    # 响应里只要出现 GBK 编不出的字符（实测：返回内容含 \xa0 不间断空格）就会
    # 在 print(rsp) 处抛 UnicodeEncodeError，整条调用白跑且看不出原因。
    child_env = dict(os.environ)
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"

    with io.open(jobs_path, encoding="utf-8") as f:
        jobs = json.load(f)

    lines = []
    for i, j in enumerate(jobs):
        if j.get("raw"):
            cmd = [py, "tencentdocs.py"] + j["raw"]
            title = " ".join(j["raw"])
        else:
            cmd = [py, "tencentdocs.py", "tdoc_call", "tencent-docs",
                   j["tool"], json.dumps(j["args"], ensure_ascii=False)]
            title = j["tool"]
        lines.append("=== [%d] %s ===" % (i, title))
        try:
            r = subprocess.run(cmd, cwd=base_dir, capture_output=True,
                               timeout=180, env=child_env)
            raw = r.stdout.decode("utf-8", "replace").strip()
            inner = unwrap(raw)
            if inner is None:
                lines.append(raw or "(no stdout)")
            elif isinstance(inner, dict) and "csv_data" in inner:
                fname = "%s_%d.csv" % (out_base, i)
                io.open(fname, "w", encoding="utf-8").write(inner["csv_data"])
                lines.append("csv_data -> %s (%d chars, %d lines)"
                             % (fname, len(inner["csv_data"]),
                                inner["csv_data"].count("\n") + 1))
                keep = {k: v for k, v in inner.items() if k != "csv_data"}
                lines.append(json.dumps(keep, ensure_ascii=False, indent=1))
            else:
                lines.append(json.dumps(inner, ensure_ascii=False, indent=1))
            e = r.stderr.decode("utf-8", "replace").strip()
            if e:
                lines.append("[stderr] " + e)
        except Exception as ex:
            lines.append("[EXC] %r" % (ex,))
        lines.append("")

    out_txt = out_base + ".txt"
    io.open(out_txt, "w", encoding="utf-8").write("\n".join(lines))
    print("wrote %s" % out_txt)


if __name__ == "__main__":
    main()
