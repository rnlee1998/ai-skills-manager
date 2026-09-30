# -*- coding: utf-8 -*-
"""v24(215707) 平庸退出机制 逐年分析 + 退出反事实检验"""
import re, io, os
import pandas as pd, numpy as np
from collections import defaultdict

BASE = r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy"
CACHE = os.path.join(BASE, "price_cache")

LOGS = {
    "v24_combo12_cap10_exit": "csi1000_backtest_log_20260929_215707.txt",
    "v23_combo12_cap15_noexit": "csi1000_backtest_log_20260929_164335.txt",
    "v23_combo13_cap10_noexit": "csi1000_backtest_log_20260929_152140.txt",
    "v19_combo12_cap10_noexit": "csi1000_backtest_log_20260928_205211.txt",
}

# ---- 行情 ----
bars = {}
for fn in os.listdir(CACHE):
    if not fn.endswith(".csv") or fn.startswith("_"): continue
    df = pd.read_csv(os.path.join(CACHE, fn), dtype={"date": str})
    df["d"] = df["date"].str.replace("-", "")
    bars[fn[:-4]] = df.sort_values("d").reset_index(drop=True)
idx = pd.read_csv(os.path.join(CACHE, "_INDEX_000852.csv"), dtype={"date": str})
idx["d"] = idx["date"].str.replace("-", "")
idx = idx.sort_values("d").reset_index(drop=True)
idx_map = dict(zip(idx["d"], idx["close"].astype(float)))
cal = list(idx["d"])

def nav_series(path):
    """提取 (法定交易日 -> 总资产) 快照"""
    out = []; cur = None
    for line in io.open(path, encoding="utf-8", errors="replace"):
        m = re.search(r"交易日: (\d{8})", line)
        if m: cur = m.group(1); continue
        m = re.search(r"总资产: ([0-9.]+)", line)
        if m and cur: out.append((cur, float(m.group(1))))
    return out

print("="*80)
print("【A】逐年净值与本年度收益对比 (初始1000万)")
print(f"{'版本':<28}{'2020':>10}{'2021':>10}{'2022':>10}{'2023':>10}")
yearly = {}
for name, fn in LOGS.items():
    path = os.path.join(BASE, fn)
    if not os.path.exists(path): continue
    s = nav_series(path)
    if not s: continue
    # 年末净值: 每年最后一个快照
    byyear = {}
    for d, v in s:
        byyear[d[:4]] = (d, v)   # 顺序遍历 -> 保留每年最后一个快照=年末
    prev = 10_000_000.0
    rets = {}
    for y in ["2020", "2021", "2022", "2023"]:
        if y in byyear:
            v = byyear[y][1]
            rets[y] = (v / prev - 1) * 100; prev = v
    yearly[name] = rets
    print(f"{name:<28}" + "".join(f"{rets.get(y, float('nan')):>9.1f}%" for y in ["2020","2021","2022","2023"]))

# ---- 平庸退出事件 ----
print("\n" + "="*80)
print("【B】平庸退出事件反事实检验: 卖出后该股走势")
path = os.path.join(BASE, LOGS["v24_combo12_cap10_exit"])
ev = []
for line in io.open(path, encoding="utf-8", errors="replace"):
    if "平庸退出:" not in line or "[卖出]" not in line: continue
    m = re.search(r"\[(\d{8})\] \[卖出\] (\S+) (\S+?) (\d+)份 成交价([\d.]+)", line)
    if not m: continue
    date, code, name, sh, px = m.group(1), m.group(2), m.group(3), int(m.group(4)), float(m.group(5))
    m2 = re.search(r"持仓(\d+)日", line)
    hold = int(m2.group(1)) if m2 else None
    m3 = re.search(r"超额(-?[\d.]+)%", line)
    ex = float(m3.group(1)) if m3 else None
    ev.append(dict(date=date, code=code, name=name, px=px, hold=hold, ex=ex))

def after(code, d0, nd):
    df = bars.get(code)
    if df is None: return None
    sub = df[df["d"] >= d0].reset_index(drop=True)
    if len(sub) <= nd: return None
    p0 = float(sub.iloc[0]["close"]); p1 = float(sub.iloc[nd]["close"])
    i0 = idx_map.get(sub.iloc[0]["d"]); i1 = idx_map.get(sub.iloc[nd]["d"])
    stk = p1/p0 - 1
    exx = (1+stk)/(i1/i0) - 1 if i0 and i1 else None
    return stk, exx

