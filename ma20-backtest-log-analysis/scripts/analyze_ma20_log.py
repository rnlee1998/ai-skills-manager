# -*- coding: utf-8 -*-
"""
MA20 策略回测日志分析器（csi1000_backtest_log_*.txt）

用法:
    python analyze_ma20_log.py "<日志目录>" "<combo1文件,combo2文件,...>" [标签映射]

参数:
    日志目录     : 存放 csi1000_backtest_log_*.txt 的目录
    文件列表     : 逗号分隔的文件名（相对目录）
    标签映射(可选): 逗号分隔的 "combo1:因子名" 形式，用于表头显示

输出:
    <日志目录>/_ma20_analysis.txt   人读报告
    <日志目录>/_ma20_analysis.json  结构化结果

示例:
    python analyze_ma20_log.py "D:\\WorkSpace\\Myrepo\\quant\\MA20 stratedgy" \
        "csi1000_backtest_log_20260923_163146.txt,csi1000_backtest_log_20260923_165509.txt" \
        "combo1:-1*ATR分位,combo2:+1*市值分位"

注意: 本机 Bash 工具不可用，用 PowerShell 调用 managed python，
      并把 stdout 重定向到文件后再读（PowerShell stdout 常不回显）。
"""
import io
import json
import os
import re
import statistics
import sys
from collections import OrderedDict, defaultdict

# ---------------------------------------------------------------- 正则
# ⚠️ 坑1: 名称可能含空格（特 力Ａ / 诺 普 信 / 粤 传 媒）
#         必须用非贪婪 (.+?) + 以 "N份" 为锚点，否则静默漏掉约 6 笔
# ⚠️ 坑2: [买入] 有两种行，预算行不是成交，靠 "成交价" 锚点区分
# ⚠️ 坑3: 卖出原因在第 8 捕获组，不是第 7（第7是佣金）
RE_BUY = re.compile(
    r"^\[(\d{8})\] \[买入\] (\d{6}\.[A-Z]{2})\s+(.+?)\s+"
    r"(\d+)份 成交价([\d.]+) 金额([\d.]+)元 佣金([\d.]+)元")
RE_SELL = re.compile(
    r"^\[(\d{8})\] \[卖出\] (\d{6}\.[A-Z]{2})\s+(.+?)\s+"
    r"(\d+)份 成交价([\d.]+) 金额([\d.]+)元 佣金([\d.]+)元 \((.*)\)\s*$")
RE_MKT = re.compile(r"^\[(\d{8})\] \[大盘\] 中证1000 (.+?) ADX14=([\d.]+)\s*$")
RE_POOL = re.compile(r"^\[(\d{8})\] \[分池更新\] A类(\d+)只 B类(\d+)只")
RE_EQ = re.compile(
    r"^\s+持仓市值: ([\d.]+), 累计已实现: ([+-][\d.]+), "
    r"总资产: ([\d.]+), 累计收益: ([+-][\d.]+) \(([+-][\d.]+)%\)\s*$")
RE_POS = re.compile(r"^\s+交易日: (\d{8}) \| 持仓(\d+)只\s*$")
RE_PF = re.compile(r"浮盈(-?[\d.]+)%")
RE_DD = re.compile(r"回撤(-?[\d.]+)%>(\d+)%")
RE_CAND = re.compile(r"(\d{6}\.[A-Z]{2})\(市值([\d.]+)亿 得分(-?[\d.]+)\)")

INIT = 10000000.0          # 初始资金
COMMISSION = 0.0003        # 佣金费率
SLIPPAGE_PER_SIDE = 0.001  # 单边滑点


# ---------------------------------------------------------------- 工具
def m0(x):
    """带正负号 + 千分位。% 格式化不支持逗号，必须用 format()"""
    return format(x, "+,.0f")


def c0(x):
    return format(x, ",.0f")


def d2f(d):
    from datetime import date
    return date(int(d[:4]), int(d[4:6]), int(d[6:8]))


def kind_of(reason):
    if "顶背离" in reason:
        return "顶背离清仓"
    m = RE_DD.search(reason)
    if m:
        return "回撤%s%%档%s" % (m.group(2), "+破MA5" if "<MA5" in reason else "")
    return "其他"


