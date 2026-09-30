# -*- coding: utf-8 -*-
"""v25 收益保护诊断: 回撤定位 + 回撤来源拆分 + 盈利回吐(MFE vs realized)"""
import re, io, os
import pandas as pd, numpy as np
from collections import defaultdict

BASE = r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy"
CACHE = os.path.join(BASE, "price_cache")
LOG = os.path.join(BASE, "csi1000_backtest_log_20260929_225032.txt")

lines = io.open(LOG, encoding="utf-8", errors="replace").read().splitlines()

# ---------- A. 净值曲线 + 回撤 ----------
nav = []; cur = None
switch = {}
for ln in lines:
    m = re.search(r"交易日: (\d{8})", ln)
    if m: cur = m.group(1); continue
    m = re.search(r"总资产: ([0-9.]+)", ln)
    if m and cur: nav.append((cur, float(m.group(1))))
    m = re.search(r"\[(\d{8})\] \[大盘\].*?开关(ON|OFF)", ln)
    if m: switch[m.group(1)] = m.group(2)

# 去重(同日只留最后)
seen = {}
for d, v in nav: seen[d] = v
nav = sorted(seen.items())
vals = np.array([v for d, v in nav])
dates = [d for d, v in nav]
print("="*78)
print(f"【A】净值快照 {len(nav)} 个交易日, {dates[0]} ~ {dates[-1]}")
peak = -1; peak_i = 0; mdd = 0; mdd_seg = None
dd_list = []
cur_peak = vals[0]; cur_pi = 0
for i, v in enumerate(vals):
    if v > cur_peak: cur_peak, cur_pi = v, i
    dd = v/cur_peak - 1
    if dd < mdd: mdd, mdd_seg = dd, (cur_pi, i)
    dd_list.append((dd, cur_pi, i))
print(f"  区间最高净值 {vals.max():,.0f} ({dates[int(vals.argmax())]}), 最低 {vals.min():,.0f} ({dates[int(vals.argmin())]})")
print(f"  全期最大回撤 {mdd*100:.1f}%  ({dates[mdd_seg[0]]} -> {dates[mdd_seg[1]]})")

# Top5 回撤(互不重叠, 按峰值日去重)
segs = []
cur_peak = vals[0]; cur_pi = 0; trough = vals[0]; trough_i = 0
for i, v in enumerate(vals):
    if v > cur_peak:
        if cur_pi != trough_i and trough < cur_peak:
            segs.append((cur_peak, vals[trough_i], dates[cur_pi], dates[trough_i], cur_pi, trough_i))
        cur_peak, cur_pi, trough, trough_i = v, i, v, i
    if v < trough: trough, trough_i = v, i
if cur_pi != trough_i:
    segs.append((cur_peak, vals[trough_i], dates[cur_pi], dates[trough_i], cur_pi, trough_i))
segs = sorted(segs, key=lambda s: s[1]/s[0])[:6]
print("\n  最大 6 段回撤(峰->谷):")
print(f"    {'峰值日':>10}{'谷底日':>10}{'峰净值':>12}{'谷净值':>12}{'回撤':>8}{'历时(交易日)':>10}")
for pk, tr, dp, dt, pi, ti in segs:
    print(f"    {dp:>10}{dt:>10}{pk:>12,.0f}{tr:>12,.0f}{(tr/pk-1)*100:>7.1f}%{ti-pi:>10}")

# ---------- B. 回撤期间大盘开关状态 ----------
print("\n" + "="*78)
print("【B】最大回撤期间的大盘开关状态(死叉只禁买、不清仓)")
pk, tr, dp, dt, pi, ti = segs[0]
seg_dates = dates[pi:ti+1]
on = sum(1 for d in seg_dates if switch.get(d) == "ON")
off = sum(1 for d in seg_dates if switch.get(d) == "OFF")
print(f"  {dp}→{dt} 区间 {len(seg_dates)} 个交易日: 开关ON {on} 日 / OFF {off} 日")
# 全期 OFF 日占比
allon = sum(1 for v in switch.values() if v == "ON"); alloff = sum(1 for v in switch.values() if v == "OFF")
print(f"  全期开关: ON {allon} 日 / OFF {alloff} 日 (OFF 占比 {alloff/(allon+alloff)*100:.0f}%)")

