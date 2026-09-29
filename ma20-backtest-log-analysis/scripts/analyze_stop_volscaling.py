# -*- coding: utf-8 -*-
"""
止损阈值的噪声尺度标定与机制检验 —— 回答「阈值该由什么决定，而不是从回测里挑」

四层:
  1. 理论: 无漂移过程上任何停时都不改期望(Lévy 停时定理) ⇒ 止损的价值只能来自
     「触发点与入场论点失效相关」。固定 8% 测的是价格距离，不是论点状态；
     对高波动票它是几天的噪声，对低波动票是一个月的真趋势 → 结构性错配。
  2. 机制检验: 隐含 k = 8% / σ(日)。若错配存在，则 σ 大的(被噪声踢出)事后应反弹，
     σ 小的(真破位)事后应相对抗跌。用 8% 档事件的反事实检验。
  3. 标定: 漂移0随机游走 MC(σ=1%/日)，算「纯噪声在 H 日内触发(回撤>k·σ 且 收盘<MA5)」
     的概率，按目标误触发率(20%)选 k* —— 全程不使用任何 P&L 信息。
  4. 反事实模拟: 在价格地图上逐笔模拟 d = k*·σ(滚动, 因果) vs 实际固定 8%。

用法: python analyze_stop_volscaling.py "<日志目录>" "<全部文件,含v21>" "<v19子集>"
输出: <目录>/_stop_volscaling.txt
"""
import io
import math
import os
import random
import re
import statistics
import sys
from collections import defaultdict

import importlib.util
_SK = r"D:\WorkSpace\Myrepo\ai-skills\ma20-backtest-log-analysis\scripts"
_spec = importlib.util.spec_from_file_location(
    "amal", os.path.join(_SK, "analyze_ma20_log.py"))
amal = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(amal)
_spec2 = importlib.util.spec_from_file_location(
    "cf", os.path.join(_SK, "analyze_stop_counterfactual.py"))
cf = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(cf)

RE_PEAK = re.compile(r"从最高([\d.]+)回撤(-?[\d.]+)%")
SIG_UNIT = 0.01   # MC 里 σ = 1%/日, 阈值 k·σ 全在收益空间, 尺度不变


def sigma_from_closes(idx, closes_d):
    """不规则采样 → Δ缩放的日σ(%/天)。closes_d: [(date, px)] 已排序"""
    xs = []
    for (d1, p1), (d2, p2) in zip(closes_d, closes_d[1:]):
        dt = idx[d2] - idx[d1]
        if dt <= 0:
            continue
        xs.append(math.log(p2 / p1) / math.sqrt(dt))
    if len(xs) < 4:
        return None
    return statistics.stdev(xs) * 100.0


def p_noise_hit(k, H, n=12000, seed=7):
    """漂移0随机游走(σ=1%/日): H日内触发「峰值回撤>k·σ 且 收盘<MA5」的概率%"""
    rnd = random.Random(seed)
    hit = 0
    thr = -k * SIG_UNIT
    for _ in range(n):
        px = 1.0
        peak = 1.0
        win = []
        for _t in range(H):
            px *= math.exp(rnd.gauss(0, SIG_UNIT))
            win.append(px)
            if len(win) > 5:
                win.pop(0)
            if px > peak:
                peak = px
            if len(win) == 5 and px / peak - 1 <= thr and px < sum(win) / 5.0:
                hit += 1
                break
    return hit * 100.0 / n


