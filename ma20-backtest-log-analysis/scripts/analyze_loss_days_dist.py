# -*- coding: utf-8 -*-
"""亏损交易的'亏损天数'分布: 持有期内浮盈<0的交易日数统计"""
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
    events = []
    snapshots = {}
    cur_date = None
    for line in io.open(path, encoding="utf-8", errors="replace"):
        m = re_sell.search(line)
        if m:
            events.append((m.group(1), "S", m.group(2), m.group(3), float(m.group(4)))); continue
        m = re_buy.search(line)
        if m:
            events.append((m.group(1), "B", m.group(2), m.group(3), None)); continue
        m = re_day.search(line)
        if m:
            cur_date = m.group(1); snapshots.setdefault(cur_date, {}); continue
        m = re_pos.match(line)
        if m and cur_date:
            snapshots[cur_date][m.group(1)] = float(m.group(2))

    dates = sorted(snapshots)
    didx = {d: i for i, d in enumerate(dates)}
    open_ep = {}
    losses = []   # (code, name, final_pct, hold_days, loss_days, win_days)
    for d, t, c, nm, pct in events:
        if t == "B":
            open_ep[c] = (d, nm)
        else:
            ep = open_ep.pop(c, None)
            if ep is None or pct > 0: continue
            bd, bnm = ep
            pcts = [snapshots[dd].get(c) for dd in dates if bd <= dd <= d]
            pcts = [p for p in pcts if p is not None]
            loss_days = sum(1 for p in pcts if p < 0)
            win_days = sum(1 for p in pcts if p > 0)
            losses.append((c, nm or bnm, pct, didx[d]-didx[bd], loss_days, win_days))

    def dist(vals, label):
        vals = sorted(vals); n = len(vals)
        w(f"{label:<14} n={n:>3}  均值{sum(vals)/n:>6.1f}  中位{vals[n//2]:>4}  "
          f"p25={vals[n//4]:>3}  p75={vals[n*3//4]:>3}  p90={vals[int(n*0.9)]:>3}  max={vals[-1]:>3}")

    w("="*70)
    w(f"【{tag}】亏损单 {len(losses)} 笔")
    w("")
    dist([r[4] for r in losses], "浮亏天数")
    dist([r[3] for r in losses], "总持有天数")
    dist([r[4]/max(r[3],1)*100 for r in losses], "浮亏占比%")
    w("")
    w("浮亏天数分布直方图:")
    buckets = [(0,0,"0天(始终未飘正的相反:天天亏)"), (1,3,"1-3天"), (4,6,"4-6天"), (7,10,"7-10天"),
               (11,15,"11-15天"), (16,25,"16-25天"), (26,99,"26天以上")]
    for lo, hi, lab in buckets:
        sub = [r for r in losses if lo <= r[4] <= hi]
        if not sub: continue
        avg_final = sum(r[2] for r in sub)/len(sub)
        bar = "#" * max(1, int(len(sub)/len(losses)*50))
        w(f"  {lab:<8} {len(sub):>3}笔 ({len(sub)/len(losses)*100:4.1f}%)  平均最终亏损{avg_final:+5.1f}%  {bar}")
    w("")
    w("交叉: '从未飘正'(浮亏天数=持有期全部)的单:")
    never = [r for r in losses if r[4] >= r[3]]
    dist([r[3] for r in never], "  其持有天数")
    w(f"  共{len(never)}笔, 占亏损单{len(never)/len(losses)*100:.0f}%, 平均最终亏损{sum(r[2] for r in never)/max(len(never),1):+.1f}%")

io.open(r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\亏损交易亏损天数分布_检验.txt", "w", encoding="utf-8").write("\n".join(L))
print("OK")
