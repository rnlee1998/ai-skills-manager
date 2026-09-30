# -*- coding: utf-8 -*-
"""割肉后是否被重新买入? 按卖出原因统计再入场率、间隔、再入场收益"""
import re, io, os
from collections import defaultdict

BASE = r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy"
IDX = os.path.join(BASE, "price_cache", "_INDEX_000852.csv")

LOGS = {
    "v24_combo12_cap10_exit": "csi1000_backtest_log_20260929_215707.txt",
    "v23_combo12_cap15_noexit": "csi1000_backtest_log_20260929_164335.txt",
    "v23_combo13_cap10_noexit": "csi1000_backtest_log_20260929_152140.txt",
}

# 交易日历
cal = []
for line in io.open(IDX, encoding="utf-8", errors="replace"):
    m = re.match(r"\s*(\d{4}-\d{2}-\d{2})", line)
    if m: cal.append(m.group(1).replace("-", ""))
if not cal:
    import csv
    with io.open(IDX, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r: cal.append(str(row["date"]).replace("-", ""))
cal = sorted(set(cal)); didx = {d: i for i, d in enumerate(cal)}

def classify(reason):
    if "顶背离" in reason: return "顶背离"
    if "平庸退出" in reason: return "平庸退出"
    if "回撤" in reason: return "回撤止损"
    return "其他"

for name, fn in LOGS.items():
    path = os.path.join(BASE, fn)
    if not os.path.exists(path): continue
    events = []  # (date, 'B'/'S', code, name, reason, pct)
    for line in io.open(path, encoding="utf-8", errors="replace"):
        m = re.search(r"\[(\d{8})\] \[买入\] (\S+) (\S+?) \d+份", line)
        if m:
            events.append((m.group(1), "B", m.group(2), m.group(3), "", None)); continue
        m = re.search(r"\[(\d{8})\] \[卖出\] (\S+) (\S+?) \d+份 .*?\((.*)\)\s*$", line)
        if m:
            reason = m.group(4)
            mp = re.search(r"浮盈(-?[\d.]+)%", reason)
            if mp:
                pct = float(mp.group(1))
            else:
                mb = re.search(r"买入价([\d.]+)\s*现价([\d.]+)", reason)
                pct = (float(mb.group(2)) / float(mb.group(1)) - 1) * 100 if mb else None
            events.append((m.group(1), "S", m.group(2), m.group(3), reason, pct))

    # 配对成交 -> 每笔 trade 的 realized pct
    open_b = {}; trades = []   # (code, name, buy, sell, pct, reason)
    for d, t, c, nm, reason, pct in events:
        if t == "B": open_b[c] = (d, nm)
        else:
            ob = open_b.pop(c, None)
            if ob: trades.append((c, nm, ob[0], d, pct, reason))
    buy_dates = defaultdict(list)
    for c, nm, b, s, p, r in trades: buy_dates[c].append((b, s, p, r))

    sells = [(c, nm, s, r, p) for c, nm, b, s, p, r in trades]
    print("="*78)
    print(f"【{name}】交易 {len(trades)} 笔")

    def gap_days(d0, d1):
        return didx.get(d1, -1) - didx.get(d0, -1)

    stat = defaultdict(lambda: [0, 0, [], []])  # reason -> [sells, rebought, gaps, re_pct]
    for c, nm, s, r, p in sells:
        k = classify(r)
        stat[k][0] += 1
        nxt = [x for x in buy_dates[c] if x[0] > s]
        if nxt:
            nb = min(nxt, key=lambda x: x[0])
            stat[k][1] += 1
            stat[k][2].append(gap_days(s, nb[0]))
            if nb[2] is not None: stat[k][3].append(nb[2])
        stat["全部"][0] += 1
        if nxt:
            stat["全部"][1] += 1
            stat["全部"][2].append(gap_days(s, min(nxt, key=lambda x: x[0])[0]))
            if min(nxt, key=lambda x: x[0])[2] is not None:
                stat["全部"][3].append(min(nxt, key=lambda x: x[0])[2])

    print(f"{'卖出原因':<10}{'卖出':>5}{'再买入':>7}{'再入率':>7}{'再入间隔中位':>12}   再入场那笔收益(中位/均值/胜率)")
    for k in ["全部", "回撤止损", "平庸退出", "顶背离"]:
        n, rb, gaps, rp = stat[k]
        if n == 0: continue
        gm = sorted(gaps)[len(gaps)//2] if gaps else None
        if rp:
            rs = sorted(rp)
            print(f"{k:<10}{n:>5}{rb:>7}{rb/n*100:>6.0f}%{(''+str(gm)+'日') if gm is not None else '-':>12}   "
                  f"{rs[len(rs)//2]:+.1f}% / {sum(rs)/len(rs):+.1f}% / {sum(1 for x in rs if x>0)/len(rs)*100:.0f}%")
        else:
            print(f"{k:<10}{n:>5}{rb:>7}{rb/n*100:>6.0f}%{(''+str(gm)+'日') if gm is not None else '-':>12}   -")

    # 同一只股票被反复买卖的次数分布
    cnt = defaultdict(int)
    for c, nm, s, r, p in sells: cnt[c] += 1
    dist = defaultdict(int)
    for c, v in cnt.items(): dist[v] += 1
    print("  个股被卖出次数分布: " + " ".join(f"{k}次:{v}只" for k, v in sorted(dist.items())))
    print("  ★ 反复被交易(卖出≥3次)的股票: " +
          ", ".join(f"{c}({cnt[c]}次)" for c in sorted(cnt, key=lambda x: -cnt[x]) if cnt[c] >= 3)[:300])
print("\nOK")