# ---------------------------------------------------------------- 解析
def parse(path):
    r = dict(combo=None, buys=[], sells=[], eq=[], pos=[], pool=[], mkt=[],
             cand=defaultdict(int), budget=0, full=0, skip=0, snap=0)
    with io.open(path, encoding="utf-8", errors="replace") as f:
        for L in f:
            L = L.rstrip("\r\n")

            if L.startswith("因子组合combo") or L.startswith("因子:"):
                r["combo"] = L.strip()
                continue

            m = RE_BUY.match(L)
            if m:
                r["buys"].append(dict(
                    d=m.group(1), code=m.group(2), name=m.group(3),
                    qty=int(m.group(4)), px=float(m.group(5)),
                    amt=float(m.group(6)), fee=float(m.group(7))))
                continue

            m = RE_SELL.match(L)
            if m:
                pf = RE_PF.search(m.group(8))
                r["sells"].append(dict(
                    d=m.group(1), code=m.group(2), name=m.group(3),
                    qty=int(m.group(4)), px=float(m.group(5)),
                    amt=float(m.group(6)), fee=float(m.group(7)),
                    reason=m.group(8), kind=kind_of(m.group(8)),
                    pnl_pct=float(pf.group(1)) if pf else None))
                continue

            m = RE_MKT.match(L)
            if m:
                r["mkt"].append((m.group(1),
                                 "ON" if "开关ON" in m.group(2) else "OFF",
                                 float(m.group(3))))
                continue

            m = RE_POOL.match(L)
            if m:
                r["pool"].append((m.group(1), int(m.group(2))))
                continue

            m = RE_EQ.match(L)
            if m:
                r["eq"].append(dict(
                    d=r["pos"][-1][0] if r["pos"] else None,
                    mv=float(m.group(1)), realized=float(m.group(2)),
                    total=float(m.group(3)), pnl=float(m.group(4)),
                    pct=float(m.group(5))))
                continue

            m = RE_POS.match(L)
            if m:
                r["pos"].append((m.group(1), int(m.group(2))))
                continue

            # 坑2: 预算行 / 状态行单独计数，绝不进 buys
            if "[买入] 可用资金" in L:
                r["budget"] += 1
                continue
            if "[仓位已满]" in L:
                r["full"] += 1
                continue
            if "未入选" in L:
                r["skip"] += 1
                continue
            if "[买入候选]" in L:
                for c, mv, sc in RE_CAND.findall(L):
                    r["cand"][c] += 1
                continue
            if "[成分快照]" in L:
                r["snap"] += 1
                continue
    return r


def pair_fifo(buys, sells):
    """同代码 FIFO 配对: 买入入队，卖出 pop(0)"""
    openq = defaultdict(list)
    for b in buys:
        openq[b["code"]].append(b)
    holds = []
    for s in sells:
        if openq[s["code"]]:
            b = openq[s["code"]].pop(0)
            holds.append(dict(
                code=s["code"], name=s["name"], buy=b["d"], sell=s["d"],
                days=(d2f(s["d"]) - d2f(b["d"])).days,
                pnl_pct=s["pnl_pct"], kind=s["kind"],
                reason=s["reason"], buy_px=b["px"], sell_px=s["px"],
                pnl_amt=(s["amt"] - b["amt"]) - s["fee"] - b["fee"]))
    n_open = sum(len(v) for v in openq.values())
    return holds, n_open


