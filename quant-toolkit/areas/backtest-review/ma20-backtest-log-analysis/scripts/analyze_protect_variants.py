# -*- coding: utf-8 -*-
"""v25 收益保护: 多方案反事实(金额口径)"""
import re, io, os
import pandas as pd, numpy as np

BASE = r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy"
CACHE = os.path.join(BASE, "price_cache")
LOG = os.path.join(BASE, "csi1000_backtest_log_20260929_225032.txt")
lines = io.open(LOG, encoding="utf-8", errors="replace").read().splitlines()

trades = []; open_b = {}
for ln in lines:
    m = re.search(r"\[(\d{8})\] \[买入\] (\d{6}\.[A-Z]{2}) (\S+?) \d+份 成交价([\d.]+) 金额([\d.]+)元", ln)
    if m:
        open_b[m.group(2)] = (m.group(1), m.group(3), float(m.group(4)), float(m.group(5))); continue
    m = re.search(r"\[(\d{8})\] \[卖出\] (\d{6}\.[A-Z]{2}) (\S+?) \d+份 成交价([\d.]+) 金额[\d.]+元 .*?\((.*)\)\s*$", ln)
    if m:
        c = m.group(2)
        ob = open_b.pop(c, None)
        if ob:
            trades.append(dict(c=c, nm=m.group(3), bd=ob[0], sd=m.group(1), entry=ob[2],
                               amt=ob[3], v0=float(m.group(4))/ob[2]-1, reason=m.group(5)))

bars = {}
for fn in os.listdir(CACHE):
    if not fn.endswith(".csv") or fn.startswith("_"): continue
    df = pd.read_csv(os.path.join(CACHE, fn), dtype={"date": str})
    df["d"] = df["date"].str.replace("-", "")
    df = df.sort_values("d").reset_index(drop=True)
    df["ma5"] = df["close"].astype(float).rolling(5).mean()
    bars[fn[:-4]] = df

def sim(t, rule, use_orig_for_high=True):
    """rule(pnl, peak_pnl)->阈值 or None"""
    df = bars.get(t["c"])
    if df is None: return t["v0"], t["sd"]
    sub = df[(df["d"] >= t["bd"]) & (df["d"] <= t["sd"])]
    if len(sub) < 2: return t["v0"], t["sd"]
    entry = float(sub.iloc[0]["close"]); hh = entry; peakp = 0.0
    for _, row in sub.iloc[1:].iterrows():
        px = float(row["close"]); hh = max(hh, px)
        pnl = px/entry-1; peakp = max(peakp, pnl); dd = px/hh-1
        thr = rule(pnl, peakp)
        if thr is not None and dd <= -thr and not np.isnan(row["ma5"]) and px < row["ma5"]:
            return px/entry-1, row["d"]
    return t["v0"], t["sd"]

# 方案定义 (pnl=当前浮盈, pk=峰值浮盈)
V = {
 "V1 补洞15%(10~50%)": lambda pnl, pk: 0.08 if pnl < 0.10 else (0.15 if pnl < 0.50 else None),
 "V2 全档20%棘轮":     lambda pnl, pk: 0.08 if pnl < 0.10 else 0.20,
 "V2b 30%以上用20%":   lambda pnl, pk: 0.08 if pnl < 0.10 else (0.15 if pnl < 0.30 else 0.20),
 "V3 守住峰值一半":     lambda pnl, pk: 0.08 if pnl < 0.10 else (max(0.10, pnl - 0.5*pk) if pk > 0 else None),
 "V4 全档25%棘轮":     lambda pnl, pk: 0.08 if pnl < 0.10 else 0.25,
}

base = sum(t["amt"]*t["v0"] for t in trades)
print("="*80)
print(f"可配对 {len(trades)} 笔, 买入金额合计 {sum(t['amt'] for t in trades):,.0f} 元")
print(f"V0 原规则 已实现盈亏: {base:,.0f} 元\n")
for name, rule in V.items():
    tot = 0.0; diffs = []
    for t in trades:
        r, d = sim(t, rule)
        tot += t["amt"]*r
        if abs(r - t["v0"]) > 0.005:
            diffs.append((t, r, t["amt"]*(r-t["v0"])))
    up = sum(1 for _, __, m in diffs if m > 0); dn = sum(1 for _, __, m in diffs if m < 0)
    print(f"{name:<20} 已实现 {tot:>12,.0f} 元  Δ{tot-base:>+11,.0f}  (差异{len(diffs)}笔 赚{up}/亏{dn})")
    if diffs:
        w = sorted(diffs, key=lambda x: x[2])
        for t, r, m in w[:2] + w[-2:]:
            print(f"      {t['c']} {t['nm']:<7} {t['v0']*100:>7.1f}% -> {r*100:>7.1f}%  {m:>+11,.0f}  [{t['reason'][:10]}]")
print("\nOK")
