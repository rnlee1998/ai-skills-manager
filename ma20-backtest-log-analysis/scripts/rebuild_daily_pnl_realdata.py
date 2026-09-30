# -*- coding: utf-8 -*-
"""用真实行情重建每笔交易的逐日浮盈亏:
- 亏损单: 水下(收盘<成本)天数精确分布
- 盈利单: 转正用时精确分布 (修正之前快照口径的低估)
数据源: akshare stock_zh_a_hist_tx (腾讯, qfq), 本地CSV缓存, 8线程
"""
import re, io, os, json, time
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

LOGS = {
    "旧combo13cap10": r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\csi1000_backtest_log_20260929_152140.txt",
    "新combo12cap15": r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\csi1000_backtest_log_20260929_164335.txt",
}
CACHE = r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\price_cache"
OUT = r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\真实行情浮盈亏重建_结果.txt"
TRADES_JSON = r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy\trades_all.json"
os.makedirs(CACHE, exist_ok=True)

import pandas as pd
import akshare as ak

re_sell = re.compile(r"\[(\d{8})\] \[卖出\] (\S+) (\S+?) \d+份.*?\(浮盈([-\d.]+)%")
re_buy = re.compile(r"\[(\d{8})\] \[买入\] (\S+) (\S+?) ")
re_anydate = re.compile(r"^\[(\d{8})\]")

# ---------- 1. 提取交易 ----------
trades = []  # tag, code, name, buy, sell, pct
for tag, path in LOGS.items():
    open_ep = {}
    for line in io.open(path, encoding="utf-8", errors="replace"):
        m = re_sell.search(line)
        if m:
            d, c, nm, pct = m.group(1), m.group(2), m.group(3), float(m.group(4))
            ep = open_ep.pop(c, None)
            if ep: trades.append((tag, c, nm, ep[0], d, pct, ep[2]))
            continue
        m = re_buy.search(line)
        if m:
            c = m.group(2)
            open_ep[c] = (m.group(1), m.group(3), len([t for t in trades if t[1] == c]))
            continue
json.dump(trades, io.open(TRADES_JSON, "w", encoding="utf-8"))
codes = sorted(set(t[1] for t in trades))
print(f"trades={len(trades)} unique_codes={len(codes)}", flush=True)

# ---------- 2. 批量取日线(缓存) ----------
lock = threading.Lock()
fails = []
def fetch(code):
    fp = os.path.join(CACHE, code + ".csv")
    if os.path.exists(fp) and os.path.getsize(fp) > 200:
        return code, True
    sym = ("sh" if code.endswith(".SH") else "sz") + code[:6]
    for attempt in range(3):
        try:
            df = ak.stock_zh_a_hist_tx(symbol=sym, start_date="20191201",
                                       end_date="20240110", adjust="qfq")
            if df is not None and len(df) > 0:
                df.to_csv(fp, index=False, encoding="utf-8")
                return code, True
        except Exception as e:
            time.sleep(1 + attempt * 2)
    return code, False

t0 = time.time()
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = [ex.submit(fetch, c) for c in codes]
    done = 0
    for f in as_completed(futs):
        code, ok = f.result()
        done += 1
        if not ok: fails.append(code)
        if done % 50 == 0:
            print(f"progress {done}/{len(codes)} elapsed {time.time()-t0:.0f}s fails={len(fails)}", flush=True)
print(f"fetch done {time.time()-t0:.0f}s fails={fails}", flush=True)

# ---------- 3. 重建逐日浮盈亏 ----------
closes = {}
for code in codes:
    fp = os.path.join(CACHE, code + ".csv")
    if os.path.exists(fp) and os.path.getsize(fp) > 200:
        df = pd.read_csv(fp, dtype={"date": str})
        closes[code] = dict(zip(df["date"].str.replace("-", ""), df["close"].astype(float)))
cal = sorted(set(d for m in closes.values() for d in m))
didx = {d: i for i, d in enumerate(cal)}

results = []  # tag, code, name, buy, sell, pct_log, hold, underwater, above, first_pos, n_bars, entry_px
for tag, c, nm, bd, sd, pct, att in trades:
    cl = closes.get(c)
    if not cl: continue
    # 买入日入场价: 买入当日(或之前最近)qfq收盘
    dates_c = [d for d in cl if bd <= d <= sd]
    if not dates_c: continue
    pre = [d for d in cl if d <= bd]
    if not pre: continue
    entry = cl[max(pre)]  # 买入日收盘(qfq)
    bars = [(d, cl[d]) for d in dates_c]
    underwater = sum(1 for d, p in bars if p < entry * 0.999)  # 容忍0.1%滑点佣金
    above = sum(1 for d, p in bars if p >= entry * 0.999)
    fp = None
    for d, p in bars:
        if p >= entry * 1.001: fp = didx[d] - didx[max(pre)]; break
    hold = didx[sd] - didx[max(pre)]
    results.append(dict(tag=tag, code=c, name=nm, buy=bd, sell=sd, pct=pct,
                        hold=hold, uw=underwater, ab=above, fp=fp, nbars=len(bars)))

