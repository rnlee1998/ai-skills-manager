# -*- coding: utf-8 -*-
"""v25 补洞反事实: 若把 15% 回撤规则扩展到所有 浮盈>=10%, 能少回吐多少"""
import re, io, os
import pandas as pd, numpy as np

BASE = r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy"
CACHE = os.path.join(BASE, "price_cache")
LOG = os.path.join(BASE, "csi1000_backtest_log_20260929_225032.txt")
lines = io.open(LOG, encoding="utf-8", errors="replace").read().splitlines()

trades = []; open_b = {}
for ln in lines:
    m = re.search(r"\[(\d{8})\] \[买入\] (\S+) (\S+?) \d+份", ln)
    if m: open_b[m.group(2)] = (m.group(1), m.group(3)); continue
    m = re.search(r"\[(\d{8})\] \[卖出\] (\S+) (\S+?) \d+份 .*?\((.*)\)\s*$", ln)
    if m:
        c, nm, sd, reason = m.group(2), m.group(3), m.group(1), m.group(4)
        mp = re.search(r"浮盈(-?[\d.]+)%", reason)
        pct = float(mp.group(1)) if mp else None
        if pct is None:
            mb = re.search(r"买入价([\d.]+)\s*现价([\d.]+)", reason)
            pct = (float(mb.group(2))/float(mb.group(1))-1)*100 if mb else None
        ob = open_b.pop(c, None)
        if ob: trades.append((c, nm, ob[0], sd, pct, reason))

bars = {}
for fn in os.listdir(CACHE):
    if not fn.endswith(".csv") or fn.startswith("_"): continue
    df = pd.read_csv(os.path.join(CACHE, fn), dtype={"date": str})
    df["d"] = df["date"].str.replace("-", "")
    df = df.sort_values("d").reset_index(drop=True)
    df["ma5"] = df["close"].astype(float).rolling(5).mean()
    bars[fn[:-4]] = df

miss_codes = sorted(set(c for c, nm, b, s, p, r in trades if c not in bars))
have = [t for t in trades if t[0] in bars and t[4] is not None]
print(f"v25 交易 {len(trades)} 笔; 有行情 {len(have)} 笔; 缺 {len(miss_codes)} 只: {','.join(c[:6] for c in miss_codes[:40])}")

# 反事实: 把 15% 档扩展到所有 pnl>=10%  (关闭 30-50% 缺口)
saved_pp = []
print("\n" + "="*84)
print("补洞反事实: 浮盈>=10% 一律用 15% 回撤+破MA5  (原规则 30%<=浮盈<50% 无保护)")
print(f"{'代码':<11}{'名称':<9}{'买入':>10}{'卖出':>10}{'实收%':>8}{'补洞后%':>9}{'改善pp':>8}{'补洞卖出日':>12}")
for c, nm, bd, sd, pct, reason in sorted(have, key=lambda x: -x[4]):
    df = bars[c]
    sub = df[(df["d"] >= bd) & (df["d"] <= sd)]
    if len(sub) < 2: continue
    entry = float(sub.iloc[0]["close"])
    if entry <= 0: continue
    hh = entry; new_exit = None; new_px = None
    for _, row in sub.iloc[1:].iterrows():
        px = float(row["close"]); hh = max(hh, px)
        pnl = px/entry - 1; dd = px/hh - 1
        thr = 0.08 if pnl < 0.10 else 0.15
        if dd <= -thr and not np.isnan(row["ma5"]) and px < row["ma5"]:
            new_exit = row["d"]; new_px = px; break
    new_pct = (new_px/entry - 1)*100 if new_px else pct
    imp = new_pct - pct
    if abs(imp) >= 3:   # 只打印有明显差异的
        mark = "  <== 补洞省下" if imp > 0 else "  (补洞更差)"
        print(f"{c:<11}{nm:<9}{bd:>10}{sd:>10}{pct:>8.1f}{new_pct:>9.1f}{imp:>8.1f}{str(new_exit) if new_exit else '-':>12}{mark}")
    saved_pp.append(imp)

sv = np.array(saved_pp)
print(f"\n  全部 {len(sv)} 笔: 补洞后收益变化 中位 {np.median(sv):+.1f}pp / 均值 {sv.mean():+.1f}pp")
print(f"  改善的 {np.sum(sv>1)} 笔 / 变差的 {np.sum(sv<-1)} 笔 / 基本不变 {(np.abs(sv)<=1).sum()} 笔")
print(f"  累计 pp 变化 {sv.sum():+.0f}pp")
print("\nOK")
