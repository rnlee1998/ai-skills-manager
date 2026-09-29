# -*- coding: utf-8 -*-
"""
8% 止损反事实检验（csi1000_backtest_log_*.txt）

回答的问题: 「8%档止损亏掉的这些交易，如果不止损会怎样？」

方法:
  1. 扫描全部日志的持仓明细块（每只持仓股每天的 现价），加上买卖成交价，
     交叉拼出 code -> {date: price} 的价格地图（各组合持仓重叠，覆盖率高）。
  2. 对每个 8%档止损事件（只用 v19 引擎 c1~c11 的事件，卖出规则一致），
     在价格地图里查卖出日之后 +5/+10/+20/+60 交易日的价格，算反事实收益。
  3. 模拟三种处置: A=按规则止损(基准,0)；B=放宽到12%止损；C=完全不止损持有60日。

用法:
    python analyze_stop_counterfactual.py "<日志目录>" "<文件1,文件2,...>" "<v19文件子集>"
输出:
    <日志目录>/_stop_counterfactual.txt
"""
import io
import os
import re
import sys
import statistics
from collections import defaultdict

import importlib.util
_SK = r"D:\WorkSpace\Myrepo\ai-skills\ma20-backtest-log-analysis\scripts"
_spec = importlib.util.spec_from_file_location(
    "amal", os.path.join(_SK, "analyze_ma20_log.py"))
amal = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(amal)

# 持仓明细行:  代码 名称 持仓量 成本价 现价 市值 相关性 盈亏额 (盈亏%)
# 名称可含空格(特 力Ａ)，用数量锚点
RE_POSLINE = re.compile(
    r"^\s{2}(\d{6}\.[A-Z]{2})\s+(.+?)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+"
    r"([\d.]+)\s+([+-][\d.]+)\s+([+-][\d.]+)\s+\(")


def build_price_map(d, files):
    """code -> {date: px}，来源: 持仓明细块现价 + 买卖成交价"""
    price = defaultdict(dict)
    cal = set()
    n_posline = {}
    for fn in files:
        p = os.path.join(d, fn)
        pos_date = None
        n = 0
        with io.open(p, encoding="utf-8", errors="replace") as f:
            for L in f:
                L = L.rstrip("\r\n")
                m = amal.RE_MKT.match(L)
                if m:
                    cal.add(m.group(1))
                    continue
                m = amal.RE_POS.match(L)
                if m:
                    pos_date = m.group(1)
                    continue
                m = RE_POSLINE.match(L)
                if m and pos_date:
                    price[m.group(1)][pos_date] = float(m.group(5))
                    n += 1
                    continue
                m = amal.RE_BUY.match(L)
                if m:
                    price[m.group(2)][m.group(1)] = float(m.group(5))
                    continue
                m = amal.RE_SELL.match(L)
                if m:
                    price[m.group(2)][m.group(1)] = float(m.group(5))
        n_posline[fn] = n
    return price, sorted(cal), n_posline