L = []; w = L.append
w(f"真实行情(qfq)重建逐日浮盈亏 | 交易 {len(results)}/{len(trades)} 笔, 股票 {len(codes)} 只, 拉取失败 {len(fails)}")
for tag in LOGS:
    sub = [r for r in results if r["tag"] == tag]
    los = [r for r in sub if r["pct"] <= 0]
    win = [r for r in sub if r["pct"] > 0]
    w("="*74)
    w(f"【{tag}】亏损单 {len(los)} 盈利单 {len(win)}")
    def dist(vals, label):
        vals = sorted(vals); n = len(vals)
        w(f"  {label:<16} n={n:>3} 均值{sum(vals)/n:>6.1f} 中位{vals[n//2]:>4} p25={vals[n//4]:>3} "
          f"p75={vals[n*3//4]:>3} p90={vals[int(n*.9)]:>3} max={vals[-1]}")
    w(">> 亏损单水下天数(收盘<成本, 含滑点容忍):")
    dist([r["uw"] for r in los], "水下交易日")
    dist([r["hold"] for r in los], "持有交易日")
    dist([r["uw"]/max(r["hold"],1)*100 for r in los], "水下占比%")
    w("  直方图:")
    n = len(los)
    for lo, hi, lab in [(0,2,"0-2天"), (3,5,"3-5天"), (6,10,"6-10天"), (11,20,"11-20天"),
                        (21,40,"21-40天"), (41,999,"40天以上")]:
        s2 = [r for r in los if lo <= r["uw"] <= hi]
        if s2:
            w(f"    {lab:<9}{len(s2):>4}笔 ({len(s2)/n*100:4.1f}%) 平均终亏{sum(r['pct'] for r in s2)/len(s2):+5.1f}%  "
              + "#" * max(1, int(len(s2)/n*50)))
    w("  亏损单持有期内最大浮亏深度(qfq):")
    deeps = []
    for r in los:
        cl = closes[r["code"]]; pre = [d for d in cl if d <= r["buy"]]
        if not pre: continue
        entry = cl[max(pre)]
        ps = [cl[d] for d in cl if r["buy"] <= d <= r["sell"]]
        if ps and entry > 0:
            deeps.append((min(ps)/entry - 1) * 100)
    if deeps:
        deeps_s = sorted(deeps); m = len(deeps_s)
        w(f"    n={m} 中位{deeps_s[m//2]:.1f}% p25={deeps_s[m//4]:.1f}% 最深单{deeps_s[0]:.1f}%")
    w("")
    w(">> 盈利单转正用时(修正版, 精确):")
    fps = [r["fp"] for r in win if r["fp"] is not None]
    never = sum(1 for r in win if r["fp"] is None)
    if fps:
        fps_s = sorted(fps); m = len(fps_s)
        w(f"  n={len(win)} 从未转正(收盘口径) {never} 笔; 转正用时: 均值{sum(fps)/m:.1f} 中位{fps_s[m//2]} "
          f"p75={fps_s[m*3//4]} p90={fps_s[int(m*.9)]} max={fps_s[-1]}")
    for lab, cond in [("小盈0-10%", lambda p: 0 < p < 10), ("中盈10-50%", lambda p: 10 <= p < 50),
                      ("大盈>=50%", lambda p: p >= 50)]:
        s2 = [r["fp"] for r in win if cond(r["pct"]) and r["fp"] is not None]
        if s2:
            s2s = sorted(s2); m2 = len(s2s)
            w(f"  {lab:<10} n={len([r for r in win if cond(r['pct'])]):>3} 转正: 均值{sum(s2)/m2:.1f} 中位{s2s[m2//2]}")
    w(">> 对照: 亏损单中'收盘从未浮盈'的比例:")
    nevl = sum(1 for r in los if r["fp"] is None)
    w(f"  {nevl}/{len(los)} ({nevl/len(los)*100:.0f}%) 买入后收盘价从未回到成本上方")
io.open(OUT, "w", encoding="utf-8").write("\n".join(L))
json.dump(results, io.open(OUT.replace(".txt", ".json"), "w", encoding="utf-8"))
print("OK", flush=True)