# ---------- C. 盈利回吐: MFE vs 实际卖出 ----------
bars = {}
for fn in os.listdir(CACHE):
    if not fn.endswith(".csv") or fn.startswith("_"): continue
    df = pd.read_csv(os.path.join(CACHE, fn), dtype={"date": str})
    df["d"] = df["date"].str.replace("-", "")
    bars[fn[:-4]] = df.sort_values("d").reset_index(drop=True)

trades = []; open_b = {}
for ln in lines:
    m = re.search(r"\[(\d{8})\] \[买入\] (\S+) (\S+?) \d+份", ln)
    if m: open_b[m.group(2)] = (m.group(1), m.group(3)); continue
    m = re.search(r"\[(\d{8})\] \[卖出\] (\S+) (\S+?) \d+份 .*?\((.*)\)\s*$", ln)
    if m:
        c, nm, sd, reason = m.group(2), m.group(3), m.group(1), m.group(4)
        mp = re.search(r"浮盈(-?[\d.]+)%", reason)
        if mp: pct = float(mp.group(1))
        else:
            mb = re.search(r"买入价([\d.]+)\s*现价([\d.]+)", reason)
            pct = (float(mb.group(2))/float(mb.group(1))-1)*100 if mb else None
        ob = open_b.pop(c, None)
        if ob: trades.append((c, nm, ob[0], sd, pct, reason))

miss = 0; gv = []
for c, nm, bd, sd, pct, reason in trades:
    if pct is None: continue
    df = bars.get(c)
    if df is None: miss += 1; continue
    sub = df[(df["d"] >= bd) & (df["d"] <= sd)]
    if len(sub) == 0: miss += 1; continue
    entry = float(sub.iloc[0]["close"])
    mfe = float(sub["close"].max())/entry - 1
    gv.append((c, nm, bd, sd, mfe*100, pct, (mfe*100 - pct), reason))

print("\n" + "="*78)
print(f"【C】盈利回吐: 持有期内最大浮盈(MFE) - 实际卖出收益  (成交 {len(trades)} 笔, 行情缺失 {miss})")
g2 = [g for g in gv if g[4] >= 10]     # 曾赚过>=10%的
gb = [g[6] for g in g2]
print(f"  曾浮盈≥10% 的交易 {len(g2)} 笔: 回吐 中位 {np.median(gb):.1f}pp / 均值 {np.mean(gb):.1f}pp")
g3 = [g for g in gv if g[4] >= 50]
gb3 = [g[6] for g in g3]
if g3:
    print(f"  曾浮盈≥50% 的大赢家 {len(g3)} 笔: MFE中位 {np.median([g[4] for g in g3]):.1f}% -> "
          f"实际中位 {np.median([g[5] for g in g3]):.1f}%  回吐 中位 {np.median(gb3):.1f}pp / 均值 {np.mean(gb3):.1f}pp")
    tot_mfe = sum(g[4] for g in g3); tot_real = sum(g[5] for g in g3)
    print(f"  ★ 这 {len(g3)} 笔合计: 峰值浮盈 {tot_mfe:,.0f}pp -> 落袋 {tot_real:,.0f}pp, 回吐 {tot_mfe-tot_real:,.0f}pp (吐掉 {(tot_mfe-tot_real)/tot_mfe*100:.0f}%)")
print("\n  回吐最多的 12 笔:")
print(f"    {'代码':<11}{'名称':<9}{'买入':>10}{'卖出':>10}{'MFE%':>8}{'实收%':>8}{'回吐pp':>8}  原因")
for c, nm, bd, sd, mfe, pct, back, reason in sorted(gv, key=lambda x: -x[6])[:12]:
    r = "顶背离" if "顶背离" in reason else ("平庸退出" if "平庸退出" in reason else ("回撤止损" if "回撤" in reason else "其他"))
    print(f"    {c:<11}{nm:<9}{bd:>10}{sd:>10}{mfe:>8.1f}{pct:>8.1f}{back:>8.1f}  {r}")
print("\nOK")
