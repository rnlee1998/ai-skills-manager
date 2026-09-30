# -*- coding: utf-8 -*-
"""Q1 先亏后盈占比 / Q2 长期未触发止损的槽位占用 / Q3 无效占用的识别方法检验
数据: price_cache/*.csv (qfq, 腾讯源) + _INDEX_000852.csv
"""
import re, io, os, json
from collections import defaultdict
import pandas as pd
import numpy as np

BASE = r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy"
CACHE = os.path.join(BASE, "price_cache")
TRADES = os.path.join(BASE, "trades_all.json")
OUT = os.path.join(BASE, "无效占用诊断_三问_结果.txt")

trades = json.load(io.open(TRADES, encoding="utf-8"))
# trades: [tag, code, name, buy, sell, pct, attempt]

# --- 载入行情 ---
bars = {}
for fn in os.listdir(CACHE):
    if not fn.endswith(".csv") or fn.startswith("_"): continue
    code = fn[:-4]
    df = pd.read_csv(os.path.join(CACHE, fn), dtype={"date": str})
    df["d"] = df["date"].str.replace("-", "")
    df = df.sort_values("d")
    bars[code] = df.reset_index(drop=True)

idx = pd.read_csv(os.path.join(CACHE, "_INDEX_000852.csv"), dtype={"date": str})
idx["d"] = idx["date"].str.replace("-", "")
idx = idx.sort_values("d").reset_index(drop=True)
idx_map = dict(zip(idx["d"], idx["close"]))
cal = list(idx["d"])
didx = {d: i for i, d in enumerate(cal)}

def series_for(code, d0, d1):
    df = bars.get(code)
    if df is None: return None
    s = df[(df["d"] >= d0) & (df["d"] <= d1)].reset_index(drop=True)
    return s if len(s) else None

def macd_hist(closes, fast=12, slow=26, sig=9):
    c = pd.Series(closes, dtype=float)
    ef = c.ewm(span=fast, adjust=False).mean()
    es = c.ewm(span=slow, adjust=False).mean()
    dif = ef - es
    dea = dif.ewm(span=sig, adjust=False).mean()
    return (dif - dea).values

L = []; w = L.append

# ============ 逐笔重建 ============
recs = []
for tag, code, name, bd, sd, pct_log, att in trades:
    df = bars.get(code)
    if df is None: continue
    # 全序列(含买入前, 用于MA5/MACD/量能)
    full = df[df["d"] <= sd]
    if len(full) == 0: continue
    sub = df[(df["d"] >= bd) & (df["d"] <= sd)]
    if len(sub) == 0: continue
    entry = float(sub.iloc[0]["close"])
    if entry <= 0: continue
    closes = sub["close"].values.astype(float)
    pnl = closes / entry - 1
    peak = np.maximum.accumulate(closes)
    dd = 1 - closes / peak
    ma5 = pd.Series(full["close"].values.astype(float)).rolling(5).mean().values[-len(closes):]
    macd = macd_hist(full["close"].values.astype(float))[-len(closes):]
    vol = full["volume"].values.astype(float)[-len(closes):]
    idx_dates = [d for d in sub["d"]]
    i0 = didx[bd]
    idx_val0 = idx_map.get(bd, np.nan)
    recs.append(dict(tag=tag, code=code, name=name, buy=bd, sell=sd, pct=pct_log,
                     i0=i0, closes=closes, pnl=pnl, dd=dd, ma5=ma5, macd=macd, vol=vol,
                     dates=idx_dates, entry=entry, n=len(closes)))

w(f"重建 {len(recs)} / {len(trades)} 笔")

