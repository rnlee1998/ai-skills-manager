# -*- coding: utf-8 -*-
"""对比 v23 combo13/cap10 (152140) vs combo12/cap15 (164335)
拆解: 持仓上限 10->15 与 因子 combo13->combo12 各自的影响
"""
import re, io, sys
from collections import defaultdict

OLD = r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\csi1000_backtest_log_20260929_152140.txt"
NEW = r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\csi1000_backtest_log_20260929_164335.txt"
OUT = r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\cap15_vs_cap10_对比结果.txt"

re_sell = re.compile(
    r"\[(\d{8})\] \[卖出\] (\S+) (\S+?) \d+份 成交价[\d.]+ 金额(\d+)元 佣金\d+元 \(浮盈([-\d.]+)%")
re_daily = re.compile(r"累计收益: ([-+][\d.]+)%")
re_buy = re.compile(r"\[(\d{8})\] \[买入\] (\S+) (\S+?) (\d+)份 成交价([\d.]+) 金额(\d+)元")
re_cand = re.compile(r"\[(\d{8})\] \[买入候选\] 按因子得分取前(\d+)只")
re_total = re.compile(r"总资产: ([\d.]+), 累计收益: ([-+][\d.]+)")

def parse(path):
    sells = []  # (date, code, name, amount, pct)
    buys = []
    daily = {}  # date -> total asset
    for line in io.open(path, encoding="utf-8", errors="replace"):
        m = re_sell.search(line)
        if m:
            sells.append((m.group(1), m.group(2), m.group(3), int(m.group(4)), float(m.group(5))))
            continue
        m = re_buy.search(line)
        if m:
            buys.append((m.group(1), m.group(2), m.group(3), int(m.group(4)), float(m.group(5)), int(m.group(6))))
            continue
        m = re_total.search(line)
        if m:
            daily[line[1:9]] = float(m.group(1))
    return sells, buys, daily

def yearly_trades(sells):
    y = defaultdict(lambda: [0, 0.0, 0])  # n, sum_pct, wins
    for d, c, nm, amt, pct in sells:
        k = d[:4]
        y[k][0] += 1; y[k][1] += pct
        if pct > 0: y[k][2] += 1
    return y