# ---------------------------------------------------------------- 分析主流程
def analyse(entries):
    """entries: list of (key, label, filename)"""
    res = OrderedDict()
    for key, label, fn in entries:
        r = parse(fn)

        buy_amt = sum(b["amt"] for b in r["buys"])
        sell_amt = sum(s["amt"] for s in r["sells"])
        fee = sum(b["fee"] for b in r["buys"]) + sum(s["fee"] for s in r["sells"])

        # 自检1: 佣金 == 买入额 × 0.03%
        chk = abs(buy_amt * COMMISSION - sum(b["fee"] for b in r["buys"])) \
            < max(50, buy_amt * COMMISSION * 0.02)

        holds, n_open = pair_fifo(r["buys"], r["sells"])
        realised = sum(h["pnl_amt"] for h in holds)
        log_realised = r["eq"][-1]["realized"] if r["eq"] else 0.0
        # 自检2: 配对盈亏 ≈ 日志自报「累计已实现」
        chk2 = abs(realised - log_realised)

        good = [h for h in holds if h["pnl_pct"] is not None]
        good.sort(key=lambda x: -x["pnl_amt"])

        # 净值口径（稀疏快照: 只在有成交的日子打印）
        tot = [x["total"] for x in r["eq"]]
        peak, mdd = (tot[0] if tot else INIT), 0.0
        for v in tot:
            peak = max(peak, v)
            mdd = min(mdd, (v / peak - 1) * 100)

        pf = [h["pnl_pct"] for h in good]
        wins = [x for x in pf if x > 0]
        losses = [x for x in pf if x <= 0]

        kinds = defaultdict(list)
        for h in good:
            kinds[h["kind"]].append(h)

        # 分年度收益
        yr = OrderedDict()
        prev = INIT
        for y in ("2020", "2021", "2022", "2023"):
            seg = [x for x in r["eq"] if x["d"] and x["d"][:4] == y]
            if seg:
                yr[y] = (seg[-1]["total"] / prev - 1) * 100
                prev = seg[-1]["total"]

        # 择时开关 / 持仓
        on_by_y = defaultdict(lambda: [0, 0])
        for d, st, _adx in r["mkt"]:
            on_by_y[d[:4]][1] += 1
            if st == "ON":
                on_by_y[d[:4]][0] += 1
        posy = defaultdict(list)
        for d, c in r["pos"]:
            posy[d[:4]].append(c)

        # 年度成交额 / 佣金
        cash = defaultdict(lambda: [0.0, 0.0])
        for b in r["buys"]:
            cash[b["d"][:4]][0] += b["amt"]
            cash[b["d"][:4]][1] += b["fee"]
        for s in r["sells"]:
            cash[s["d"][:4]][0] += s["amt"]
            cash[s["d"][:4]][1] += s["fee"]

        # 持仓天数分布
        buck = OrderedDict((("<=10天", 0), ("11~30天", 0), ("31~60天", 0),
                            ("61~120天", 0), (">120天", 0)))
        for h in good:
            x = h["days"]
            if x <= 10:
                buck["<=10天"] += 1
            elif x <= 30:
                buck["11~30天"] += 1
            elif x <= 60:
                buck["31~60天"] += 1
            elif x <= 120:
                buck["61~120天"] += 1
            else:
                buck[">120天"] += 1

        # 重复交易
        rep = defaultdict(int)
        for b in r["buys"]:
            rep[b["code"]] += 1
        multi = {k: v for k, v in rep.items() if v >= 2}

        # 换仓日
        bd, sd = defaultdict(int), defaultdict(int)
        for b in r["buys"]:
            bd[b["d"]] += 1
        for s in r["sells"]:
            sd[s["d"]] += 1
        both = sorted(set(bd) & set(sd))

        # 8% 档的真实代价
        k8 = [h for h in good if h["kind"].startswith("回撤8")]
        gave_back = [h for h in k8 if h["pnl_pct"] > 0]
        deep_loss = [h for h in k8 if h["pnl_pct"] < -8]

        res[key] = dict(
            label=label, combo_def=r["combo"],
            fee_ok=chk, pair_bias=chk2,
            n_buy=len(r["buys"]), n_sell=len(r["sells"]),
            n_budget=r["budget"], n_full=r["full"], n_skip=r["skip"],
            n_snap=r["snap"],
            buy_amt=buy_amt, sell_amt=sell_amt, fee=fee,
            turnover=(buy_amt + sell_amt) / INIT * 100,
            slip=(buy_amt + sell_amt) * SLIPPAGE_PER_SIDE,
            last_snap=(tot[-1] if tot else INIT),
            last_snap_ret=(tot[-1] / INIT - 1) * 100 if tot else 0.0,
            mdd_sparse=mdd, peak=max(tot) if tot else INIT,
            low=min(tot) if tot else INIT,
            n_hold=len(good), n_open=n_open,
            win=len(wins) * 100.0 / len(pf) if pf else 0.0,
            avg=sum(pf) / len(pf) if pf else 0.0,
            avgwin=sum(wins) / len(wins) if wins else 0.0,
            avgloss=sum(losses) / len(losses) if losses else 0.0,
            best=max(pf) if pf else 0.0, worst=min(pf) if pf else 0.0,
            avgdays=sum(h["days"] for h in good) / len(good) if good else 0.0,
            realised=realised, log_realised=log_realised,
            kinds={k: dict(n=len(v), pnl=sum(x["pnl_amt"] for x in v),
                           avg=sum(x["pnl_pct"] for x in v) / len(v),
                           win=len([x for x in v if x["pnl_pct"] > 0]) * 100.0 / len(v))
                   for k, v in sorted(kinds.items(), key=lambda kv: -len(kv[1]))},
            yr={k: round(v, 2) for k, v in yr.items()},
            on={y: on_by_y[y] for y in sorted(on_by_y)},
            pos_yr={y: (sum(posy[y]) / len(posy[y]) if posy[y] else 0.0)
                    for y in sorted(posy)},
            cash_yr={y: [cash[y][0], cash[y][1]] for y in sorted(cash)},
            buck=buck, n_codes=len(rep),
            n_multi=len(multi), n_multi_trades=sum(multi.values()),
            multi_top=sorted(multi.items(), key=lambda x: -x[1])[:8],
            n_chg=len(both),
            k8=dict(n=len(k8), pnl=sum(x["pnl_amt"] for x in k8),
                    gave_back=len(gave_back),
                    gave_back_avg=(sum(x["pnl_pct"] for x in gave_back) / len(gave_back)
                                   if gave_back else 0.0),
                    deep_loss=len(deep_loss)),
            top_win=[(h["code"], h["name"], h["pnl_pct"], h["days"], h["kind"],
                      h["pnl_amt"]) for h in good[:10]],
            top_los=[(h["code"], h["name"], h["pnl_pct"], h["days"],
                      h["kind"], h["pnl_amt"]) for h in good[-10:][::-1]],
            cum=dict((n, sum(h["pnl_amt"] for h in good[n:]))
                     for n in (0, 1, 3, 5, 10, 20, 30)),
            pool_min=min((x[1] for x in r["pool"]), default=0),
            pool_max=max((x[1] for x in r["pool"]), default=0),
            pool_last=r["pool"][-1][1] if r["pool"] else 0,
            pos_hist=dict(n=len(r["pos"]),
                          avg=(sum(c for _, c in r["pos"]) / len(r["pos"])
                               if r["pos"] else 0.0),
                          zero=len([c for _, c in r["pos"] if c == 0]),
                          le2=len([c for _, c in r["pos"] if c <= 2]),
                          ge8=len([c for _, c in r["pos"] if c >= 8])),
            adx_on=[a for _d, s, a in r["mkt"] if s == "ON"],
            adx_off=[a for _d, s, a in r["mkt"] if s == "OFF"],
        )
    return res


