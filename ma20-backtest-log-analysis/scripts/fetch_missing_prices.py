# -*- coding: utf-8 -*-
"""补齐 v25 日志中 price_cache 缺失个股的 qfq 日线"""
import re, io, os, time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import akshare as ak

BASE = r"D:\WorkSpace\Myrepo\quant\MA20 stratedgy"
CACHE = os.path.join(BASE, "price_cache")
LOG = os.path.join(BASE, "csi1000_backtest_log_20260929_225032.txt")
os.makedirs(CACHE, exist_ok=True)

codes = set()
for ln in io.open(LOG, encoding="utf-8", errors="replace"):
    m = re.search(r"\[(?:买入|卖出)\] (\d{6}\.[A-Z]{2}) ", ln)
    if m: codes.add(m.group(1))

def to_tx(c):
    n, mkt = c.split(".")
    return ("sh" if mkt == "SH" else "sz") + n

todo = [c for c in sorted(codes) if not os.path.exists(os.path.join(CACHE, c + ".csv"))]
print(f"日志共 {len(codes)} 只, 缺失 {len(todo)} 只, 开始拉取...", flush=True)

def fetch(c):
    try:
        df = ak.stock_zh_a_hist_tx(symbol=to_tx(c), start_date="20191201",
                                   end_date="20240110", adjust="qfq")
        if df is None or len(df) == 0: return c, 0
        df.to_csv(os.path.join(CACHE, c + ".csv"), index=False, encoding="utf-8")
        return c, len(df)
    except Exception as e:
        return c, -1

ok = bad = 0
with ThreadPoolExecutor(max_workers=6) as ex:
    for c, n in ex.map(fetch, todo):
        if n > 0: ok += 1
        else: bad += 1; print("  FAIL", c, flush=True)
print(f"完成: 成功 {ok}, 失败 {bad}", flush=True)