print(f"{'日期':<10}{'代码':<11}{'名称':<9}{'持有':>4}{'超额%':>8} | {'后10日':>8}{'后20日':>8}{'后40日':>8} | {'后20超额':>9}")
rows = []
for e in ev:
    a10 = after(e["code"], e["date"], 10)
    a20 = after(e["code"], e["date"], 20)
    a40 = after(e["code"], e["date"], 40)
    f = lambda a, i: (a[i]*100 if a else float('nan'))
    print(f"{e['date']:<10}{e['code']:<11}{e['name']:<9}{e['hold'] or 0:>4}{e['ex'] or 0:>8.1f} | "
          f"{f(a10,0):>7.1f}%{f(a20,0):>7.1f}%{f(a40,0):>7.1f}% | {f(a20,1):>8.1f}%")
    if a20: rows.append((a10[0] if a10 else None, a20[0], a40[0] if a40 else None, a20[1]))

print(f"\n  样本 {len(rows)} 笔:")
for lab, i in [("后10日", 0), ("后20日", 1), ("后40日", 2)]:
    v = sorted([r[i] for r in rows if r[i] is not None])
    if v:
        print(f"    {lab} 个股收益: 中位 {v[len(v)//2]*100:+.1f}%  均值 {sum(v)/len(v)*100:+.1f}%  "
              f"跌的占比 {sum(1 for x in v if x<0)/len(v)*100:.0f}%")
v = sorted([r[3] for r in rows if r[3] is not None])
if v:
    print(f"    后20日相对指数超额: 中位 {v[len(v)//2]*100:+.1f}%  (负=卖对了)")

# ---- D 退出后腾出的槽位换入的新股表现 ----
print("\n" + "="*80)
print("【D】平庸退出当天腾出的槽位, 换入的新股表现如何")
buys = []   # (date, code, name)
sells = {}  # (code, buy_hint) -> we need pair; instead track realized pct per code sequentially
open_b = {}
realized = []   # (code, buy_date, sell_date, pct)
for line in io.open(path, encoding="utf-8", errors="replace"):
    m = re.search(r"\[(\d{8})\] \[买入\] (\S+) (\S+?) \d+份", line)
    if m: open_b[m.group(2)] = (m.group(1), m.group(3)); buys.append((m.group(1), m.group(2), m.group(3))); continue
    m = re.search(r"\[(\d{8})\] \[卖出\] (\S+) (\S+?) \d+份 .*?\(浮盈(-?[\d.]+)%", line)
    if m:
        c = m.group(2); pct = float(m.group(4))
        ob = open_b.pop(c, None)
        if ob: realized.append((c, ob[0], m.group(1), pct, ob[1]))

buy_on = {}
for d, c, n in buys: buy_on.setdefault(d, []).append(c)
exit_dates = set(e["date"] for e in ev)
refill_codes = []
for d in exit_dates:
    for c in buy_on.get(d, []): refill_codes.append((d, c))
print(f"  退出日当天有买入的: {len(exit_dates)} 个日期中 "
      f"{sum(1 for d in exit_dates if buy_on.get(d))} 个, 换入 {len(refill_codes)} 笔")
if refill_codes:
    rc = set(c for d, c in refill_codes)
    sub = [r for r in realized if r[0] in rc and r[1] in exit_dates]
    if sub:
        ps = sorted(r[3] for r in sub)
        print(f"  这些'换入即出'的替补交易 {len(sub)} 笔: 中位 {ps[len(ps)//2]:+.1f}%  "
              f"均值 {sum(ps)/len(ps):+.1f}%  盈利占比 {sum(1 for x in ps if x>0)/len(ps)*100:.0f}%")
allp = sorted(r[3] for r in realized)
print(f"  参考: v24 全部已实现交易 {len(allp)} 笔 中位 {allp[len(allp)//2]:+.1f}%  "
      f"均值 {sum(allp)/len(allp):+.1f}%  盈利占比 {sum(1 for x in allp if x>0)/len(allp)*100:.0f}%")
print("\nOK")