# ---------------------------------------------------------------- 报告
def render(res):
    W = []
    a = W.append
    keys = list(res.keys())
    d0, d1 = "", ""
    a("=" * 100)
    a("MA20 策略 · 回测日志分析  (初始资金 %s 元 / 每份日志 = 一个因子组合)" % c0(INIT))
    a("=" * 100)

    # 0 一致性校验
    a("\n【0】解析一致性自检 —— 不通过则后续所有结论不可信")
    a("  %-8s %-16s %5s %5s %6s %8s %14s %14s %10s" % (
        "combo", "因子", "买入", "卖出", "预算行", "候选未选", "配对已实现", "日志已实现", "偏差(元)"))
    for k in keys:
        v = res[k]
        a("  %-8s %-16s %5d %5d %6d %8d %14s %14s %10.0f%s" % (
            k, v["label"], v["n_buy"], v["n_sell"], v["n_budget"], v["n_skip"],
            c0(v["realised"]), c0(v["log_realised"]), v["pair_bias"],
            "" if v["pair_bias"] < 1000 else "  <<< 异常"))
    a("  佣金规则校验: " + "  ".join(
        "%s=%s" % (k, "PASS" if res[k]["fee_ok"] else "FAIL") for k in keys))

    # 1 总体
    a("\n【1】总体结果与交易强度")
    a("%-8s %-16s %5s %5s %12s %12s %10s %10s %10s %9s" % (
        "combo", "因子", "买入", "卖出", "买入额(万)", "卖出额(万)",
        "换手率%", "佣金(元)", "滑点(元)", "摩擦%" ))
    for k in keys:
        v = res[k]
        a("%-8s %-16s %5d %5d %12.0f %12.0f %9.0f%% %10.0f %10.0f %8.1f%%" % (
            k, v["label"], v["n_buy"], v["n_sell"], v["buy_amt"] / 1e4,
            v["sell_amt"] / 1e4, v["turnover"], v["fee"], v["slip"],
            (v["fee"] + v["slip"]) / INIT * 100))

    # 2 净值
    a("\n【2】末快照净值 / 回撤（稀疏快照口径，实际期末值比这里高约 4~5%）")
    a("%-8s %14s %14s %14s %14s" % ("combo", "末快照净值", "末快照收益", "峰值", "最大回撤"))
    for k in keys:
        v = res[k]
        a("%-8s %14.4f %13.2f%% %14.0f %13.2f%%" % (
            k, v["last_snap"] / INIT, v["last_snap_ret"], v["peak"], v["mdd_sparse"]))

    # 3 卖出规则归因 ★
    a("\n【3】★ 卖出规则盈亏归因 —— 全篇最有价值的一张表")
    a("%-8s %-20s %5s %16s %11s %9s" % (
        "combo", "退出规则", "笔数", "该规则盈亏(元)", "平均浮盈%", "胜率%"))
    for k in keys:
        a("  " + k)
        for kk, vv in res[k]["kinds"].items():
            a("        %-20s %5d %16s %10.1f%% %8.1f%%" % (
                kk, vv["n"], m0(vv["pnl"]), vv["avg"], vv["win"]))

    # 4 集中度 ★
    a("\n【4】★ 收益集中度 —— 剔除盈利最大的 N 笔后的累计盈亏")
    a("%-8s %16s %16s %16s %16s %16s" % (
        "combo", "全部", "剔除Top1", "剔除Top3", "剔除Top5", "剔除Top10"))
    for k in keys:
        c = res[k]["cum"]
        a("%-8s %16s %16s %16s %16s %16s" % (
            k, m0(c[0]), m0(c[1]), m0(c[3]), m0(c[5]), m0(c[10])))
    a("  注: 若「剔除Top3」就转负 → 收益高度依赖少数大赢家，结论必须点名其脆弱性。")

    # 5 平仓统计
    a("\n【5】平仓统计")
    a("%-8s %5s %5s %8s %9s %9s %9s %9s %9s %8s" % (
        "combo", "平仓", "未平", "胜率%", "均值%", "均盈%", "均亏%",
        "最好%", "最差%", "平均天"))
    for k in keys:
        v = res[k]
        a("%-8s %5d %5d %7.1f%% %8.2f%% %8.2f%% %8.2f%% %8.1f%% %8.1f%% %8.1f" % (
            k, v["n_hold"], v["n_open"], v["win"], v["avg"], v["avgwin"],
            v["avgloss"], v["best"], v["worst"], v["avgdays"]))

    # 6 单笔排行
    a("\n【6】单笔盈利 Top10 / 亏损 Top10（含退出原因）")
    for k in keys:
        a("  ---- %s (%s) ----" % (k, res[k]["label"]))
        a("    %-11s %-9s %6s %8s %12s  %s" % ("代码", "名称", "天数", "浮盈", "盈亏(元)", "退出原因"))
        for c_, n_, p_, dd_, kd_, pa_ in res[k]["top_win"]:
            a("    %-11s %-9s %6d %7.1f%% %12.0f  %s" % (c_, n_.replace(" ", ""), dd_, p_, pa_, kd_))
        a("    亏损榜:")
        for c_, n_, p_, dd_, kd_, pa_ in res[k]["top_los"]:
            a("    %-11s %-9s %6d %7.1f%% %12.0f  %s" % (c_, n_.replace(" ", ""), dd_, p_, pa_, kd_))

    # 7 8% 止损的真实代价 ★
    a("\n【7】★ 「回撤8%档+破MA5」的真实代价")
    a("%-8s %6s %8s %8s %16s %16s" % (
        "combo", "触发", "占比%", "仍浮盈", "仍浮盈均%", "该档总盈亏(元)"))
    for k in keys:
        v = res[k]
        k8 = v["k8"]
        a("%-8s %6d %7.1f%% %8d %15.1f%% %16s" % (
            k, k8["n"], k8["n"] * 100.0 / max(1, v["n_hold"]), k8["gave_back"],
            k8["gave_back_avg"], m0(k8["pnl"])))

    # 8 分年度
    a("\n【8】分年度收益（%）")
    a("%-8s %12s %12s %12s %12s" % ("combo", "2020", "2021", "2022", "2023"))
    for k in keys:
        y = res[k]["yr"]
        a("%-8s %11.1f%% %11.1f%% %11.1f%% %11.1f%%" % (
            k, y.get("2020", 0), y.get("2021", 0), y.get("2022", 0), y.get("2023", 0)))

    # 9 择时开关 & 仓位
    a("\n【9】择时开关效率 / 仓位利用（各组合开关信号完全相同，取第一组展示）")
    v0 = res[keys[0]]
    a("  开关ON占比: " + "  ".join(
        "%s %.0f%%(%d/%d)" % (y, v[0] * 100.0 / v[1], v[0], v[1])
        for y, v in v0["on"].items()))
    a("  平均持仓:   " + "  ".join("%s %.1f只" % (y, c) for y, c in v0["pos_yr"].items()))
    ph = v0["pos_hist"]
    a("  持仓快照 n=%d，平均 %.1f 只，空仓 %d 次，<=2只 %d 次，>=8只 %d 次"
      % (ph["n"], ph["avg"], ph["zero"], ph["le2"], ph["ge8"]))
    if v0["adx_on"] and v0["adx_off"]:
        a("  ADX14（仅展示、未参与开关条件）: ON时中位%.1f 均值%.1f | OFF时中位%.1f 均值%.1f"
          % (statistics.median(v0["adx_on"]), sum(v0["adx_on"]) / len(v0["adx_on"]),
             statistics.median(v0["adx_off"]), sum(v0["adx_off"]) / len(v0["adx_off"])))
        a("  ↑ 两组几乎不可分 → ADX14 是无效展示字段，建议删除或真正接入条件。")
    a("  A池规模区间 %d~%d 只，最新 %d 只" % (v0["pool_min"], v0["pool_max"], v0["pool_last"]))
    a("  成分快照行 %d 条（对应 PTrade 半年期实测名单）" % v0["n_snap"])

    # 10 持仓周期 / 重复交易
    a("\n【10】持仓周期分布 / 交易集中度")
    for k in keys:
        v = res[k]
        a("  %s 天数分布: %s" % (k, "  ".join("%s:%d" % (kk, vv) for kk, vv in v["buck"].items())))
        a("      标的重复: 买入 %d 笔覆盖 %d 个标的，重复买入>=2次 %d 个（共 %d 笔）| 换仓日 %d 天"
          % (v["n_buy"], v["n_codes"], v["n_multi"], v["n_multi_trades"], v["n_chg"]))
        if v["multi_top"]:
            a("      重复最多: " + ", ".join("%s×%d" % (kk, vv) for kk, vv in v["multi_top"]))

    # 11 成本分年
    a("\n【11】分年度成交额 / 佣金")
    for k in keys:
        v = res[k]
        a("  %s 成交额(万): %s" % (k, "  ".join(
            "%s %.0f" % (y, c[0] / 1e4) for y, c in v["cash_yr"].items())))
        a("      佣金(元): %s" % ("  ".join(
            "%s %.0f" % (y, c[1]) for y, c in v["cash_yr"].items())))

    # 12 跨组合赢家
    a("\n【12】跨组合重复出现的赢家标的（判断「因子是否真的选出了东西」）")
    hit = defaultdict(list)
    for k in keys:
        for c_, n_, p_, dd_, kd_, pa_ in res[k]["top_win"]:
            hit[c_].append((k, n_.replace(" ", ""), p_))
    for c_ in sorted(hit, key=lambda x: -len(hit[x])):
        if len(hit[c_]) >= 2:
            a("  %s %-8s 出现在 %s" % (
                c_, hit[c_][0][1], ", ".join("%s(%+.0f%%)" % (h[0], h[2]) for h in hit[c_])))
    a("  ↑ 跨组合重复出现的票 → 收益来自共用环节（分池+择时），而不是被测试的那个因子。")

    a("\n" + "=" * 100)
    return "\n".join(W)


