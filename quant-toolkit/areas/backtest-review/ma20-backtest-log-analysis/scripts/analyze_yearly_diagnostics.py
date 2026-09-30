# -*- coding: utf-8 -*-
"""
逐年口径交易诊断 + 机制错选追踪 + 运气检验
  用法: python analyze_yearly_diagnostics.py "<日志目录>" "<目标日志>" "<基线日志>" "<全部日志,供价格地图>"
  输出: <日志目录>/_yearly_diagnostics.txt
"""
import io
import os
import re
import sys
import statistics
from collections import defaultdict

import importlib.util
_SK = r"D:\WorkSpace\Myrepo\ai-skills\ma20-backtest-log-analysis\scripts"


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_SK, fn))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


amal = _load("amal", "analyze_ma20_log.py")
ascf = _load("ascf", "analyze_stop_counterfactual.py")

RE_CAND_LINE = re.compile(r"^\[(\d{8})\] \[买入候选\] (.+)$")
RE_CAND_ITEM = re.compile(r"(\d{6}\.[A-Z]{2})\(市值([\d.]+)亿 得分([+-]?[\d.]+)\)")
RE_FULL = re.compile(r"^\[(\d{8})\] \[仓位已满\]")
YEARS = ["2020", "2021", "2022", "2023"]
K8, K15, KTV = "回撤8", "回撤15", "顶背离"


def kind3(k):
    return K8 if k.startswith(K8) else (K15 if k.startswith(K15) else KTV)


def parse_cand_days(path):
    """逐日候选明细(top-N行) -> {date: [(code, cap亿, score)]}; 另回 仓位已满 计数"""
    out, full = {}, defaultdict(int)
    with io.open(path, encoding="utf-8", errors="replace") as f:
        for L in f:
            L = L.rstrip("\r\n")
            m = RE_CAND_LINE.match(L)
            if m and "(市值" in m.group(2):
                out[m.group(1)] = [(c, float(mv), float(sc))
                                   for c, mv, sc in RE_CAND_ITEM.findall(m.group(2))]
                continue
            m = RE_FULL.match(L)
            if m:
                full[m.group(1)[:4]] += 1
    return out, full


def mean(v):
    return sum(v) / len(v) if v else 0.0