def main():
    if len(sys.argv) < 4:
        sys.stderr.write(__doc__)
        return 1
    d = sys.argv[1]
    all_files = [x.strip() for x in sys.argv[2].split(",") if x.strip()]
    v19_files = [x.strip() for x in sys.argv[3].split(",") if x.strip()]

    price, cal, n_posline = build_price_map(d, all_files)
    idx = {dd: i for i, dd in enumerate(cal)}

    W = []
    a = W.append
    a("=" * 96)
    a("8% 止损反事实检验  ——  「不止损会亏更多吗？」")
    a("=" * 96)
    a("价格地图: %d 个标的, %d 个交易日(%s ~ %s), %d 个价格点"
      % (len(price), len(cal), cal[0], cal[-1], sum(len(v) for v in price.values())))
    a("持仓明细行捕获(每文件): " + " ".join("%s:%d" % kv for kv in n_posline.items()))

    # ---- 收集 v19 的 8%档 事件
    events = []
    for i, fn in enumerate(v19_files, 1):
        r = amal.parse(os.path.join(d, fn))
        holds, _ = amal.pair_fifo(r["buys"], r["sells"])
        for h in holds:
            if h["kind"].startswith("回撤8") and h["pnl_pct"] is not None:
                h["src"] = "c%d" % i
                events.append(h)
    a("\n8%%档止损事件(v19 引擎 c1~c%d): %d 笔" % (len(v19_files), len(events)))

    def fwd(code, sd, H, tol=3):
        """卖出日后第 H 个交易日附近的价格 -> 收益率; 无数据返回 None"""
        i0 = idx[sd]
        best = None
        for dd, px in price.get(code, {}).items():
            i = idx.get(dd)
            if i is None or i <= i0:
                continue
            if abs(i - (i0 + H)) <= tol:
                if best is None or abs(i - (i0 + H)) < abs(idx[best[0]] - (i0 + H)):
                    best = (dd, px)
        return None if best is None else best[1] / a_px - 1

    def fwd_ext(code, sd, lo=1, hi=60):
        """(卖出日后 lo~hi 日内的最小/最大收益率, 对应日)"""
        i0 = idx[sd]
        lo_r = hi_r = None
        for dd, px in price.get(code, {}).items():
            i = idx.get(dd)
            if i is None or not (i0 + lo <= i <= i0 + hi):
                continue
            r = px / a_px - 1
            if lo_r is None or r < lo_r[0]:
                lo_r = (r, dd)
            if hi_r is None or r > hi_r[0]:
                hi_r = (r, dd)
        return (lo_r or (None, None)), (hi_r or (None, None))

    # ---- 逐事件反事实
    rows = []
    for h in events:
        global a_px
        a_px = h["sell_px"]
        code, sd = h["code"], h["sell"]
        r5, r10, r20, r60 = (fwd(code, sd, H) for H in (5, 10, 20, 60))
        (rmin, dmin), (rmax, dmax) = fwd_ext(code, sd)
        rows.append(dict(src=h["src"], code=code, name=h["name"].replace(" ", ""),
                         buy=h["buy"], sell=sd, pnl=h["pnl_pct"],
                         amt=h["sell_px"] * 0 + h["pnl_amt"], sell_amt=None,
                         r5=r5, r10=r10, r20=r20, r60=r60,
                         rmin=rmin, rmax=rmax))
    # sell_amt 没在 holds 里 -> 用 pnl_amt/pnl_pct 反推基数（pnl_pct 是相对成本的浮动盈亏%）
    # 更稳妥: 直接用 (pnl_amt / (pnl_pct/100)) = 持仓成本额
    for x in rows:
        x["cost_amt"] = abs(x["amt"] / (x["pnl"] / 100.0)) if x["pnl"] else None

    HORS = ("r5", "r10", "r20", "r60")
    a("\n【1】反事实收益率分布: 被止损后如果继续持有 H 个交易日")
    a("  %-6s %7s %9s %9s %9s %9s" % ("视野", "覆盖%", "中位", "均值", ">0占比", "样本"))
    for k, lab in zip(HORS, ("+5日", "+10日", "+20日", "+60日")):
        v = [x[k] for x in rows if x[k] is not None]
        if not v:
            a("  %-6s   无数据" % lab)
            continue
        a("  %-6s %6.1f%% %+8.2f%% %+8.2f%% %8.1f%% %7d"
          % (lab, len(v) * 100.0 / len(rows), statistics.median(v) * 100,
             sum(v) / len(v) * 100,
             len([t for t in v if t > 0]) * 100.0 / len(v), len(v)))

    # 分层: 止损时仍浮盈(gave_back) vs 止损时已亏损
    a("\n【2】分层: 止损时「仍浮盈」vs「已亏损」(核心: 止损砍掉的是谁)")
    for lab, sel in (("仍浮盈>0", lambda x: x["pnl"] > 0),
                     ("已亏损<=0", lambda x: x["pnl"] <= 0),
                     ("其中深亏<-8%", lambda x: x["pnl"] < -8)):
        sub = [x for x in rows if sel(x)]
        if not sub:
            continue
        a("  -- %s: %d 笔 (%.1f%%), 止损时平均浮盈 %+.1f%%"
          % (lab, len(sub), len(sub) * 100.0 / len(rows),
             sum(x["pnl"] for x in sub) / len(sub)))
        for k, hl in zip(HORS, ("+5日", "+10日", "+20日", "+60日")):
            v = [x[k] for x in sub if x[k] is not None]
            if v:
                a("       %s: 中位%+.2f%%  均值%+.2f%%  >0占%.1f%%  n=%d"
                  % (hl, statistics.median(v) * 100, sum(v) / len(v) * 100,
                     len([t for t in v if t > 0]) * 100.0 / len(v), len(v)))

    # 止损后继续下跌的风险（放宽止损会多亏多少）
    a("\n【3】止损后价格继续下探的风险 (卖出后60日内相对卖出价的最低点)")
    v = [x["rmin"] for x in rows if x["rmin"] is not None]
    if v:
        buck = defaultdict(int)
        for t in v:
            buck["<=-15%" if t <= -0.15 else
                 "-15~-10%" if t <= -0.10 else
                 "-10~-5%" if t <= -0.05 else
                 "-5~0%" if t < 0 else ">=0%"] += 1
        order = ("<=-15%", "-15~-10%", "-10~-5%", "-5~0%", ">=0%")
        a("  覆盖 %d 笔; 最低点分布: " % len(v) + "  ".join(
            "%s:%.1f%%" % (k, buck[k] * 100.0 / len(v)) for k in order))
        deep = [x for x in rows if x["rmin"] is not None and x["rmin"] <= -0.05]
        if deep:
            v60 = [x["r60"] for x in deep if x["r60"] is not None]
            a("  其中先下探<=-5%%的 %d 笔: 其+60日中位%s"
              % (len(deep), "%.2f%%" % (statistics.median(v60) * 100) if v60 else "无数据"))

    # ---- 三种处置模拟（按可配比样本）
    a("\n【4】三种处置模拟 (仅用反事实数据齐全的事件, 按成本额加权)")
    sub = [x for x in rows if all(x[k] is not None for k in ("r20", "r60"))
           and x["rmin"] is not None and x["cost_amt"]]
    a("  可配比样本: %d / %d 笔, 覆盖成本额 %.0f 万"
      % (len(sub), len(rows), sum(x["cost_amt"] for x in sub) / 1e4))

    def scen(label, fn, sample=None):
        tot = d_ = 0.0
        n_better = 0
        s = sample if sample is not None else sub
        if not s:
            return
        for x in s:
            base = 0.0                       # A: 按规则止损(实际已发生)
            alt = fn(x)
            d_ += (alt - base) * x["cost_amt"]
            tot += x["cost_amt"]
            n_better += 1 if alt > 0 else 0
        a("  %-28s 相对基准增厚 %+9.0f 元 (%+6.2f%% of 成本额), 单笔改善占比 %.1f%%"
          % (label, d_, d_ * 100.0 / tot if tot else 0,
             n_better * 100.0 / len(s)))

    scen("B1 放宽12%止损(近似)", lambda x: x["rmin"] if x["rmin"] <= -0.04 else 0.0)
    scen("B2 只放宽到-4%再止损", lambda x: min(x["rmin"], 0.0) if x["rmin"] < 0 else 0.0)
    scen("C  不止损持有+20日", lambda x: x["r20"])
    scen("D  不止损持有+60日", lambda x: x["r60"])
    sub2 = [x for x in sub if x["code"] not in ("002756.SZ", "000913.SZ")]
    scen("D' 同上,剔除002756/000913", lambda x: x["r60"], sub2)
    a("  注: B1 把「先多跌4%才触发12%止损」近似成 rmin<=-4% 时取 rmin（偏保守），"
      "其余按未触发=0。")
    a("  注: 未计入止损释放资金再投资的收益（这是保留止损的正贡献，见报告文字）。")

    # D 的贡献分解: 增厚额 = r60 * 成本额
    a("\n  【4.1】D 场景(+60日)贡献分解 Top8 —— 检验是否又是少数票撑起来的")
    contrib = sorted(sub, key=lambda x: -(x["r60"] * x["cost_amt"]))
    tot_d = sum(x["r60"] * x["cost_amt"] for x in sub)
    cum = 0.0
    for x in contrib[:8]:
        c_ = x["r60"] * x["cost_amt"]
        cum += c_
        a("    %s %-9s r60=%+7.1f%% 成本%.0f万 贡献%+.0f万 (累计占总增厚 %.0f%%)"
          % (x["code"], x["name"], x["r60"] * 100, x["cost_amt"] / 1e4,
             c_ / 1e4, cum * 100.0 / tot_d if tot_d else 0))

    # 逐 combo 分解
    a("\n【5】按来源 combo 分解 (+60日反事实中位)")
    for i in range(1, len(v19_files) + 1):
        s = [x for x in rows if x["src"] == "c%d" % i and x["r60"] is not None]
        if s:
            a("  c%-2d n=%-4d 中位%+.2f%%  >0占%.0f%%"
              % (i, len(s), statistics.median([x["r60"] for x in s]),
                 len([x for x in s if x["r60"] > 0]) * 100.0 / len(s)))

    # 反例/正例各列几笔
    a("\n【6】典型样本: 止损后+60日涨幅最大的 8 笔 / 跌幅最大的 8 笔")
    with60 = [x for x in rows if x["r60"] is not None]
    with60.sort(key=lambda x: -x["r60"])
    for lab, seq in (("止损卖飞", with60[:8]), ("止损躲过", with60[-8:][::-1])):
        a("  -- %s --" % lab)
        for x in seq:
            a("    %s %-9s 止损时%+6.1f%% -> +60日 %+7.1f%%  (%s, %s买%s卖)"
              % (x["code"], x["name"], x["pnl"], x["r60"] * 100, x["src"],
                 x["buy"], x["sell"]))

    out = os.path.join(d, "_stop_counterfactual.txt")
    with io.open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(W))
    print("ok: %s (%d chars)" % (out, len("\n".join(W))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