# ---------------------------------------------------------------- main
def main():
    if len(sys.argv) < 3:
        sys.stderr.write(__doc__)
        return 1
    d = sys.argv[1]
    files = [x.strip() for x in sys.argv[2].split(",") if x.strip()]
    lab = {}
    if len(sys.argv) >= 4:
        for item in sys.argv[3].split(","):
            if ":" in item:
                k, v = item.split(":", 1)
                lab[k.strip()] = v.strip()

    entries = []
    for i, fn in enumerate(files, 1):
        key = "combo%d" % i
        entries.append((key, lab.get(key, ""), os.path.join(d, fn)))

    res = analyse(entries)
    txt = render(res)

    p_txt = os.path.join(d, "_ma20_analysis.txt")
    p_json = os.path.join(d, "_ma20_analysis.json")
    with io.open(p_txt, "w", encoding="utf-8") as f:
        f.write(txt)
    # adx 明细不进 json（太长），其余全保留
    slim = OrderedDict()
    for k, v in res.items():
        v = dict(v)
        v.pop("adx_on", None)
        v.pop("adx_off", None)
        slim[k] = v
    with io.open(p_json, "w", encoding="utf-8") as f:
        f.write(json.dumps(slim, ensure_ascii=False, indent=1, default=str))
    print("ok: %s (%d chars)" % (p_txt, len(txt)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