def stats(sells):
    pcts = sorted(s[4] for s in sells)
    n = len(pcts)
    wins = [p for p in pcts if p > 0]
    loss = [p for p in pcts if p <= 0]
    # 金额加权平均收益
    tot_amt = sum(s[3] for s in sells)
    wret = sum(s[3]*s[4]/100 for s in sells)
    return dict(n=n, win=len(wins)/n*100, avg=sum(pcts)/n, med=pcts[n//2],
                avg_w=sum(wins)/len(wins), avg_l=sum(loss)/len(loss),
                wret=wret, tot_amt=tot_amt,
                p5=pcts[int(n*0.05)], p25=pcts[int(n*0.25)], p75=pcts[int(n*0.75)], p95=pcts[int(n*0.95)])

old_s, old_b, old_d = parse(OLD)
new_s, new_b, new_d = parse(NEW)

L = []
w = L.append
w("="*70)
w("v23 对比: combo13+上限10 (152140)  vs  combo12+上限15 (164335)")
w("回测区间均 20200102-20231229, 初始 1000 万")
w("="*70)

for tag, s, b in [("旧: combo13 cap10", old_s, old_b), ("新: combo12 cap15", new_s, new_b)]:
    st = stats(s)
    w("")
    w(f"--- {tag} ---")
    w(f"卖出 {st['n']} 笔, 胜率 {st['win']:.1f}%, 平均单笔 {st['avg']:+.2f}%, 中位 {st['med']:+.2f}%")
    w(f"  盈利单均值 {st['avg_w']:+.2f}% / 亏损单均值 {st['avg_l']:+.2f}%")
    w(f"  分位: p5={st['p5']:+.1f}% p25={st['p25']:+.1f}% p75={st['p75']:+.1f}% p95={st['p95']:+.1f}%")
    w(f"  卖出总金额 {st['tot_amt']/1e4:.0f} 万, 金额加权累计收益 {st['wret']/1e4:+.1f} 万")
    w(f"  买入 {len(b)} 笔")

# 年度
w("")
w("--- 年度卖出笔数 / 平均浮盈% / 胜率 ---")
yo, yn = yearly_trades(old_s), yearly_trades(new_s)
w(f"{'年份':<6}{'旧cap10笔数':>10}{'旧均%':>8}{'旧胜率':>8}{'|新cap15笔数':>12}{'新均%':>8}{'新胜率':>8}")
for y in sorted(set(yo) | set(yn)):
    a = yo.get(y, [0,0,0]); b = yn.get(y, [0,0,0])
    w(f"{y:<6}{a[0]:>10}{a[1]/max(a[0],1):>8.2f}{a[2]/max(a[0],1)*100:>7.1f}%{('|'+str(b[0])):>12}{b[1]/max(b[0],1):>8.2f}{b[2]/max(b[0],1)*100:>7.1f}%")

# 年末资产
w("")
w("--- 每年最后交易日总资产 ---")
for tag, d in [("旧cap10", old_d), ("新cap15", new_d)]:
    ys = {}
    for dt in sorted(d):
        ys[dt[:4]] = (dt, d[dt])
    w(f"{tag}: " + ", ".join(f"{y}:{v/1e4:.0f}万({dt})" for y, (dt, v) in sorted(ys.items())))

# 头部盈利/亏损贡献
w("")
w("--- 单笔贡献 TOP10 (盈利) / BOTTOM10 (亏损) ---")
for tag, s in [("旧cap10", old_s), ("新cap15", new_s)]:
    w(f"\n{tag}:")
    top = sorted(s, key=lambda x: -x[3]*x[4]/100)[:10]
    bot = sorted(s, key=lambda x: x[3]*x[4]/100)[:10]
    for d, c, nm, amt, pct in top:
        w(f"  盈 {d} {c} {nm:<8} {amt/1e4:6.1f}万 {pct:+7.2f}% -> {amt*pct/100/1e4:+7.1f}万")
    for d, c, nm, amt, pct in bot:
        w(f"  亏 {d} {c} {nm:<8} {amt/1e4:6.1f}万 {pct:+7.2f}% -> {amt*pct/100/1e4:+7.1f}万")

# 同股对照: 两版都交易过的股票, 比各自平均单笔收益
w("")
w("--- 同股两版平均单笔浮盈对照 (两版都卖出>=2次的股票, 按差异排序) ---")
old_avg = defaultdict(list); new_avg = defaultdict(list)
old_nm = {}
for d, c, nm, amt, pct in old_s: old_avg[c].append(pct); old_nm[c] = nm
for d, c, nm, amt, pct in new_s: new_avg[c].append(pct)
rows = []
for c in set(old_avg) & set(new_avg):
    if len(old_avg[c]) >= 2 and len(new_avg[c]) >= 2:
        a = sum(old_avg[c])/len(old_avg[c]); b = sum(new_avg[c])/len(new_avg[c])
        rows.append((a-b, c, old_nm.get(c, ""), a, len(old_avg[c]), b, len(new_avg[c])))
rows.sort(key=lambda x: -abs(x[0]))
w(f"{'代码':<12}{'名称':<10}{'旧均%':>8}{'笔数':>5}{'新均%':>8}{'笔数':>5}{'差':>8}")
for diff, c, nm, a, na, b, nb in rows[:25]:
    w(f"{c:<12}{nm:<10}{a:>8.2f}{na:>5}{b:>8.2f}{nb:>5}{diff:>+8.2f}")

# 首日15只 vs 前10只的归宿: 在新日志中追踪20200106买入的15只
w("")
w("--- 新日志 20200106 首日买入 15 只的完整归宿 (排名1-10 vs 11-15) ---")
first15 = [b for b in new_b if b[0] == "20200106"]
# sell map: code -> list of (date,pct)
sell_map = defaultdict(list)
for d, c, nm, amt, pct in new_s: sell_map[c].append((d, pct))
for i, (d, c, nm, sh, px, amt) in enumerate(first15):
    rk = f"r{i+1:02d}"
    sells_c = sell_map[c]
    if sells_c:
        w(f"  {rk} {c} {nm:<8} " + "; ".join(f"{sd}卖 {p:+.1f}%" for sd, p in sells_c))
    else:
        w(f"  {rk} {c} {nm:<8} (日志期内未卖出/仍持有)")

io.open(OUT, "w", encoding="utf-8").write("\n".join(L))
print("OK", len(L))
