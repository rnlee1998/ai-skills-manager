# -*- coding: utf-8 -*-
"""演示: 相对中证1000超额(excess)的精确计算 + 真实数据验证"""
import json, io, os
import pandas as pd, numpy as np

BASE = r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy"
CACHE = os.path.join(BASE, "price_cache")
TRADES = os.path.join(BASE, "trades_all.json")

trades = json.load(io.open(TRADES, encoding="utf-8"))
bars = {}
for fn in os.listdir(CACHE):
    if not fn.endswith(".csv") or fn.startswith("_"): continue
    df = pd.read_csv(os.path.join(CACHE, fn), dtype={"date": str})
    df["d"] = df["date"].str.replace("-", "")
    bars[fn[:-4]] = df.sort_values("d").reset_index(drop=True)

idx = pd.read_csv(os.path.join(CACHE, "_INDEX_000852.csv"), dtype={"date": str})
idx["d"] = idx["date"].str.replace("-", "")
idx = idx.sort_values("d").reset_index(drop=True)
idx_series = pd.Series(idx["close"].astype(float).values,
                    index=pd.to_datetime(idx["d"].values))

def excess_vs_csi1000(buy_price, cur_price, idx_close_buy, idx_close_cur):
    stock_ret = cur_price / buy_price - 1.0
    idx_ret   = idx_close_cur / idx_close_buy - 1.0
    if idx_ret <= -0.999: return float('nan')
    return (1.0 + stock_ret) / (1.0 + idx_ret) - 1.0

# ---- 真实数据验证: T=10 时点的超额分布 + 后续表现 ----
print("="*70)
print("T=10 时点: 相对中证1000超额分布 & 该规则后续判别力")
T = 10
for tag in sorted(set(t[0] for t in trades)):
    rows = []
    for tag_, code, name, bd, sd, pct, att in trades:
        if tag_ != tag: continue
        df = bars.get(code)
        if df is None: continue
        sub = df[(df["d"] >= bd) & (df["d"] <= sd)]
        if len(sub) <= T + 2: continue
        entry = float(sub.iloc[0]["close"])
        cur   = float(sub.iloc[T]["close"])
        idx_b = idx_series.asof(pd.Timestamp(bd))
        idx_c = idx_series.asof(pd.Timestamp(sub.iloc[T]["d"]))
        if pd.isna(idx_b) or pd.isna(idx_c): continue
        ex = excess_vs_csi1000(entry, cur, idx_b, idx_c)
        if np.isnan(ex): continue
        remain = float(sub.iloc[-1]["close"]) / cur - 1.0
        rows.append((ex, remain, pct, code))
    if not rows: continue
    arr = np.array([r[0] for r in rows])
    print(f"\n【{tag}】可用 {len(rows)} 笔")
    print(f"  T=10 超额: 中位 {np.median(arr)*100:+.1f}%  均值 {arr.mean()*100:+.1f}%  "
          f"p10 {np.percentile(arr,10)*100:+.1f}%  p25 {np.percentile(arr,25)*100:+.1f}%")
    trig = [r for r in rows if r[0] < -0.05]
    other= [r for r in rows if r[0] >= -0.05]
    if trig and other:
        print(f"  excess<-5% 触发 {len(trig)} 笔 | 后续收益中位 "
              f"{np.median([r[1] for r in trig])*100:+.1f}%  最终中位 "
              f"{np.median([r[2] for r in trig]):+.1f}%")
        print(f"  excess>=-5% 未触发 {len(other)} 笔 | 后续收益中位 "
              f"{np.median([r[1] for r in other])*100:+.1f}%  最终中位 "
              f"{np.median([r[2] for r in other]):+.1f}%")

# ---- 一个具体例子: 找一笔 excess 先<-5% 而后又起飞 / 与一笔持续跑输 ----
print("\n" + "="*70)
print("具体个股样例: 某笔交易逐日 excess")
ex = []
for tag_, code, name, bd, sd, pct, att in trades:
    df = bars.get(code)
    if df is None: continue
    sub = df[(df["d"] >= bd) & (df["d"] <= sd)]
    if len(sub) <= 30: continue
    entry = float(sub.iloc[0]["close"]); idx_b = idx_series.asof(pd.Timestamp(bd))
    if pd.isna(idx_b): continue
    line = []
    for i in range(0, min(len(sub), 30), 5):
        c = float(sub.iloc[i]["close"]); ic = idx_series.asof(pd.Timestamp(sub.iloc[i]["d"]))
        if pd.isna(ic): continue
        line.append((sub.iloc[i]["d"], excess_vs_csi1000(entry, c, idx_b, ic)))
    if any(l[1] < -0.05 for l in line) and pct > 20 and all(abs(l[1]) < 1.2 for l in line):
        print(f"\n  {code} {name} 最终+{pct:.0f}% (先跑输后起飞型):")
        for d, v in line: print(f"    {d}  excess {v*100:+.1f}%")
        break
print("\nOK")