# ============ Q1 先亏后盈 ============
w("")
w("="*76)
w("Q1 是否先亏损后转正? 占比多少?")
for tag in sorted(set(r["tag"] for r in recs)):
    sub = [r for r in recs if r["tag"] == tag]
    win = [r for r in sub if r["pct"] > 0]
    los = [r for r in sub if r["pct"] <= 0]
    both = []; never_dn = []
    uw_before = []
    for r in win:
        neg_days = [i for i in range(1, r["n"]) if r["pnl"][i] < -0.001]
        first_pos = next((i for i in range(1, r["n"]) if r["pnl"][i] > 0.001), None)
        if neg_days:
            pre = [i for i in neg_days if first_pos is None or i < first_pos]
            if pre: both.append(r); uw_before.append(len(pre))
            else: never_dn.append(r)
        else:
            never_dn.append(r)
    w(f"【{tag}】盈利单 {len(win)} 笔")
    w(f"  先亏后盈(转正前有过收盘浮亏): {len(both)} 笔, 占盈利单 {len(both)/len(win)*100:.1f}%")
    if uw_before:
        u = sorted(uw_before)
        w(f"  这些单转正前的水下天数: 中位{u[len(u)//2]} 均值{sum(u)/len(u):.1f} p75={u[len(u)*3//4]} max={u[-1]}")
    w(f"  从未浮亏(一路没破成本): {len(never_dn)} 笔 ({len(never_dn)/len(win)*100:.1f}%)")
    if both:
        w(f"  先亏后盈单的平均最终收益 {sum(r['pct'] for r in both)/len(both):+.1f}%  vs  "
          f"未亏过单 {sum(r['pct'] for r in never_dn)/max(len(never_dn),1):+.1f}%")
    # 亏损单里"曾经浮盈过"的
    had_up = [r for r in los if any(r["pnl"][i] > 0.001 for i in range(1, r["n"]))]
    w(f"  亏损单中曾浮盈过的: {len(had_up)}/{len(los)} ({len(had_up)/len(los)*100:.1f}%)")

# ============ Q2 长期未触发止损但占用槽位 ============
w("")
w("="*76)
w("Q2 长期未触发止损线、却长期占用槽位的单子")
for tag in sorted(set(r["tag"] for r in recs)):
    sub = [r for r in recs if r["tag"] == tag]
    for r in sub:
        # 一档止损触发判定: 浮盈<10% 且 从最高回撤>8% 且 收盘<MA5
        trig = False; trig_i = None
        for i in range(r["n"]):
            if np.isnan(r["ma5"][i]): continue
            if r["pnl"][i] < 0.10 and r["dd"][i] > 0.08 and r["closes"][i] < r["ma5"][i]:
                trig = True; trig_i = i; break
        r["trig"] = trig; r["trig_i"] = trig_i
        r["maxdd"] = float(r["dd"].max())
        r["hold"] = r["n"] - 1
    total_slot = sum(max(r["hold"], 0) for r in sub)
    zombies = [r for r in sub if r["hold"] >= 15 and not r["trig"] and r["pct"] < 10]
    zslot = sum(r["hold"] for r in zombies)
    w(f"【{tag}】总交易 {len(sub)} 笔, 总占用槽位 {total_slot} 槽·日")
    w(f"  僵尸单(持有>=15交易日 且 从未触发一档止损 且 最终收益<10%): {len(zombies)} 笔 "
      f"({len(zombies)/len(sub)*100:.1f}%), 占用 {zslot} 槽·日 ({zslot/total_slot*100:.1f}%)")
    if zombies:
        hs = sorted(r["hold"] for r in zombies)
        ps = sorted(r["pct"] for r in zombies)
        dd_ = sorted(r["maxdd"] for r in zombies)
        w(f"  其持有天数: 中位{hs[len(hs)//2]} p75={hs[len(hs)*3//4]} max={hs[-1]}")
        w(f"  其最终收益: 中位{ps[len(ps)//2]:+.1f}% 均值{sum(ps)/len(ps):+.1f}% 最好{ps[-1]:+.1f}%")
        w(f"  期内最大回撤(从最高): 中位{dd_[len(dd_)//2]*100:.1f}% max={dd_[-1]*100:.1f}%")
        w(f"  僵尸单里最终盈利的: {sum(1 for r in zombies if r['pct']>0)} 笔, 平均"
          f"{sum(r['pct'] for r in zombies if r['pct']>0)/max(sum(1 for r in zombies if r['pct']>0),1):+.1f}%")
    # 槽位占用结构
    w("  槽位占用结构(按最终收益分类占比):")
    cats = [("大赢家>=50%", lambda p: p >= 50), ("中赢10-50%", lambda p: 10 <= p < 50),
            ("小赢0-10%", lambda p: 0 < p < 10), ("小亏-8~0%", lambda p: -8 <= p <= 0),
            ("大亏<-8%", lambda p: p < -8)]
    for lab, cond in cats:
        s2 = [r for r in sub if cond(r["pct"])]
        sl = sum(r["hold"] for r in s2)
        w(f"    {lab:<12}{len(s2):>4}笔  槽·日 {sl:>5} ({sl/max(total_slot,1)*100:4.1f}%)  "
          f"平均持有{sum(r['hold'] for r in s2)/max(len(s2),1):5.1f}天")

