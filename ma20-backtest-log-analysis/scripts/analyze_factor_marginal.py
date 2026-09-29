# -*- coding: utf-8 -*-
"""因子「边际贡献」诊断 —— 回答「截面有效的因子，为什么在这套策略里失灵」。

设计要点（为什么这么做）
------------------------
11 个组合共用同一股票池、同一择时、同一卖出规则，只有**排序权重**不同。
但**不能**简单地按「被几个组合买过」来分层：绝大多数买入日是「只买 1 只」，
谁有空位是路径依赖的 → 共识度会被「槽位空档的日历巧合」污染。

正确做法：只用**同口径建仓日**——即「10~11 个组合同日各建仓 8~10 只」的日子。
这些天所有组合同时重建组合，槽位不构成差异，各组的选股差异**只能**来自因子。
在此子样本上按「当日被几个组同时选中」分层，得到的结论才是干净的。

其余输出：
  B. 按退出规则分组的持仓天数（验证「信号周期 vs 持仓周期」错配）
  C. 各因子组的大赢家数量（验证「因子是否选掉了趋势股」）
  D. 全样本共识度分层（附污染说明，仅供参考）

用法:
    python analyze_factor_marginal.py "<日志目录>" "<a.txt,b.txt,...>" "<标签1,标签2,...>"
输出:
    <日志目录>/_factor_marginal.txt
"""
import importlib.util
import io
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

FACTORS = {
    "combo1":  ("-ATR",),
    "combo2":  ("+市值",),
    "combo3":  ("+反转",),
    "combo4":  ("-量比",),
    "combo5":  ("-换手",),
    "combo6":  ("-ATR", "-市值"),
    "combo7":  ("-ATR", "+市值"),
    "combo8":  ("-ATR", "+反转"),
    "combo9":  ("-ATR", "-量比"),
    "combo10": ("-ATR", "-量比", "+反转"),
    "combo11": ("-换手", "+市值"),
}
GROUPS = {
    "-量比": ["combo4", "combo9", "combo10"],
    "-换手": ["combo5", "combo11"],
    "+市值": ["combo2", "combo7", "combo11"],
    "+反转": ["combo3", "combo8", "combo10"],
    "-ATR":  ["combo1", "combo6", "combo7", "combo8", "combo9", "combo10"],
}
KINDS = ("回撤8%档+破MA5", "回撤15%档+破MA5", "顶背离清仓")

CLEAN_MIN_COMBOS = 8      # 干净日：至少这么多组合同日建仓
CLEAN_MIN_BUYS = 6        # 且每组至少买这么多只


