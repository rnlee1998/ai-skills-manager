# -*- coding: utf-8 -*-
"""盈利股票从买入到浮盈首次转正需要多少天(交易日)"""
import re, io
from collections import defaultdict

LOGS = {
    "旧combo13cap10": r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\csi1000_backtest_log_20260929_152140.txt",
    "新combo12cap15": r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\csi1000_backtest_log_20260929_164335.txt",
}
re_sell = re.compile(r"\[(\d{8})\] \[卖出\] (\S+) (\S+?) \d+份.*?\(浮盈([-\d.]+)%")
re_buy = re.compile(r"\[(\d{8})\] \[买入\] (\S+) (\S+?) ")
re_day = re.compile(r"交易日: (\d{8})")
re_pos = re.compile(r"^\s+(\d{6}\.\S{2})\s+\S+\s+\d+\s+[\d.]+\s+[\d.]+\s+\d+\s+[-+][\d.]+\s+[-+][\d,]+ \(([-+][\d.]+)%\)")

L = []; w = L.append

for tag, path in LOGS.items():
    events = []      # ordered: (date, 'B'/'S', code)
    snapshots = {}   # date -> {code: pct}
    cur_date = None
    for line in io.open(path, encoding="utf-8", errors="replace"):
        m = re_sell.search(line)
        if m:
            events.append((m.group(1), "S", m.group(2), float(m.group(4)))); continue
        m = re_buy.search(line)
        if m:
            events.append((m.group(1), "B", m.group(2), None)); continue
        m = re_day.search(line)
        if m:
            cur_date = m.group(1); snapshots.setdefault(cur_date, {}); continue
        m = re_pos.match(line)
        if m and cur_date:
            snapshots[cur_date][m.group(1)] = float(m.group(2))

    dates = sorted(snapshots)
    didx = {d: i for i, d in enumerate(dates)}
    # 配对 episode: 买入 -> 卖出
    open_ep = {}   # code -> buy_date
    results = []   # (final_pct, tturn_days_or_None, hold_days, code)
    for d, t, c, pct in events:
        if t == "B":
            open_ep[c] = d
        else:
            bd = open_ep.pop(c, None)
            if bd is None: continue
            # 扫描买入日(含)之后到卖出日(含)的快照, 找首次 pct>0
            first_pos = None
            for dd in dates:
                if dd < bd or dd > d: continue
                p = snapshots[dd].get(c)
                if p is not None and p > 0:
                    first_pos = dd; break
            tturn = didx[first_pos] - didx[bd] if first_pos else None
            hold = didx[d] - didx[bd]
            results.append((pct, tturn, hold, c))

    dates_n = len(dates)
    w("="*66)
    w(f"【{tag}】共 {len(results)} 笔平仓交易, {dates_n} 个快照交易日")
    for label, cond in [
        ("全部盈利单(卖出浮盈>0)", lambda p: p > 0),
        ("  其中小盈 0<p<10%", lambda p: 0 < p < 10),
        ("  其中中盈 10<=p<50%", lambda p: 10 <= p < 50),
        ("  其中大盈 p>=50%", lambda p: p >= 50),
        ("对照: 亏损单(p<=0)", lambda p: p <= 0),
    ]:
        sub = [r for r in results if cond(r[0])]
        if not sub: w(f"{label:<28} 无"); continue
        tt = [r[1] for r in sub if r[1] is not None]
        never = sum(1 for r in sub if r[1] is None)
        tt_s = sorted(tt)
        med = tt_s[len(tt_s)//2] if tt else None
        w(f"{label:<28} n={len(sub):>3}  馌正天数: 均值{sum(tt)/len(tt):>5.1f} 中位{med:>4} "
          f"p25={tt_s[len(tt_s)//4]:>3} p75={tt_s[len(tt_s)*3//4]:>3}  (从未飘正 {never} 笔)")
    # 亏损单中"曾飘正过"的比例
    loss = [r for r in results if r[0] <= 0]
    ever = sum(1 for r in loss if r[1] is not None)
    w(f"亏损单中曾飘正过的: {ever}/{len(loss)} ({ever/max(len(loss),1)*100:.0f}%)  "
      f"即这些单先给过蝇头小利再套住")
    # 大盈单明细
    w("")
    w("大盈单(p>=50%)明细: 飘正用时(交易日) / 总持有 / 最终收益")
    for p, tt, hold, c in sorted([r for r in results if r[0] >= 50], key=lambda x: -x[0]):
        w(f"  {c}  最终{p:+6.1f}%   飘正:{tt if tt is not None else '从未':>4}天   持有:{hold}天")

io.open(r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\盈利股票飘正用时_检验.txt", "w", encoding="utf-8").write("\n".join(L))
print("OK")