# ============ Q3 识别方法检验 ============
w("")
w("="*76)
w("Q3 识别无效占用: 方法检验 (在T=10日时点用当时可知信息, 看后续表现)")
T = 10
for tag in sorted(set(r["tag"] for r in recs)):
    sub = [r for r in recs if r["tag"] == tag and r["n"] > T + 2]
    w(f"【{tag}】可用于T={T}检验的交易 {len(sub)} 笔")
    rows = []
    for r in sub:
        i = T
        rT = r["pnl"][i]
        peakT = r["closes"][:i+1].max()
        ddT = 1 - r["closes"][i] / peakT
        i_buy = didx[r["buy"]]
        exT = (1 + rT) / (idx_map[r["dates"][i]] / idx_map[r["buy"]]) - 1
        high_flag = 1 if peakT > r["closes"][0] * 1.02 else 0
        m = r["macd"]
        macd_now = m[i] if not np.isnan(m[i]) else np.nan
        macd_prev = m[i-2] if i-2 >= 0 and not np.isnan(m[i-2]) else np.nan
        macd_fall = 1 if (not np.isnan(macd_now) and not np.isnan(macd_prev) and macd_now < macd_prev) else 0
        v5 = np.mean(r["vol"][i-4:i+1]); v20 = np.mean(r["vol"][max(0, i-19):i+1])
        vr = v5 / v20 if v20 > 0 else np.nan
        remain = r["closes"][-1] / r["closes"][i] - 1
        rows.append(dict(rt=rT, ddt=ddT, ex=exT, high=high_flag, mf=macd_fall, vr=vr,
                         remain=remain, final=r["pct"], hold=r["hold"], code=r["code"]))
    df = pd.DataFrame(rows)
    def tmean(s):  # 去掉最高最低5%的截尾均值
        s = sorted(s.dropna())
        if len(s) < 8: return sum(s)/max(len(s), 1)
        k = max(1, int(len(s)*0.05))
        core = s[k:-k]
        return sum(core)/len(core)

    w(f"  全体: T=10已实现收益均值 {df['rt'].mean()*100:+.1f}%, 后续(10日->卖出)收益: "
      f"中位 {df['remain'].median()*100:+.1f}% 截尾均值 {tmean(df['remain'])*100:+.1f}%")
    def bucket(col, bins, labels):
        w(f"  按 {col} 分档 的后续收益(中位/截尾均值):")
        for lo, hi, lab in zip(bins[:-1], bins[1:], labels):
            s2 = df[(df[col] > lo) & (df[col] <= hi)]
            if len(s2) >= 3:
                w(f"    {lab:<18} n={len(s2):>3}  后续中位 {s2['remain'].median()*100:+6.1f}%  "
                  f"截尾均值 {tmean(s2['remain'])*100:+6.1f}%  | 最终收益中位 {s2['final'].median():+6.1f}%")
    bucket("rt", [-1, -0.05, -0.02, 0, 0.05, 0.10, 9], ["<-5%", "-5~-2%", "-2~0%", "0~5%", "5~10%", ">10%"])
    bucket("ex", [-1, -0.15, -0.05, 0, 0.05, 9], ["跑输>15%", "跑输15~5%", "跑输5~0%", "跑赢0~5%", "跑赢>5%"])
    bucket("ddt", [-1, 0, 0.05, 0.10, 9], ["无回撤", "0-5%", "5-10%", ">10%"])
    bucket("vr", [0, 0.6, 0.9, 1.2, 99], ["量能<0.6", "0.6-0.9", "0.9-1.2", ">1.2"])
    # 组合规则检验
    w("  组合规则检验(规则触发=建议退出):")
    rules = {
        "R1 浮亏且未创新高": (df["rt"] < 0) & (df["high"] == 0),
        "R2 跑输指数5%以上": df["ex"] < -0.05,
        "R3 MACD柱衰减": df["mf"] == 1,
        "R4 量能萎缩<0.9": df["vr"] < 0.9,
        "R5 R1且R2": (df["rt"] < 0) & (df["high"] == 0) & (df["ex"] < -0.05),
    }
    for lab, mask in rules.items():
        a = df[mask]; b = df[~mask]
        if len(a) >= 3:
            w(f"    {lab:<20} 触发{len(a):>3}笔 后续中位{a['remain'].median()*100:+6.1f}% | "
              f"未触发{len(b):>3}笔 后续中位{b['remain'].median()*100:+6.1f}%   差"
              f"{(a['remain'].median()-b['remain'].median())*100:+6.1f}pp")
    # 负动量排名(横截面)检验
    w("  负动量排名(横截面相对指数超额, 末位=最弱) 检验:")
    snap = []
    start_i = didx.get("20200102", 0)
    for d_i in range(start_i + 10, len(cal) - 12):
        d = cal[d_i]
        act = [r for r in recs if r["tag"] == tag and r["buy"] <= d <= r["sell"]]
        if len(act) < 4: continue
        vals = []
        for r in act:
            j = next((k for k, dd in enumerate(r["dates"]) if dd == d), None)
            if j is None: continue
            ex = (1 + r["pnl"][j]) / (idx_map[d] / idx_map[r["buy"]]) - 1
            fwd = None
            d5 = cal[min(d_i + 5, len(cal) - 1)]
            j5 = next((k for k, dd in enumerate(r["dates"]) if dd >= d5), None)
            if j5 is not None:
                fwd = (r["closes"][j5] / r["closes"][j] - 1) - (idx_map[d5] / idx_map[d] - 1)
            vals.append((ex, fwd))
        if len(vals) < 4: continue
        vals.sort(key=lambda x: x[0])
        q = max(1, len(vals) // 4)
        bot = [v[1] for v in vals[:q] if v[1] is not None]
        top = [v[1] for v in vals[-q:] if v[1] is not None]
        if bot and top: snap.append((sum(bot)/len(bot), sum(top)/len(top)))
    if snap:
        bs = sorted(s[0] for s in snap); ts = sorted(s[1] for s in snap)
        b = bs[len(bs)//2]; t = ts[len(ts)//2]
        w(f"    样本 {len(snap)} 个截面(日): 最弱1/4持仓未来5日超额 中位{b*100:+.2f}% (均值{sum(bs)/len(bs)*100:+.2f}%), "
          f"最强1/4 中位{t*100:+.2f}% (均值{sum(ts)/len(ts)*100:+.2f}%), 中位差 {(b-t)*100:+.2f}pp")
        w(f"    最弱1/4跑输最强1/4的截面占比: {sum(1 for s in snap if s[0]<s[1])/len(snap)*100:.0f}%")

io.open(OUT, "w", encoding="utf-8").write("\n".join(L))
print("OK", flush=True)