def load_m20():
    spec = importlib.util.spec_from_file_location(
        "ma20", os.path.join(HERE, "analyze_ma20_log.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def median(v):
    if not v:
        return 0.0
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def mean(v):
    return sum(v) / len(v) if v else 0.0


def main():
    if len(sys.argv) < 3:
        sys.stderr.write(__doc__)
        return 1
    d = sys.argv[1]
    files = [x.strip() for x in sys.argv[2].split(",") if x.strip()]
    labels = ([x.strip() for x in sys.argv[3].split(",")]
              if len(sys.argv) > 3 else [""] * len(files))
    m20 = load_m20()

    keys, DATA = [], {}
    for i, fn in enumerate(files, 1):
        key = "combo%d" % i
        r = m20.parse(os.path.join(d, fn))
        holds, n_open = m20.pair_fifo(r["buys"], r["sells"])
        holds = [h for h in holds if h["pnl_pct"] is not None]
        DATA[key] = dict(label=labels[i - 1], r=r, holds=holds, n_open=n_open)
        keys.append(key)
        print("parsed %s" % key, file=sys.stderr)

    # 年化（净值曲线按 4 年折算）
    ann = {}
    for k in keys:
        prev, cp = m20.INIT, 1.0
        for yy in ("2020", "2021", "2022", "2023"):
            seg = [x for x in DATA[k]["r"]["eq"] if x["d"] and x["d"][:4] == yy]
            if seg:
                cp *= seg[-1]["total"] / prev
                prev = seg[-1]["total"]
        ann[k] = (cp ** 0.25 - 1) * 100

    # 逐组合逐日买入
    daybuys = {k: defaultdict(list) for k in keys}
    for k in keys:
        for h in DATA[k]["holds"]:
            daybuys[k][h["buy"]].append(h)
    alldays = sorted({dd for k in keys for dd in daybuys[k]})
    clean = [dd for dd in alldays
             if sum(1 for k in keys
                    if len(daybuys[k].get(dd, [])) >= CLEAN_MIN_BUYS
                    ) >= CLEAN_MIN_COMBOS]

    W = []
    a = W.append
    a("=" * 106)
    a("因子「边际贡献」诊断 —— 截面有效 ≠ 框架内有效 (%d 个组合)" % len(keys))
    a("=" * 106)

    # ---------- 1 干净建仓日 ----------
    a("\n【1】★★ 干净建仓日（同口径横截面样本）")
    a("    定义：当日有 >=%d 个组合各买入 >=%d 只 → 所有组合同时重建组合，"
      % (CLEAN_MIN_COMBOS, CLEAN_MIN_BUYS))
    a("          槽位空档不构成差异，各组的选股差异**只能来自因子**。")
    a("    %-10s %8s %s" % ("日期", "建仓组数", "各组买入笔数"))
    for dd in clean:
        det = " ".join("%s=%d" % (k.replace("combo", "c"),
                                  len(daybuys[k].get(dd, []))) for k in keys)
        a("    %-10s %8d %s" % (dd, sum(1 for k in keys
                                       if len(daybuys[k].get(dd, [])) >= CLEAN_MIN_BUYS), det))
    a("    → 共 %d 天；年份分布：%s" % (
        len(clean),
        ", ".join("%s:%d" % (y, sum(1 for x in clean if x[:4] == y))
                  for y in sorted({x[:4] for x in clean}))))

    # ---------- 2 干净日内的「共识 vs 独有」 ----------
    a("\n【2】★★ 干净建仓日内的「共识度 vs 收益率」—— 本报告最干净的检验")
    a("    只统计干净日买入的股票；共识度 = 当日有几组同时选了它。")
    a("    收益率取同一 (股票,买入日) 在各组的中位数。")
    rec = defaultdict(list)      # (code, day) -> [pnl_pct...]
    nsel = defaultdict(int)      # (code, day) -> 当日有几组买了它
    for dd in clean:
        for k in keys:
            codes = sorted({x["code"] for x in daybuys[k].get(dd, [])})
            for code in codes:
                nsel[(code, dd)] += 1
                for x in daybuys[k].get(dd, []):
                    if x["code"] == code:
                        rec[(code, dd)].append(x["pnl_pct"])
    bk = defaultdict(list)
    for kk, v in rec.items():
        c = nsel[kk]
        lab = ("9~11组" if c >= 9 else "7~8组" if c >= 7 else
               "5~6组" if c >= 5 else "3~4组" if c >= 3 else "1~2组")
        bk[lab].append(median(v))
    a("    %-10s %6s %12s %12s %10s" % ("共识度", "只数", "平均收益率", "中位收益率", "胜率"))
    for lab in ("9~11组", "7~8组", "5~6组", "3~4组", "1~2组"):
        v = bk[lab]
        if v:
            a("    %-10s %6d %11.2f%% %11.2f%% %9.1f%%" % (
                lab, len(v), mean(v), median(v),
                len([x for x in v if x > 0]) * 100.0 / len(v)))
    a("")
    a("    按组合看：干净建仓日里，各组的平均收益率（同池同日同敞口）")
    a("    %-8s %-24s %8s %13s %11s" % ("combo", "因子", "建仓只数", "干净日均收益", "全样本均收益"))
    coh = {}
    for k in keys:
        v = []
        for dd in clean:
            v.extend(h["pnl_pct"] for h in daybuys[k].get(dd, []))
        coh[k] = v
        allp = [h["pnl_pct"] for h in DATA[k]["holds"]]
        a("    %-8s %-24s %8d %12.2f%% %10.2f%%" % (
            k, DATA[k]["label"], len(v), mean(v), mean(allp)))
    fv = defaultdict(list)
    for k, v in coh.items():
        for f in FACTORS[k]:
            fv[f].append(mean(v))
    a("")
    a("    按因子归并（干净建仓日平均收益率）：")
    for f in sorted(fv, key=lambda x: -mean(fv[x])):
        a("      %-8s %+7.2f%%" % (f, mean(fv[f])))

    # 稳健性：逐日看，共识度结论是不是由某一天单独造成的
    a("")
    a("    逐日稳健性（每天各自算：高共识组 vs 低共识组 的平均收益率）")
    a("    %-10s %8s %14s %14s %10s" % (
        "日期", "只数", "共识>=7 平均", "共识<=2 平均", "差值"))
    nwin = 0
    for dd in clean:
        hi, lo = [], []
        for k in keys:
            for h in daybuys[k].get(dd, []):
                c = nsel[(h["code"], dd)]
                (hi if c >= 7 else lo if c <= 2 else []).append(h["pnl_pct"])
        if hi and lo:
            nwin += 1 if mean(lo) > mean(hi) else 0
            a("    %-10s %8d %13.2f%% %13.2f%% %9.2f%%" % (
                dd, len(hi) + len(lo), mean(hi), mean(lo),
                mean(lo) - mean(hi)))
    a("    → 「低共识更好」在 %d 天里成立（共 %d 天可比较）" % (nwin, len(clean)))

    # ---------- 3 持仓周期 × 退出规则 ----------
    a("\n【3】★★ 持仓天数 × 退出规则 —— 「信号周期 vs 持仓周期」错配")
    a("    %-8s %-24s  %17s  %17s  %17s" % (
        "combo", "因子", "8%档+破MA5", "15%档+破MA5", "MACD顶背离"))
    a("    %-8s %-24s  %5s%6s%6s  %5s%6s%6s  %5s%6s%6s" % (
        "", "", "笔", "均天", "中位", "笔", "均天", "中位", "笔", "均天", "中位"))
    pool = defaultdict(list)
    for k in keys:
        row = []
        for kd in KINDS:
            v = [h["days"] for h in DATA[k]["holds"] if h["kind"] == kd]
            pool[kd].extend(v)
            row.append("%5d%6.0f%6.0f" % (len(v), mean(v), median(v)) if v
                       else "%5s%6s%6s" % ("-", "-", "-"))
        a("    %-8s %-24s  %s  %s  %s" % (k, DATA[k]["label"], row[0], row[1], row[2]))
    a("")
    a("    全组合汇总：")
    a("    %-22s %7s %11s %11s %9s %9s" % (
        "退出规则", "笔数", "均持仓天", "中位天数", "最短", "最长"))
    for kd in KINDS:
        v = pool[kd]
        if v:
            a("    %-22s %7d %11.1f %11.0f %9d %9d" % (
                kd, len(v), mean(v), median(v), min(v), max(v)))

    # ---------- 4 大赢家数量 ----------
    a("\n【4】★★ 各组的「大赢家」数量 —— 因子有没有把趋势股选掉")
    a("    %-8s %-24s %8s %8s %8s %8s %10s" % (
        "combo", "因子", "最大浮盈", ">30%", ">50%", ">100%", "顶背离笔数"))
    big = {}
    for k in keys:
        pf = [h["pnl_pct"] for h in DATA[k]["holds"]]
        ndb = len([h for h in DATA[k]["holds"] if h["kind"] == "顶背离清仓"])
        big[k] = (len([x for x in pf if x > 50]), len([x for x in pf if x > 100]), ndb)
        a("    %-8s %-24s %7.1f%% %8d %8d %8d %10d" % (
            k, DATA[k]["label"], max(pf), len([x for x in pf if x > 30]),
            big[k][0], big[k][1], ndb))
    a("")
    a("    按因子归并（平均）：")
    a("    %-8s %10s %10s %10s" % ("因子", ">50%笔数", ">100%笔数", "顶背离笔数"))
    fbig = defaultdict(list)
    for k, v in big.items():
        for f in FACTORS[k]:
            fbig[f].append(v)
    for f in sorted(fbig, key=lambda x: -mean([z[0] for z in fbig[x]])):
        a("    %-8s %10.2f %10.2f %10.2f" % (
            f, mean([z[0] for z in fbig[f]]), mean([z[1] for z in fbig[f]]),
            mean([z[2] for z in fbig[f]])))

    # ---------- 5 全样本共识度（附污染说明） ----------
    a("\n【5】全样本共识度分层（⚠️ 有污染，仅作参考）")
    a("    ⚠️ 全样本下 74~80% 的买入日是「只买 1 只」，谁有空位是路径依赖的 →")
    a("       共识度与「当日有几组恰好有空位」强相关，不能当作纯因子共识。")
    tk = defaultdict(list)
    for k in keys:
        for h in DATA[k]["holds"]:
            tk[(h["code"], h["buy"])].append((k, h["pnl_pct"]))
    cons = {kk: len(set(c for c, _ in v)) for kk, v in tk.items()}
    hist = defaultdict(int)
    for v in cons.values():
        hist[v] += 1
    a("    共识度分布: " + "  ".join("%2d组=%3d笔" % (c, hist[c])
                                    for c in sorted(hist, reverse=True)))
    bk2 = defaultdict(list)
    for kk, v in tk.items():
        c = cons[kk]
        lab = ("8~11组" if c >= 8 else "5~7组" if c >= 5 else
               "3~4组" if c >= 3 else "1~2组")
        bk2[lab].append(median([x[1] for x in v]))
    a("    %-10s %6s %12s %12s %10s" % ("共识度", "只数", "平均收益率", "中位收益率", "胜率"))
    for lab in ("8~11组", "5~7组", "3~4组", "1~2组"):
        v = bk2[lab]
        if v:
            a("    %-10s %6d %11.2f%% %11.2f%% %9.1f%%" % (
                lab, len(v), mean(v), median(v),
                len([x for x in v if x > 0]) * 100.0 / len(v)))

    # ---------- 6 量比 vs 换手 ----------
    a("\n【6】★★ 量比 vs 换手 —— 同为「量能类」因子，结果为何相反")
    a("    %-8s %-14s %10s %13s %11s %11s %10s" % (
        "因子", "各组", "年化均值", "建仓日均%", "8%档均天", ">50%笔数", "顶背离"))
    for f, ks in GROUPS.items():
        ks = [k for k in ks if k in coh]
        if not ks:
            continue
        a("    %-8s %-14s %9.2f%% %12.2f%% %10.1f %10.2f %10.2f" % (
            f, ",".join(k.replace("combo", "c") for k in ks),
            mean([ann[k] for k in ks]), mean([mean(coh[k]) for k in ks]),
            mean([mean([h["days"] for h in DATA[k]["holds"]
                        if h["kind"] == "回撤8%档+破MA5"]) for k in ks]),
            mean([big[k][0] for k in ks]), mean([big[k][2] for k in ks])))
    a("")
    a("    （combo11 同时含 -换手 与 +市值，两行都计入；combo10 含 -量比 与 +反转）")

    # ---------- 7 退出规则盈亏 × 因子组 ----------
    a("\n【7】★★ 钱是在哪一档丢掉的 —— 退出规则盈亏按因子组汇总")
    a("    三档之和 = 该组各组已实现盈亏之和（穷尽分解，已校验）")
    a("    %-8s %-14s %14s %14s %14s %14s" % (
        "因子", "各组", "8%档+破MA5", "15%档+破MA5", "MACD顶背离", "合计"))
    for f, ks in GROUPS.items():
        ks = [k for k in ks if k in coh]
        if not ks:
            continue
        sums = {}
        for kd in KINDS:
            sums[kd] = sum(h["pnl_amt"] for k in ks for h in DATA[k]["holds"]
                           if h["kind"] == kd)
        a("    %-8s %-14s %14s %14s %14s %14s" % (
            f, ",".join(k.replace("combo", "c") for k in ks),
            m20.m0(sums[KINDS[0]]), m20.m0(sums[KINDS[1]]),
            m20.m0(sums[KINDS[2]]), m20.m0(sum(sums.values()))))
    a("")
    a("    8%档占总平仓比例（越高=越依赖这个亏损档）：")
    for f, ks in GROUPS.items():
        ks = [k for k in ks if k in coh]
        if not ks:
            continue
        n8 = sum(1 for k in ks for h in DATA[k]["holds"]
                 if h["kind"] == KINDS[0])
        nt = sum(len(DATA[k]["holds"]) for k in ks)
        a("      %-8s %5.1f%%" % (f, n8 * 100.0 / nt))

    a("")
    a("    ★★ 按「每组平均」归一化 —— 这是判断「因子到底在哪一档起作用」的关键")
    a("    %-8s %7s %14s %14s %14s" % (
        "因子", "组数", "8%档/组", "15%档/组", "顶背离/组"))
    tier_mean = {}
    for f, ks in GROUPS.items():
        ks = [k for k in ks if k in coh]
        if not ks:
            continue
        row = []
        for kd in KINDS:
            s = sum(h["pnl_amt"] for k in ks for h in DATA[k]["holds"]
                    if h["kind"] == kd)
            row.append(s / len(ks))
        tier_mean[f] = row
        a("    %-8s %7d %14s %14s %14s" % (
            f, len(ks), m20.m0(row[0]), m20.m0(row[1]), m20.m0(row[2])))
    if tier_mean:
        for j, kd in enumerate(KINDS):
            vs = [tier_mean[f][j] for f in tier_mean]
            lo, hi = min(vs), max(vs)
            a("      %-14s 各组间极差 %s（最大/最小 = %.2f 倍）"
              % (kd, m20.m0(hi - lo),
                 (hi / lo) if lo > 0 else (abs(lo) / hi if hi else 0)))
    a("")
    a("    ★★ 顶背离档「每笔平均盈亏」—— 差异的第二个维度（笔数 × 单笔金额）")
    a("    %-8s %10s %16s %16s" % ("因子", "顶背离笔数", "顶背离总盈亏/笔", "顶背离/组"))
    for f, ks in GROUPS.items():
        ks = [k for k in ks if k in coh]
        if not ks:
            continue
        n = sum(1 for k in ks for h in DATA[k]["holds"] if h["kind"] == KINDS[2])
        s = sum(h["pnl_amt"] for k in ks for h in DATA[k]["holds"]
                if h["kind"] == KINDS[2])
        a("    %-8s %10d %16s %16s" % (
            f, n, m20.m0(s / n) if n else "-",
            m20.m0(s / len(ks))))

    a("\n" + "=" * 106)
    out = os.path.join(d, "_factor_marginal.txt")
    io.open(out, "w", encoding="utf-8").write("\n".join(W))
    print("ok: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
