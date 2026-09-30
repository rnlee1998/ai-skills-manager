# -*- coding: utf-8 -*-
"""多组合回测日志的「选股重合度 + 收益归因」分析。

回答的问题是：**截面有效的因子，在这套框架里到底有没有真的改变选股？
还是同一批票的噪声？**

用法:
    python analyze_selection_overlap.py "<日志目录>" "<a.txt,b.txt,...>" ["标签1,标签2,..."]

输出:
    <日志目录>/_selection_overlap.txt   人读报告
    （含 6 节：逐日选股重合度矩阵 / 有效独立策略聚类 / 赢家重合度 /
      分年度排名稳定性 / 超级赢家归因 / 反事实）

依赖: 同目录的 analyze_ma20_log.py（复用其 parse / pair_fifo / m0）
"""
import importlib.util
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RE_SEL = re.compile(r"^\[(\d{8})\] \[买入候选\] (.*)$")
RE_CODE = re.compile(r"\d{6}\.[A-Z]{2}")

# 兜底中文标签（日志目录里 combo 顺序固定时的默认名）
DEFAULT_LABELS = ["-1*ATR", "+1*市值", "+1*反转", "-1*量比", "-1*换手",
                  "-0.5ATR-0.5市值", "-0.5ATR+0.5市值", "-0.5ATR+0.5反转",
                  "-0.5ATR-0.5量比", "-0.3ATR-0.3量比+0.3反转", "-0.5换手+0.5市值"]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "ma20", os.path.join(HERE, "analyze_ma20_log.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def spearman(x, y):
    def rank(v):
        s = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for pos, i in enumerate(s):
            r[i] = pos + 1.0
        return r
    rx, ry = rank(x), rank(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    den = (sum((rx[i] - mx) ** 2 for i in range(n)) *
           sum((ry[i] - my) ** 2 for i in range(n))) ** 0.5
    return num / den if den else 0.0


def main():
    if len(sys.argv) < 3:
        sys.stderr.write(__doc__)
        return 1
    d = sys.argv[1]
    files = [x.strip() for x in sys.argv[2].split(",") if x.strip()]
    labels = ([x.strip() for x in sys.argv[3].split(",")]
              if len(sys.argv) > 3 else DEFAULT_LABELS[:len(files)])
    m20 = load_module()

    keys, DATA = [], {}
    for i, fn in enumerate(files, 1):
        key = "combo%d" % i
        r = m20.parse(os.path.join(d, fn))
        holds, n_open = m20.pair_fifo(r["buys"], r["sells"])
        holds = [h for h in holds if h["pnl_pct"] is not None]
        holds.sort(key=lambda x: -x["pnl_amt"])
        sel = {}
        with io.open(os.path.join(d, fn), encoding="utf-8", errors="replace") as f:
            for L in f:
                mm = RE_SEL.match(L.rstrip("\r\n"))
                # 只挑「明细行」（含 市值...得分），跳过「按因子得分取前N只」的说明行
                if mm and "(市值" in mm.group(2):
                    codes = set(RE_CODE.findall(mm.group(2)))
                    if codes:
                        sel.setdefault(mm.group(1), set()).update(codes)
        DATA[key] = dict(label=labels[i - 1] if i - 1 < len(labels) else "",
                         r=r, holds=holds, sel=sel)
        keys.append(key)
        print("parsed %s" % key, file=sys.stderr)

    W = []
    a = W.append
    a("=" * 100)
    a("多组合选股重合度与收益归因（%d 个组合）" % len(keys))
    a("=" * 100)

    # ---------- 1 重合度矩阵 ----------
    a("\n【1】逐日选股重合度矩阵")
    a("    指标 = 对每个共同交易日算 |A∩B| / max(|A|,|B|)（A/B = 当日选中的前 N 只）")
    a("    100% = 每天选完全一样的票；0% = 完全不重叠")
    a("        " + "".join("%7s" % k.replace("combo", "c") for k in keys))
    J = {}
    for k1 in keys:
        line = "  %-7s" % k1.replace("combo", "c")
        for k2 in keys:
            if k1 == k2:
                line += "%7s" % "--"
                continue
            d1, d2 = DATA[k1]["sel"], DATA[k2]["sel"]
            common = set(d1) & set(d2)
            if not common:
                line += "%7s" % "n/a"
                continue
            tot = sum(len(d1[dd] & d2[dd]) / float(max(len(d1[dd]), len(d2[dd])))
                      for dd in common)
            J[(k1, k2)] = tot / len(common) * 100
            line += "%6.1f%%" % J[(k1, k2)]
        a(line)

    ever = {k: set().union(*DATA[k]["sel"].values()) if DATA[k]["sel"] else set()
            for k in keys}
    core = set.intersection(*ever.values()) if all(ever.values()) else set()
    allu = set.union(*ever.values())
    a("")
    a("    被【全部 %d 组】选过的核心票: %d 只" % (len(keys), len(core)))
    a("    任何组合选过的并集        : %d 只" % len(allu))
    a("    → 候选总量只有 %d 只，而每组买 10 只；" % len(allu))
    a("      「换个因子」是在同一批票里换排序，不是换股票池。")
    a("")
    a("    每组合选过的标的数: " + "  ".join(
        "%s=%d" % (k.replace("combo", "c"), len(ever[k])) for k in keys))
    if core:
        for k in keys:
            a("      %-8s 覆盖全部候选的 %5.1f%%，其中属核心票 %d/%d = %.0f%%"
              % (k, len(ever[k]) * 100.0 / len(allu), len(ever[k] & core),
                 len(ever[k]), len(ever[k] & core) * 100.0 / len(ever[k])))

    # ---------- 2 有效独立策略聚类 ----------
    a("\n【2】★ 「有效独立策略数」——N 个因子不等于 N 个独立下注")
    ks = [k.replace("combo", "c") for k in keys]
    cmap = {k.replace("combo", "c"): k for k in keys}

    def get(x, y):
        return J.get((cmap[x], cmap[y]), J.get((cmap[y], cmap[x])))

    pairs = sorted([(get(x, y), x, y) for i, x in enumerate(ks)
                    for y in ks[i + 1:] if get(x, y) is not None], reverse=True)
    parent = {k: k for k in ks}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r, x, y in pairs:
        if r >= 60.0:
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry
    groups = {}
    for k in ks:
        groups.setdefault(find(k), []).append(k)
    a("    判据：逐日重合度 >= 60%% 视为同一策略族 → 归并为 %d 类" % len(groups))
    a("    年化口径 = 由日志净值曲线按 4 年折算（日志实际窗口 2020-2023）；")
    a("              注意与腾讯文档「年化收益」列口径不同，后者含更晚的快照。")
    for i, (_root, mem) in enumerate(sorted(groups.items(), key=lambda kv: -len(kv[1])), 1):
        anns = []
        for mm in sorted(mem):
            ek = cmap[mm]
            y = DATA[ek]["r"]["eq"]
            if y:
                yy = {}
                prev = m20.INIT
                for yyy in ("2020", "2021", "2022", "2023"):
                    seg = [x for x in y if x["d"] and x["d"][:4] == yyy]
                    if seg:
                        yy[yyy] = seg[-1]["total"] / prev - 1
                        prev = seg[-1]["total"]
                cp = 1.0
                for v in yy.values():
                    cp *= (1 + v)
                anns.append("%.2f%%" % ((cp ** 0.25 - 1) * 100))
            else:
                anns.append("n/a")
        a("      第%d类: %-22s 年化 %s" % (i, ",".join(sorted(mem)), " / ".join(anns)))
    if J:
        vals = list(J.values())
        a("")
        a("    重合度分布: 最小 %.1f%%  最大 %.1f%%  平均 %.1f%%"
          % (min(vals), max(vals), sum(vals) / len(vals)))
        a("    随机基准（池内 50 只抽 10 只）期望 = 10*10/50 = 20%")
        a("    → 平均约为随机的 %.1f 倍：因子并非全无信息，但远非互斥。"
          % (sum(vals) / len(vals) / 20.0))

    # ---------- 3 赢家重合度 ----------
    a("\n【3】★ 交易级赢家重合度：每组最赚的 10 笔里有多少是「共同赢家」")
    acc = {}
    for k in keys:
        for h in DATA[k]["holds"][:10]:
            acc.setdefault(h["code"], []).append((k, h["name"], h["pnl_pct"]))
    a("    标的          名称        出现在                次数   各组收益率")
    for code in sorted(acc, key=lambda c: -len(acc[c])):
        lst = acc[code]
        if len(lst) < 3:
            continue
        a("    %-13s %-10s %-20s %3d    %s"
          % (code, lst[0][1], ",".join(x[0].replace("combo", "c") for x in lst),
             len(lst), ",".join("%+.1f%%" % p for p in sorted(set(round(x[2], 1) for x in lst)))))
    multi = [c for c in acc if len(acc[c]) >= 2]
    same = [c for c in multi if len(set(round(x[2], 1) for x in acc[c])) == 1]
    a("")
    a("    ★ 多组共同进入 Top10 的标的 %d 个，其中收益率【完全相同】%d 个 = %.0f%%"
      % (len(multi), len(same), len(same) * 100.0 / max(1, len(multi))))
    a("      收益率相同的唯一解释：各组合在同一日买入、同一日卖出 → 同一笔交易。")
    a("      ⇒ 因子在这些仓位上没有起到任何区分作用。")

    # ---------- 4 年度排名稳定性 ----------
    a("\n【4】★ 分年度收益与排名稳定性（因子真有能力则应逐年稳定）")
    yrs = ("2020", "2021", "2022", "2023")
    a("    %-8s %9s %9s %9s %9s %11s" % (("combo",) + yrs + ("4年累计%",)))
    yrv = {}
    for k in keys:
        y = DATA[k]["r"]["eq"]
        prev, dd = m20.INIT, {}
        for yy in yrs:
            seg = [x for x in y if x["d"] and x["d"][:4] == yy]
            if seg:
                dd[yy] = (seg[-1]["total"] / prev - 1) * 100
                prev = seg[-1]["total"]
        yrv[k] = dd
        cp = 100.0
        for yy in yrs:
            cp *= (1 + dd.get(yy, 0) / 100.0)
        a("    %-8s %8.1f%% %8.1f%% %8.1f%% %8.1f%% %10.1f%%"
          % (k, dd.get("2020", 0), dd.get("2021", 0), dd.get("2022", 0),
             dd.get("2023", 0), cp - 100))
    a("")
    a("    年度间排名的 Spearman 秩相关（1=完全一致，0=无关）：")
    sp = []
    for i in range(len(yrs)):
        for j in range(i + 1, len(yrs)):
            v = spearman([yrv[k].get(yrs[i], 0) for k in keys],
                         [yrv[k].get(yrs[j], 0) for k in keys])
            sp.append(v)
            a("      %s vs %s : %+.2f" % (yrs[i], yrs[j], v))
    a("      平均 %.3f  → 接近 0 说明「哪个组合今年赢」基本是重新抽签。" % (sum(sp) / len(sp)))

    # ---------- 5 反事实 ----------
    a("\n【5】★ 反事实：拿掉最赚的几笔之后还剩多少")
    a("    %-8s %14s %14s %14s %14s" % ("combo", "原始", "去最好1笔", "去最好3笔", "去最好5笔"))
    surv = 0
    for k in keys:
        h = DATA[k]["holds"]
        c0 = sum(x["pnl_amt"] for x in h)
        r3 = c0 - sum(x["pnl_amt"] for x in h[:3])
        if c0 > 0 and r3 > 0:
            surv += 1
        a("    %-8s %14s %14s %14s %14s"
          % (k, m20.m0(c0), m20.m0(c0 - h[0]["pnl_amt"] if h else 0),
             m20.m0(r3), m20.m0(c0 - sum(x["pnl_amt"] for x in h[:5]))))
    a("")
    a("    剔除最赚 3 笔后仍为正的组合数: %d / %d" % (surv, len(keys)))
    a("    ⚠️ 若剔除 3~5 笔后普遍转负 → 整条策略线的利润由极少数交易决定，")
    a("       此时各组合之间的收益差更应读作噪声，而非因子能力差。")

    a("")
    a("=" * 100)
    out = os.path.join(d, "_selection_overlap.txt")
    io.open(out, "w", encoding="utf-8").write("\n".join(W))
    print("ok: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
