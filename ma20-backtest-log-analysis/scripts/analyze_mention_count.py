# -*- coding: utf-8 -*-
"""大牛股在被买入前, 在'仓位已满'日被提及的次数分布 -> 验证'反复出现'是否为信号"""
import re, io
from collections import defaultdict

path = r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\csi1000_backtest_log_20260929_164335.txt"
re_full = re.compile(r"\[(\d{8})\] \[仓位已满\].*?得分前5: (.+?)$")
re_tok = re.compile(r"(\d{6}\.\S{2})")
re_sell = re.compile(r"\[(\d{8})\] \[卖出\] (\S+) (\S+?) \d+份.*?\(浮盈([-\d.]+)%")

mentions = defaultdict(list)   # code -> [dates]
for line in io.open(path, encoding="utf-8", errors="replace"):
    m = re_full.search(line)
    if m:
        for c in set(re_tok.findall(m.group(2))):
            mentions[c].append(m.group(1))

trades = defaultdict(list)     # code -> [(selldate, pct)]
for line in io.open(path, encoding="utf-8", errors="replace"):
    m = re_sell.search(line)
    if m:
        trades[m.group(2)].append((m.group(1), float(m.group(4))))

L = []; w = L.append
# 全体被提及股票: 提及次数 vs 后来买入与否 + 表现
w("被满仓日提及过的股票, 按提及次数分组的后续表现:")
w(f"{'提及次数段':<12}{'不同股票':>8}{'后来被买':>8}{'买入后均值%':>11}{'>=50%笔数':>10}")
buckets = [(1, 1), (2, 3), (4, 6), (7, 99)]
for lo, hi in buckets:
    codes = [c for c, ds in mentions.items() if lo <= len(ds) <= hi]
    nb = []; big = 0
    for c in codes:
        for d, p in trades.get(c, []):
            if not mentions[c] or d > mentions[c][-1]:
                nb.append(p)
                if p >= 50: big += 1
    w(f"{lo}-{hi}次    {len(codes):>8}{len(nb):>8}{(sum(nb)/len(nb) if nb else 0):>+11.2f}{big:>10}")

w("")
w(">=50%大牛股被买入前的满仓日提及次数 (买入日=首次成交近似):")
buys = defaultdict(list)
re_buy = re.compile(r"\[(\d{8})\] \[买入\] (\S+) (\S+?) ")
for line in io.open(path, encoding="utf-8", errors="replace"):
    m = re_buy.search(line)
    if m: buys[m.group(2)].append(m.group(1))
winners = ["300409", "002108", "300438", "300679", "603026", "600596"]
full_codes = {c[:6]: c for c in mentions}
for wc in winners:
    c = full_codes.get(wc)
    if not c: w(f"  {wc}: 未被满仓日提及过"); continue
    first_buy = min(buys.get(c, ["99999999"]))
    before = [d for d in mentions[c] if d < first_buy]
    span = (int(before[-1]) - int(before[0])) // 100 if before else 0
    w(f"  {c} 买入前提及 {len(before)} 次, 跨度约{span}个月 (首次提及{before[0] if before else '-'})")

io.open(r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\满仓候选提及次数检验.txt", "w", encoding="utf-8").write("\n".join(L))
print("OK")
