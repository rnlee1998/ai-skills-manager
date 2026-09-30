# -*- coding: utf-8 -*-
"""回答两个问题:
Q1 怎么抓到牛股 -> 牛股的入场DNA: 首次入场 vs 再入场的收益分布, 大牛股是第几次尝试
Q2 满仓时能否选更好标的 -> 仓位已满日打印的高分候选, 后来被买入后的实际表现
"""
import re, io
from collections import defaultdict

LOGS = {
    "旧combo13cap10": r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\csi1000_backtest_log_20260929_152140.txt",
    "新combo12cap15": r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\csi1000_backtest_log_20260929_164335.txt",
}
re_sell = re.compile(r"\[(\d{8})\] \[卖出\] (\S+) (\S+?) \d+份 成交价[\d.]+ 金额(\d+)元 佣金\d+元 \(浮盈([-\d.]+)%")
re_buy = re.compile(r"\[(\d{8})\] \[买入\] (\S+) (\S+?) \d+份 成交价[\d.]+ 金额\d+元")
re_full = re.compile(r"\[(\d{8})\] \[仓位已满\].*?得分前5: (.+?)$")
re_cand_tok = re.compile(r"(\d{6}\.\S{2})\(得分([\d.]+)\)")

L = []; w = L.append

for tag, path in LOGS.items():
    events = []  # (date, type, code, name, pct)
    full_days = []  # (date, [(code, score)])
    for line in io.open(path, encoding="utf-8", errors="replace"):
        m = re_sell.search(line)
        if m:
            events.append((m.group(1), "S", m.group(2), m.group(3), float(m.group(5)))); continue
        m = re_buy.search(line)
        if m:
            events.append((m.group(1), "B", m.group(2), m.group(3), None)); continue
        m = re_full.search(line)
        if m:
            cands = re_cand_tok.findall(m.group(2))
            if cands: full_days.append((m.group(1), cands))

    events.sort(key=lambda x: x[0])
    # 配对: 每笔卖出匹配最近一笔未平仓买入, 得到 (日期, 代码, 名称, 收益%, 第几次尝试, 距上次卖出的天数)
    open_lots = defaultdict(list)  # code -> list of (date, attempt_no)
    attempt_counter = defaultdict(int)
    last_sell_date = {}
    trades = []  # (selldate, code, name, pct, attempt, gap_days)
    for d, t, c, nm, pct in events:
        if t == "B":
            attempt_counter[c] += 1
            open_lots[c].append((d, attempt_counter[c]))
        else:
            if open_lots[c]:
                bd, att = open_lots[c].pop(0)
                gap = (int(d) - int(last_sell_date[c])) if c in last_sell_date else None
                trades.append((d, c, nm, pct, att, gap))
                last_sell_date[c] = d

    w("="*72)
    w(f"【{tag}】共配对 {len(trades)} 笔交易")
    # Q1: 按尝试次数分组
    w("")
    w("Q1a 按第N次尝试入场的单笔收益分布:")
    groups = defaultdict(list)
    for d, c, nm, pct, att, gap in trades:
        groups[min(att, 4)].append(pct)  # 4+ 合并
    w(f"{'尝试次数':<8}{'笔数':>6}{'胜率':>8}{'均值%':>9}{'中位%':>9}{'>=50%笔数':>10}")
    for g in sorted(groups):
        ps = sorted(groups[g])
        n = len(ps); wins = sum(1 for p in ps if p > 0)
        big = sum(1 for p in ps if p >= 50)
        label = f"{g}+" if g == 4 else f"第{g}次"
        w(f"{label:<8}{n:>6}{wins/n*100:>7.1f}%{sum(ps)/n:>+9.2f}{ps[n//2]:>+9.2f}{big:>10}")

    # Q1b 大牛股(>=50%)的尝试档案
    w("")
    w("Q1b 收益>=50%的大牛股档案 (第几次尝试抓到 / 之前尝试的结果):")
    prior = defaultdict(list)  # code -> prior pcts in order
    for d, c, nm, pct, att, gap in sorted(trades, key=lambda x: x[0]):
        if pct >= 50:
            pl = prior[c] if prior[c] else ["首次即中"]
            w(f"  {d} {c} {nm:<8} +{pct:.1f}%  第{att}次尝试  历史尝试: {', '.join(f'{p:+.1f}%' if isinstance(p,float) else p for p in pl)}")
        prior[c].append(pct)

    # Q1c 再入场间隔
    gaps = [g for d, c, nm, pct, att, gap in trades if att >= 2 and gap is not None and pct >= 20]
    all_gaps = [g for d, c, nm, pct, att, gap in trades if att >= 2 and gap is not None]
    if all_gaps:
        all_gaps.sort()
        w("")
        w(f"Q1c 再入场间隔(距上次卖出交易日数): 中位 {all_gaps[len(all_gaps)//2]}, 赢家(>=20%)的间隔中位 "
          f"{sorted(gaps)[len(gaps)//2] if gaps else 'NA'}")

    # Q2: 仓位已满日的高分候选, 之后是否被买入, 买了表现如何
    w("")
    w("Q2 满仓日高分候选的后续归宿:")
    bought_codes = defaultdict(list)  # code -> [(date,pct)] trades
    for d, c, nm, pct, att, gap in trades:
        bought_codes[c].append((d, pct))
    seen_dates = {}  # code -> first full-day mention date
    mention_days = 0; unique_c = set()
    later_bought = []; never = set()
    for fd, cands in full_days:
        for c, sc in cands:
            mention_days += 1; unique_c.add(c)
            if c not in seen_dates: seen_dates[c] = fd
    for c, fd in seen_dates.items():
        after = [(d, p) for d, p in bought_codes.get(c, []) if d > fd]
        if after: later_bought.append((c, fd, after[0]))
        else: never.add(c)
    w(f"  满仓日共 {len(full_days)} 天, 提及候选 {mention_days} 次 / {len(unique_c)} 只不同股票")
    w(f"  其中后来真被买入的: {len(later_bought)} 只; 从未被买入: {len(never)} 只")
    if later_bought:
        pcts = [p for c, fd, (d, p) in later_bought]
        pcts_s = sorted(pcts)
        wins = sum(1 for p in pcts if p > 0)
        big = sum(1 for p in pcts if p >= 30)
        w(f"  这些'曾与槽位失之交臂'的候选, 最终交易表现: 胜率 {wins/len(pcts)*100:.1f}%, "
          f"均值 {sum(pcts)/len(pcts):+.2f}%, 中位 {pcts_s[len(pcts_s)//2]:+.2f}%, >=30%共{big}笔")
        top = sorted(later_bought, key=lambda x: -x[2][1])[:8]
        for c, fd, (d, p) in top:
            w(f"    {c} 满仓日{fd}提及 -> {d}成交 {p:+.1f}%")

io.open(r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\抓牛股与满仓选股_检验结果.txt", "w", encoding="utf-8").write("\n".join(L))
print("OK")