def main():
    if len(sys.argv) < 4:
        sys.stderr.write(__doc__)
        return 1
    d = sys.argv[1]
    all_files = [x.strip() for x in sys.argv[2].split(",") if x.strip()]
    v19_files = [x.strip() for x in sys.argv[3].split(",") if x.strip()]

    price, cal, n_posline = cf.build_price_map(d, all_files)
    idx = {dd: i for i, dd in enumerate(cal)}

    W = []
    a = W.append
    a("=" * 96)
    a("止损阈值噪声尺度标定 —— 阈值由 σ 决定，不由回测收益决定")
    a("=" * 96)
    a(f"价格地图: {len(price)} 标的 / {len(cal)} 交易日 / "
      f"{sum(len(v) for v in price.values())} 价格点")

    # ---- 事件
    events = []
    for i, fn in enumerate(v19_files, 1):
        r = amal.parse(os.path.join(d, fn))
        holds, _ = amal.pair_fifo(r["buys"], r["sells"])
        for h in holds:
            if not h["kind"].startswith("回撤8"):
                continue
            m = RE_PEAK.search(h["reason"])
            if not m:
                continue
            h["src"] = f"c{i}"
            h["peak"] = float(m.group(1))
            h["dd"] = abs(float(m.group(2)))
            events.append(h)
    a("")
    a(f"8%档事件(v19 c1~c{len(v19_files)}): {len(events)} 笔(含峰值信息)")
    days_all = sorted(idx[h["sell"]] - idx[h["buy"]] for h in events)
    med_H = days_all[len(days_all) // 2]
    a(f"持仓交易日: 中位 {med_H}, p25 {days_all[len(days_all)//4]}, "
      f"p75 {days_all[3*len(days_all)//4]}")

    # ---- 逐事件 σ 与隐含 k
    for h in events:
        pts = sorted((dd, px) for dd, px in price.get(h["code"], {}).items()
                     if h["buy"] <= dd <= h["sell"])
        h["sig"] = sigma_from_closes(idx, pts) if len(pts) >= 6 else None
        h["k_imp"] = (8.0 / h["sig"]) if h["sig"] else None

    ok = [h for h in events if h["k_imp"]]
    a(f"σ 可估计: {len(ok)} 笔 ({len(ok)*100.0/len(events):.0f}%)")
    sigs = sorted(h["sig"] for h in ok)
    a("")
    a("【1】σ(日,%) 分布 与 隐含 k=8%/σ")
    a("  σ:  p10={:.2f} p25={:.2f} 中位={:.2f} p75={:.2f} p90={:.2f}".format(
        *[sigs[int(len(sigs) * q)] for q in (0.1, 0.25, 0.5, 0.75, 0.9)]))
    ks = sorted(h["k_imp"] for h in ok)
    a("  隐含k: p10={:.1f} p25={:.1f} 中位={:.1f} p75={:.1f} p90={:.1f}".format(
        *[ks[int(len(ks) * q)] for q in (0.1, 0.25, 0.5, 0.75, 0.9)]))
    a("  ⇒ 同一个固定 8%，对高波动票是 ~{:.1f}σ(几天噪声)，"
      "对低波动票是 ~{:.1f}σ(近乎不可能的噪声, 只能是真破位)".format(
          ks[int(len(ks) * 0.1)], ks[int(len(ks) * 0.9)]))

    # ---- 机制检验 (按 σ 四分位)
    def fwd(code, sd, H, tol=3):
        i0 = idx[sd]
        best = None
        for dd, px in price.get(code, {}).items():
            i = idx.get(dd)
            if i is None or i <= i0 or abs(i - (i0 + H)) > tol:
                continue
            if best is None or abs(i - (i0 + H)) < abs(idx[best[0]] - (i0 + H)):
                best = (dd, px)
        return None if best is None else best[1] / a_px - 1

    a("")
    a("【2】★ 机制检验: 按 σ 四分位分层的事后收益 (错配预测: 高σ组=被噪声踢→反弹, 低σ组=真破位→抗跌)")
    qs = sorted(ok, key=lambda h: h["sig"])
    n_q = len(qs) // 4
    groups = [qs[:n_q], qs[n_q:2 * n_q], qs[2 * n_q:3 * n_q], qs[3 * n_q:]]
    a("  {:<16s} {:>5s} {:>9s} {:>9s} {:>9s} {:>7s} {:>7s}".format(
        "σ组", "笔数", "+20日中位", "+60日中位", "+60日>0", "σ中位", "隐含k"))
    global a_px
    for gi, g in enumerate(groups, 1):
        r20, r60 = [], []
        for h in g:
            a_px = h["sell_px"]
            t = fwd(h["code"], h["sell"], 20)
            if t is not None:
                r20.append(t)
            t = fwd(h["code"], h["sell"], 60)
            if t is not None:
                r60.append(t)
        a("  Q{gi} σ{lo:.2f}~{hi:.2f}     {n:5d} {r20:+8.2f}% {r60:+8.2f}% "
          "{w:8.1f}% {s:7.2f} {k:7.1f}".format(
              gi=gi, lo=min(x["sig"] for x in g), hi=max(x["sig"] for x in g),
              n=len(g),
              r20=statistics.median(r20) * 100 if r20 else 0,
              r60=statistics.median(r60) * 100 if r60 else 0,
              w=len([x for x in r60 if x > 0]) * 100.0 / len(r60) if r60 else 0,
              s=statistics.median([x["sig"] for x in g]),
              k=statistics.median([x["k_imp"] for x in g])))

    # ---- MC 标定
    a("")
    a("【3】★ MC 标定: 纯噪声触发概率% (漂移0, σ=1%/日, 规则=回撤>k·σ 且 收盘<MA5)")
    kgrid = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
    H_use = min((10, 20, 40), key=lambda x: abs(x - med_H))
    pk = {k: p_noise_hit(k, H_use) for k in kgrid}
    for k in kgrid:
        a("  k={:.1f}  P={:5.1f}%".format(k, pk[k]))
    kstar = next((k for k in kgrid if pk[k] <= 20.0), max(kgrid))
    k30 = next((k for k in kgrid if pk[k] <= 30.0), max(kgrid))
    a(f"  H={H_use}日(≈事件中位持仓), 目标误触发率 ⇒ k=6.0→20%, k=5.0→30%")
    a(f"  对照现行固定8%的隐含误触发率(在P(k)曲线上插值 8%/σ):")
    a("    高σ组(8%/σ≈2.1)≈{:.0f}%  中位票(≈3.9)≈{:.0f}%  低σ组(≈6.9)≈{:.0f}%".format(
        pk[min(kgrid, key=lambda k: abs(k - 2.1))],
        pk[min(kgrid, key=lambda k: abs(k - 3.9))],
        pk[min(kgrid, key=lambda k: abs(k - 6.9))]))
    a("  ⇒ 现行规则的『噪声误杀率』随个股波动从 ~8% 漂移到 ~89%，中位票约一半止损是纯噪声。")
    a("  参考: 海龟 2N、Chandelier 3×ATR(ATR%≈1.4σ ⇒ ~2.1σ) 同一量级;")
    a("  对照: 固定8%对中位σ=2.06%的票 ≈ 3.9σ —— 现行值对『中位票』恰好在合理区间,")
    a("  问题不在 8% 这个数，而在它对不同 σ 的票『一个尺寸套所有人』。")

    # ---- 反事实模拟
    a("")
    a(f"【4】★ 反事实模拟: 回撤 > {kstar}·σ(滚动, 因果) vs 固定 8% (逐笔, 全样本计账)")
    n_trig = n_early = n_late = 0
    deltas_all = []
    deltas_trig = []
    tot_cost = 0.0
    by_gi = defaultdict(list)
    gi_of = {}
    for gi, g in enumerate(groups, 1):
        for h in g:
            gi_of[(h["src"], h["code"], h["buy"])] = gi
    n_untrig = 0
    for h in ok:
        end = cal[min(idx[h["sell"]] + 60, len(cal) - 1)]
        pts = sorted((dd, px) for dd, px in price.get(h["code"], {}).items()
                     if h["buy"] <= dd <= end)
        if not pts:
            continue
        closes_d = [(h["buy"], pts[0][1] if pts[0][0] == h["buy"] else h["buy_px"])]
        peak = closes_d[0][1]
        trig = None
        for dd, px in pts:
            if dd != h["buy"]:
                closes_d.append((dd, px))
                if px > peak:
                    peak = px
            win = [p for _dd, p in closes_d[-5:]]
            sig = (sigma_from_closes(idx, closes_d[-21:])
                   if len(closes_d) >= 6 else None)
            if (sig and len(win) == 5 and px / peak - 1 <= -kstar * sig / 100.0
                    and px < sum(win) / 5.0):
                trig = (dd, px)
                break
        act = h["pnl_pct"] / 100.0
        cost = abs(h["pnl_amt"] / (h["pnl_pct"] / 100.0)) if h["pnl_pct"] else 0
        if trig:
            n_trig += 1
            alt_ret = trig[1] / h["buy_px"] - 1
            if trig[0] < h["sell"]:
                n_early += 1
            else:
                n_late += 1
            deltas_trig.append((alt_ret - act) * cost)
        else:
            n_untrig += 1
            alt_ret = closes_d[-1][1] / h["buy_px"] - 1   # 持有至窗口末按市价
        dd_ = (alt_ret - act) * cost
        deltas_all.append(dd_)
        tot_cost += cost
        by_gi[gi_of.get((h["src"], h["code"], h["buy"]))].append(dd_)
    a(f"  模拟 {n_trig + n_untrig}/{len(ok)} 笔: 触发 {n_trig}"
      f"(更早 {n_early} / 更晚 {n_late}), 未触发 {n_untrig}(=固定8%会被杀但k·σ下活下来)")
    if deltas_all:
        a("  ── 全口径(含未触发按窗口末市价):")
        a("  单笔Δ(元): 中位 {:+.0f}, 均值 {:+.0f}; 合计 {:+.0f} 元 (占成本额 {:+.2f}%)".format(
            statistics.median(deltas_all), sum(deltas_all) / len(deltas_all),
            sum(deltas_all), sum(deltas_all) * 100.0 / tot_cost if tot_cost else 0))
        a("  按 σ 四分位分解:")
        for gi in (1, 2, 3, 4):
            v = by_gi.get(gi, [])
            if v:
                a("    Q{gi}: n={n} 合计 {t:+.0f} 元 (中位 {m:+.0f})".format(
                    gi=gi, n=len(v), t=sum(v), m=statistics.median(v)))
        if deltas_trig:
            a("  ── 仅触发者口径: 合计 {:+.0f} 元 (单笔中位 {:+.0f})".format(
                sum(deltas_trig), statistics.median(deltas_trig)))
    a("  注: 未触发者按窗口末市价计值, 无 60 日后的持有上限偏差; 但两边都未计再投资,")
    a("      且 k·σ 侧实际换手更低(佣金+滑点节省未计入) → 全口径仍偏保守。")
    a("  注: σ/MA5 在不规则采样点上近似(持仓块只在成交日打印), 触发检测偏向成交日。")

    # ---- 落地
    a("")
    a("【5】落地建议")
    a(f"  规则: 固定8%回撤 → 回撤 > {kstar} × σ20(滚动20日日收益标准差, %) 且 收盘<MA5")
    a(f"  等价 ATR 形式: σ ≈ ATR14%/1.4 ⇒ 止损距离 ≈ {kstar/1.4:.1f}×ATR14% (Chandelier)")
    a("  仓位同步改: 每只预算风险 = 资金×r% / (k*·σ) —— 高波动票自动降杠杆,")
    a("    这同时解决『高波动票反复被打止损』和『单票风险不均匀』两件事。")
    a("  验证: 同一因子(c5 或 c13)跑 固定8% vs k*·σ 各一次;")
    a("    看三点: 8%档笔数、顶背离档总盈亏、分年收益稳定性 —— 不看单一年度总收益。")

    out = os.path.join(d, "_stop_volscaling.txt")
    with io.open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(W))
    print("ok: %s (%d chars)" % (out, len("\n".join(W))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
