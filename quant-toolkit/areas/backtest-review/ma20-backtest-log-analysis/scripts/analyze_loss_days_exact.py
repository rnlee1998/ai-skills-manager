# -*- coding: utf-8 -*-
"""亏损交易持有天数分布(精确口径) + 快照浮亏天数(部分样本, 需注明口径)
修正: 日志持仓快照只在有交易的日子打印(覆盖~40%交易日), 之前基于快照的'转正用时/浮亏天数'是低估。
精确口径: 所有 [date] 行 = 交易日历; 亏损单持有天数 = 买入日到卖出日的交易日数。
"""
import re, io
from collections import defaultdict

LOGS = {
    "旧combo13cap10": r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\csi1000_backtest_log_20260929_152140.txt",
    "新combo12cap15": r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\csi1000_backtest_log_20260929_164335.txt",
}
re_sell = re.compile(r"\[(\d{8})\] \[卖出\] (\S+) (\S+?) \d+份.*?\(浮盈([-\d.]+)%")
re_buy = re.compile(r"\[(\d{8})\] \[买入\] (\S+) (\S+?) ")
re_day = re.compile(r"交易日: (\d{8})")
re_anydate = re.compile(r"^\[(\d{8})\]")
re_pos = re.compile(r"^\s+(\d{6}\.\S{2})\s+\S+\s+\d+\s+[\d.]+\s+[\d.]+\s+\d+\s+[-+][\d.]+\s+[-+][\d,]+ \(([-+][\d.]+)%\)")

L = []; w = L.append

for tag, path in LOGS.items():
    cal = set(); events = []; snaps = {}; cur = None
    for line in io.open(path, encoding="utf-8", errors="replace"):
        m = re_anydate.match(line)
        if m: cal.add(m.group(1))
        m = re_sell.search(line)
        if m: events.append((m.group(1), "S", m.group(2), m.group(3), float(m.group(4)))); continue
        m = re_buy.search(line)
        if m: events.append((m.group(1), "B", m.group(2), m.group(3), None)); continue
        m = re_day.search(line)
        if m: cur = m.group(1); snaps.setdefault(cur, {}); continue
        m = re_pos.match(line)
        if m and cur: snaps[cur][m.group(1)] = float(m.group(2))

    days = sorted(cal); didx = {d: i for i, d in enumerate(days)}
    w("="*72)
    w(f"【{tag}】交易日历 {len(days)} 天 (从日志全部日期行提取), 事件日快照 {len(snaps)} 天")
    open_ep = {}; losers = []; winners = []
    for d, t, c, nm, pct in events:
        if t == "B": open_ep[c] = (d, nm)
        else:
            ep = open_ep.pop(c, None)
            if ep is None: continue
            hold = didx[d] - didx[ep[0]]  # 买入日->卖出日的交易日间隔
            (winners if pct > 0 else losers).append((c, nm or ep[1], pct, hold))
    w("")
    w(">> 亏损单持有天数分布 (精确: 买入到卖出的交易日数)")
    hs = sorted(r[3] for r in losers); n = len(hs)
    w(f"  n={n}  均值{sum(hs)/n:.1f}天  中位{hs[n//2]}天  p25={hs[n//4]} p75={hs[n*3//4]} "
      f"p90={hs[int(n*0.9)]} max={hs[-1]}")
    w("  直方图:")
    for lo, hi, lab in [(1,1,"1天"), (2,2,"2天"), (3,3,"3天"), (4,5,"4-5天"), (6,8,"6-8天"),
                        (9,12,"9-12天"), (13,99,"13天以上")]:
        sub = [r for r in losers if lo <= r[3] <= hi]
        if not sub: continue
        bar = "#" * max(1, int(len(sub)/n*60))
        w(f"    {lab:<8}{len(sub):>4}笔 ({len(sub)/n*100:4.1f}%)  平均亏损{sum(r[2] for r in sub)/len(sub):+5.1f}%  {bar}")
    w("")
    w(">> 对照: 盈利单持有天数分布")
    hs2 = sorted(r[3] for r in winners); n2 = len(hs2)
    w(f"  n={n2}  均值{sum(hs2)/n2:.1f}天  中位{hs2[n2//2]}天  p25={hs2[n2//4]} p75={hs2[n2*3//4]} "
      f"p90={hs2[int(n2*0.9)]} max={hs2[-1]}")
    w("")
    w(">> 大额亏损单(<=-8%) vs 小额亏损单(-8%~0) 的持有天数:")
    for lab, cond in [("亏损<=-8%", lambda p: p <= -8), ("亏损-8%~0", lambda p: -8 < p <= 0)]:
        sub = sorted(r[3] for r in losers if cond(r[2]))
        if not sub: continue
        m = len(sub)
        w(f"  {lab:<10} n={m:>3}  均值{sum(sub)/m:.1f} 中位{sub[m//2]} p75={sub[m*3//4]} p90={sub[int(m*0.9)]}")
    w("")
    w(">> [部分样本口径] 有快照日的浮亏情况 (快照仅覆盖~40%交易日, 仅看方向性):")
    snap_stat = []
    open_ep2 = {}
    for d, t, c, nm, pct in events:
        if t == "B": open_ep2[c] = d
        else:
            bd = open_ep2.pop(c, None)
            if bd is None or pct > 0: continue
            ps = [snaps[dd][c] for dd in sorted(snaps) if bd <= dd <= d and c in snaps[dd]]
            if ps: snap_stat.append((all(p < 0 for p in ps), all(p > 0 for p in ps), len(ps)))
    a = sum(1 for s in snap_stat if s[0]); b = sum(1 for s in snap_stat if s[1])
    w(f"  可见快照的亏损单 {len(snap_stat)} 笔: 快照全为浮亏 {a} 笔({a/len(snap_stat)*100:.0f}%), "
      f"快照全为浮盈 {b} 笔({b/len(snap_stat)*100:.0f}%), 其余有正有负 {len(snap_stat)-a-b} 笔")

io.open(r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\亏损交易持有天数分布_精确版.txt", "w", encoding="utf-8").write("\n".join(L))
print("OK")