def main():
    if len(sys.argv) < 5:
        sys.stderr.write(__doc__)
        return 1
    d = sys.argv[1]
    f_tgt = sys.argv[2]
    f_base = sys.argv[3]
    all_files = [x.strip() for x in sys.argv[4].split(",") if x.strip()]

    price, cal, _n = ascf.build_price_map(d, all_files)
    idx = {dd: i for i, dd in enumerate(cal)}

    rt = amal.parse(os.path.join(d, f_tgt))
    rb = amal.parse(os.path.join(d, f_base))
    ht, _ = amal.pair_fifo(rt["buys"], rt["sells"])
    hb, _ = amal.pair_fifo(rb["buys"], rb["sells"])
    cand_t, full_t = parse_cand_days(os.path.join(d, f_tgt))
    cand_b, _f2 = parse_cand_days(os.path.join(d, f_base))

    W = []
    a = W.append
    a("=" * 100)
    a("逐年口径交易诊断  目标=%s   基线=%s" % (f_tgt, f_base))
    a("价格地图(供反事实): %d 标的 / %d 价格点 / %s~%s"
      % (len(price), sum(len(v) for v in price.values()), cal[0], cal[-1]))
    bias = abs(sum(h["pnl_amt"] for h in ht) - rt["eq"][-1]["realized"])
    a("自检: 目标日志 FIFO偏差=%.0f元 (必须<100)" % bias)

    # ---------- 【1】逐年交易分解 ----------
    for tag, r, hs in (("目标", rt, ht), ("基线", rb, hb)):
        a("")
        a("【1】%s 逐年交易分解（按卖出年归属已实现盈亏）" % tag)
        a("  年份   买笔  卖笔  已实现(万)  胜率   8%档n/盈亏(万)   15%档n/盈亏(万)  背离n/盈亏(万)  均持天")
        for y in YEARS:
            hy = [h for h in hs if h["sell"][:4] == y]
            by = [b for b in r["buys"] if b["d"][:4] == y]
            if not hy and not by:
                continue
            pn = sum(h["pnl_amt"] for h in hy)
            wr = sum(1 for h in hy if h["pnl_amt"] > 0) * 100.0 / len(hy) if hy else 0
            row = "  %s  %4d  %4d  %+9.1f  %5.1f%%" % (
                y, len(by), len(hy), pn / 1e4, wr)
            for kk in (K8, K15, KTV):
                hk = [h for h in hy if kind3(h["kind"]) == kk]
                row += "  %2d/%+7.1f" % (len(hk), sum(x["pnl_amt"] for x in hk) / 1e4)
            row += "  %5.1f" % (mean([h["days"] for h in hy]) if hy else 0)
            a(row)

    # ---------- 【2】目标顶背离逐年明细 ----------
    a("")
    a("【2】目标日志 顶背离清仓 逐年明细")
    tv = [h for h in ht if kind3(h["kind"]) == KTV]
    for y in YEARS:
        hy = [h for h in tv if h["sell"][:4] == y]
        if not hy:
            a("  %s: (无)" % y)
            continue
        a("  %s: %d笔 合计%+.0f万" % (y, len(hy), sum(h["pnl_amt"] for h in hy) / 1e4))
        for h in sorted(hy, key=lambda x: -x["pnl_amt"]):
            a("      %s %s %s  浮盈%+.1f%%  %s元  持仓%d天(买%s)"
              % (h["code"], h["name"], h["sell"], h["pnl_pct"],
                 format(h["pnl_amt"], "+,.0f"), h["days"], h["buy"]))

    # ---------- 【3】基线赢家 -> 目标去向 ----------
    a("")
    a("【3】基线大赢家(浮盈>=30%) 在目标日志中的去向 —— 回答「机制改动错过了谁」")
    tgt_by_code = defaultdict(list)
    for h in ht:
        tgt_by_code[h["code"]].append(h)
    tgt_buys = set((b["d"], b["code"]) for b in rt["buys"])
    tgt_buy_codes = set(b["code"] for b in rt["buys"])
    a("  代码       名称        基线浮盈   基线退出          目标端状态")
    for h in sorted([x for x in hb if x["pnl_pct"] >= 30], key=lambda x: -x["pnl_pct"]):
        m = tgt_by_code.get(h["code"])
        if m:
            mm = min(m, key=lambda x: abs(int(x["buy"]) - int(h["buy"])))
            st = "同笔/近似: 浮盈%+.1f%% (%s, 持%d天)" % (mm["pnl_pct"], kind3(mm["kind"]), mm["days"])
        elif h["code"] in tgt_buy_codes:
            st = "买过但未成大赢家"
        elif h["code"] in rt["cand"]:
            st = "进过候选 %d 次但从未买入" % rt["cand"][h["code"]]
        else:
            st = "从未进过候选(扩池后排序/A池变化)"
        a("  %s %s  %+7.1f%%  %-14s  %s" % (
            h["code"], h["name"], h["pnl_pct"], kind3(h["kind"]), st))

    # ---------- 【4】机制错选 ----------
    a("")
    a("【4】「错过的股票」证据链（未入选名单日志不打印，只能间接测）")
    # 说明行: 其余M只未入选
    rej = defaultdict(int)          # year -> 未入选累计
    rej_days = defaultdict(int)     # year -> 有候选的买入日
    rej_max = defaultdict(int)
    with io.open(os.path.join(d, f_tgt), encoding="utf-8", errors="replace") as f:
        for L in f:
            m = re.search(r"^\[(\d{8})\] \[买入候选\] 按因子得分取前\d+只, 其余(\d+)只未入选",
                          L.rstrip("\r\n"))
            if m:
                y = m.group(1)[:4]
                rej[y] += int(m.group(2))
                rej_days[y] += 1
                rej_max[y] = max(rej_max[y], int(m.group(2)))
    a("  说明行聚合(仅买入日可见, 满仓日/OFF日完全不可见):")
    for y in YEARS:
        if rej_days[y]:
            a("    %s: 买入日%3d天, 竞争失败(未入选)累计 %4d 只次, 日均 %.1f, 单日最多 %d"
              % (y, rej_days[y], rej[y], rej[y] * 1.0 / rej_days[y], rej_max[y]))
    a("  满仓停买日(无候选可看): %s" % ", ".join("%s:%d天" % (y, full_t[y]) for y in YEARS))
    a("  ⇒ 可观测的「错过」= 满仓 %d 天 + 未入选 %d 只次 + OFF 禁买(见【5】)"
      % (sum(full_t.values()), sum(rej.values())))

    def fwd(code, d0, H):
        pts = price.get(code)
        i0 = idx.get(d0)
        if not pts or i0 is None:
            return None
        near = [(abs(idx[dd] - i0), dd, px) for dd, px in pts.items()
                if dd in idx and abs(idx[dd] - i0) <= 5]
        if not near:
            return None
        near.sort()
        ib = idx[near[0][1]]
        bpx = near[0][2]
        after = [(abs(idx[dd] - (ib + H)), dd, px) for dd, px in pts.items()
                 if dd in idx and idx[dd] > ib]
        after = [t for t in after if t[0] <= 5]
        if not after:
            return None
        after.sort()
        return after[0][2] / bpx - 1

    missed = []  # 结构上恒为空(明细行只列恰好买入的N只), 保留以验证该口径
    for dd, items in cand_t.items():
        bought = set(c for (bd, c) in tgt_buys if bd == dd)
        for c, cap, sc in items:
            if c not in bought:
                missed.append(dict(d=dd, code=c, cap=cap, sc=sc,
                                   slots=len(bought), later=(dd, c) in tgt_buys))
    a("  验证明细行口径: 候选列示 %d 笔, 其中列而未买 %d 笔(=0 说明明细行=买入集合, 无信息量)"
      % (sum(len(v) for v in cand_t.values()), len(missed)))
    a("  候选列示笔数=%d, 当日未买=%d (%.1f%%); 仓位已满天数(完全无候选): %s"
      % (sum(len(v) for v in cand_t.values()), len(missed),
         len(missed) * 100.0 / max(1, sum(len(v) for v in cand_t.values())),
         ", ".join("%s:%d天" % (y, full_t[y]) for y in YEARS)))

    cov20 = cov60 = 0
    r20s, r60s = [], []
    for m in missed:
        m["r20"] = fwd(m["code"], m["d"], 20)
        m["r60"] = fwd(m["code"], m["d"], 60)
        if m["r20"] is not None:
            cov20 += 1
            r20s.append(m["r20"])
        if m["r60"] is not None:
            cov60 += 1
            r60s.append(m["r60"])
    a("  前瞻覆盖: +20日 %.0f%%, +60日 %.0f%%（价格地图只覆盖其他日志同期持仓的票）"
      % (cov20 * 100.0 / max(1, len(missed)), cov60 * 100.0 / max(1, len(missed))))
    if r20s:
        a("  未买票随后: +20日 中位 %+.2f%% / 均值 %+.2f%%, >10%%占比 %.1f%%"
          % (statistics.median(r20s) * 100, mean(r20s) * 100,
             sum(1 for x in r20s if x > 0.10) * 100.0 / len(r20s)))
    if r60s:
        a("             +60日 中位 %+.2f%% / 均值 %+.2f%%, >30%%占比 %.1f%%"
          % (statistics.median(r60s) * 100, mean(r60s) * 100,
             sum(1 for x in r60s if x > 0.30) * 100.0 / len(r60s)))
    a("  对照: 同日已买票的 +60日 反事实（衡量「排序前段 vs 后段」差异）:")
    same = []
    for dd, items in cand_t.items():
        bought = set(c for (bd, c) in tgt_buys if bd == dd)
        for c, cap, sc in items:
            if c in bought:
                rr = fwd(c, dd, 60)
                if rr is not None:
                    same.append(rr)
    if same:
        a("    已买票 +60日: 中位 %+.2f%% / 均值 %+.2f%% (n=%d)"
          % (statistics.median(same) * 100, mean(same) * 100, len(same)))
    a("  未买但后来又买回的: %d/%d" % (sum(1 for m in missed if m["later"]), len(missed)))
    a("  【4.1】+60日涨幅最大的未买票 Top15（机制错过的潜在赢家）:")
    big = sorted([m for m in missed if m["r60"] is not None],
                 key=lambda x: -x["r60"])[:15]
    a("    日期       代码        得分    市值    +60日    后来买回")
    for m in big:
        a("    %s  %s  %+6.3f  %5.1f亿  %+6.1f%%   %s"
          % (m["d"], m["code"], m["sc"], m["cap"], m["r60"] * 100,
             "是" if m["later"] else "否"))

    # ---------- 【5】机制性停买 逐年 ----------
    a("")
    a("【5】机制性停买（目标日志）")
    for y in YEARS:
        on = sum(1 for dd, s, _ in rt["mkt"] if dd[:4] == y and s == "ON")
        off = sum(1 for dd, s, _ in rt["mkt"] if dd[:4] == y and s == "OFF")
        a("  %s: OFF禁买 %3d天(%2.0f%%)   仓位已满停买 %3d天" % (y, off, off * 100.0 / (on + off), full_t[y]))

    # ---------- 【6】运气检验 ----------
    a("")
    a("【6】运气 vs 策略（目标日志）")
    for y in YEARS + ["全部"]:
        hy = ht if y == "全部" else [h for h in ht if h["sell"][:4] == y]
        if not hy:
            continue
        srt = sorted(hy, key=lambda x: -x["pnl_amt"])
        tot = sum(h["pnl_amt"] for h in hy)
        seg = []
        for n in (1, 3, 5, 10):
            seg.append("去Top%d %+7.0f万" % (n, (tot - sum(x["pnl_amt"] for x in srt[:n])) / 1e4))
        a("  %s: 合计%+8.0f万 | %s" % (y, tot / 1e4, " | ".join(seg)))
    bmap = {}
    for h in hb:
        bmap[(h["code"], h["buy"])] = h["pnl_pct"]
    same_tr, tot_top = 0, 0
    for h in sorted(ht, key=lambda x: -x["pnl_amt"])[:10]:
        tot_top += 1
        k = (h["code"], h["buy"])
        if k in bmap and abs(bmap[k] - h["pnl_pct"]) < 0.05:
            same_tr += 1
    a("  Top10 盈利单中与基线「同 code+同买入日+同收益率」(=同一笔框架交易)的: %d/%d"
      % (same_tr, tot_top))
    bkeys = set((h["code"], h["buy"]) for h in hb)
    shared = [h for h in ht if (h["code"], h["buy"]) in bkeys]
    own = [h for h in ht if (h["code"], h["buy"]) not in bkeys]
    a("  ★ 盈亏拆分: 框架共同交易 %d笔 %s元 | v23独有交易 %d笔 %s元"
      % (len(shared), format(sum(h["pnl_amt"] for h in shared), "+,.0f"),
         len(own), format(sum(h["pnl_amt"] for h in own), "+,.0f")))
    a("    (共同=%s)" % ", ".join("%s%+.0f万" % (h["code"][:6], h["pnl_amt"] / 1e4)
                                for h in sorted(shared, key=lambda x: -x["pnl_amt"])))
    a("  ★ 背离50%%线新卖出的 50~70%%区间单, 卖出后 +60日走势:")
    for h in tv:
        if 50.0 <= h["pnl_pct"] < 70.0:
            rr = fwd(h["code"], h["sell"], 60)
            if rr is not None:
                a("    %s %s 卖于%s 浮盈%+.1f%% → 其后+60日 %+0.1f%%"
                  % (h["code"], h["name"], h["sell"], h["pnl_pct"], rr * 100))
            else:
                a("    %s %s 卖于%s 浮盈%+.1f%% → 价格地图无后续数据"
                  % (h["code"], h["name"], h["sell"], h["pnl_pct"]))
    a("  买入标的市值(候选明细口径, 亿) 中位: 目标 %.1f vs 基线 %.1f"
      % (statistics.median([cap for items in cand_t.values() for _c, cap, _s in items]),
         statistics.median([cap for items in cand_b.values() for _c, cap, _s in items])))
    base_codes = set(b["code"] for b in rb["buys"])
    tgt_codes = set(b["code"] for b in rt["buys"])
    inter = tgt_codes & base_codes
    a("  买入标的集合重合: |目标|=%d |基线|=%d 交集=%d (Jaccard %.2f)  目标独有=%d"
      % (len(tgt_codes), len(base_codes), len(inter),
         len(inter) * 1.0 / len(tgt_codes | base_codes), len(tgt_codes - base_codes)))
    for y in YEARS:
        ty = set(b["code"] for b in rt["buys"] if b["d"][:4] == y)
        by2 = set(b["code"] for b in rb["buys"] if b["d"][:4] == y)
        a("    %s: 目标%3d只 基线%3d只 交集%3d 目标独有%3d"
          % (y, len(ty), len(by2), len(ty & by2), len(ty - by2)))

    out = os.path.join(d, "_yearly_diagnostics.txt")
    io.open(out, "w", encoding="utf-8").write("\n".join(W))
    print("ok:", out)


if __name__ == "__main__":
    main()
