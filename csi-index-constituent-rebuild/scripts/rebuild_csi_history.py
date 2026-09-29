#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""中证指数历史成分股 —— 端到端重建脚本（可复用）。

改 INDEX_CODE / INDEX_NAME 即可复用到其他中证指数（000300 / 000905 / 000852 / 932000 等）。

管道：
  阶段0  akshare 官方『纳入日期』账本         -> 真实调仓日 + 高置信成分（下界）
  阶段1  东财 RPT_F10_EH_EQUITY 历史总股本    -> _eq_share.pkl
  阶段2  新浪未复权日线收盘价                  -> _sina_px.pkl
  阶段3  一年日均总市值重建                    -> _prod.pkl
  阶段4  三源融合 + 置信度标注                 -> 交付目录

用法（必须用带 akshare/pandas 的 venv）：
  python rebuild_csi_history.py --index 000852 --out D:\\...\\csi1000_history_v2
  python rebuild_csi_history.py --index 000852 --stage 4     # 只重跑融合
"""
import argparse
import io
import os
import pickle
import sys
import time
from collections import defaultdict

import requests

# 代理：本机需要走 http://127.0.0.1:59980；若直连请设为 None
PROXY = os.environ.get("HTTP_PROXY") or None
PROXIES = {"http": PROXY, "https": PROXY} if PROXY else None

EQ_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
SINA_URL = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "CN_MarketData.getKLineData")
EM_HEADERS = {"Referer": "https://data.eastmoney.com/",
              "User-Agent": "Mozilla/5.0"}

# 中证1000 的调仓日在每年 6 月 / 12 月的第二个星期五附近；官方真实日期由账本给出，
# 这里仅作兜底（账本不可用时使用）
FALLBACK_REBALANCE_DATES = [
    "2017-06-12", "2017-12-11", "2018-06-11", "2018-12-17",
    "2019-06-17", "2019-12-16", "2020-06-15", "2020-12-14",
    "2021-06-15", "2021-12-13", "2022-06-13", "2022-12-12",
    "2023-06-12", "2023-12-11", "2024-06-17", "2024-12-16",
    "2025-06-16", "2025-12-15", "2026-06-15",
]

# 东财 RPT_INDEX_TS_COMPONENT 的 TYPE 映射
EM_TYPE = {"000300": "1", "000905": "3", "000852": "7", "932000": "13"}


def qmt_code(c):
    """6 位代码 -> QMT 形式（600519 -> 600519.SH）。"""
    c = str(c).zfill(6)
    if c.startswith(("6", "9")):
        return c + ".SH"
    if c.startswith(("0", "3")):
        return c + ".SZ"
    if c.startswith(("4", "8")):
        return c + ".BJ"
    return c + ".SZ"


# ============================ 阶段 0：官方账本 ============================

def stage0_ledger(log):
    """akshare index_stock_cons 的『纳入日期』账本。

    返回 {symbol: {qmt_code: 纳入日期str}}
    铁律：ledger(T) ⊂ 当前名单；三张表任一时点两两交集 = 0。
    """
    import akshare as ak
    out = {}
    for sym in ("000300", "000905", "000852"):
        try:
            d = ak.index_stock_cons(symbol=sym)
            d["纳入日期"] = d["纳入日期"].astype(str).str.strip()
            out[sym] = {qmt_code(r["品种代码"]): r["纳入日期"]
                        for _, r in d.iterrows()}
            log("stage0 %s -> %d 条" % (sym, len(out[sym])))
        except Exception as e:                                  # noqa: BLE001
            log("stage0 %s FAIL %s %s" % (sym, type(e).__name__, e))
    return out


# ==================== 阶段 1：东财历史总股本（单只查！） ====================

def stage1_equity(codes, cache_path, log, workers=8):
    """东财 RPT_F10_EH_EQUITY -> {code6: [[END_DATE_str, TOTAL_SHARES_float], ...]}

    ⚠️ 该接口只能单只查，`in (...)` 会静默只返回第一只。
    """
    if os.path.exists(cache_path):
        log("stage1 命中缓存 %s" % cache_path)
        return pickle.load(io.open(cache_path, "rb"))

    from concurrent.futures import ThreadPoolExecutor, as_completed
    sess = requests.Session()
    out = {}

    def fetch(code):
        suffix = "SH" if code.startswith(("6", "9")) else "SZ"
        params = {
            "reportName": "RPT_F10_EH_EQUITY",
            "filter": '(SECUCODE="%s.%s")' % (code, suffix),
            "columns": "SECUCODE,SECURITY_CODE,END_DATE,CHANGE_REASON,"
                       "TOTAL_SHARES,LISTED_A_SHARES",
            "pageSize": 200, "pageNumber": 1, "source": "WEB", "client": "WEB",
        }
        try:
            r = sess.get(EQ_URL, params=params, headers=EM_HEADERS,
                         proxies=PROXIES, timeout=20)
            j = r.json()
            rows = (j.get("result") or {}).get("data") or []
            return code, [[str(x["END_DATE"])[:10], float(x["TOTAL_SHARES"] or 0)]
                          for x in rows if x.get("END_DATE")]
        except Exception:                                       # noqa: BLE001
            return code, None

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(fetch, c) for c in codes]
        for i, f in enumerate(as_completed(futs), 1):
            c, rows = f.result()
            if rows:
                out[c] = rows
            if i % 500 == 0:
                log("  stage1 %d/%d  elapsed %.0fs" % (i, len(codes), time.time() - t0))
    log("stage1 完成 %d/%d  %.0fs" % (len(out), len(codes), time.time() - t0))
    pickle.dump(out, io.open(cache_path, "wb"), protocol=4)
    return out


# =================== 阶段 2：新浪未复权日线（主力价格源） ===================

def stage2_prices(codes, cache_path, log, workers=10, datalen=6000):
    """新浪 getKLineData -> {code6: [(yyyymmdd_int, close_float), ...]}

    返回的是**未复权**价，配合当时总股本可避开复权跳空。
    """
    if os.path.exists(cache_path):
        log("stage2 命中缓存 %s" % cache_path)
        return pickle.load(io.open(cache_path, "rb"))

    import json
    from concurrent.futures import ThreadPoolExecutor, as_completed
    sess = requests.Session()
    out = {}

    def fetch(code):
        prefix = "sh" if code.startswith(("6", "9")) else "sz"
        try:
            r = sess.get(SINA_URL, params={
                "symbol": prefix + code, "scale": 240, "ma": "no",
                "datalen": datalen,
            }, proxies=PROXIES, timeout=25)
            arr = json.loads(r.text)
            if not isinstance(arr, list):
                return code, None
            return code, [(int(x["day"].replace("-", "")), float(x["close"]))
                          for x in arr if x.get("close")]
        except Exception:                                       # noqa: BLE001
            return code, None

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(fetch, c) for c in codes]
        for i, f in enumerate(as_completed(futs), 1):
            c, rows = f.result()
            if rows:
                out[c] = rows
            if i % 500 == 0:
                log("  stage2 %d/%d  elapsed %.0fs" % (i, len(codes), time.time() - t0))
    log("stage2 完成 %d/%d  %.0fs" % (len(out), len(codes), time.time() - t0))
    pickle.dump(out, io.open(cache_path, "wb"), protocol=4)
    return out


# =================== 阶段 3：一年日均总市值重建 ===================

def stage3_rebuild(share, px, dates, log, min_days=200):
    """返回 {date: [(code, avg_mcap_yi, rank), ...]}（已剔除前800，长度1000）。

    avg_mcap = mean( 当时总股本 × 未复权收盘价 )，窗口 = 该期前 12 个月。
    min_days=200 近似「上市满一年」。
    """
    import datetime as dt
    rows_by_date = {}
    for D in dates:
        d_end = int(D.replace("-", ""))
        # 前 12 个月
        y, m, dd = (int(x) for x in D.split("-"))
        d_start = int(("%04d%02d%02d" % (y - 1, m, dd)))

        mc, dayn = {}, {}
        for code, prows in px.items():
            srows = share.get(code)
            if not srows or not prows:
                continue
            srows = [(int(r[0].replace("-", "")), float(r[1]))
                     for r in srows if r[0]]
            srows.sort()
            tot, n, si, cur = 0.0, 0, 0, None
            for d, p in prows:
                if d > d_end:
                    break
                while si < len(srows) and srows[si][0] <= d:
                    cur = srows[si][1]
                    si += 1
                if d < d_start or cur is None:
                    continue
                tot += cur * p
                n += 1
            if n:
                mc[code] = tot / n / 1e8        # 亿元
                dayn[code] = n

        mature = {c: v for c, v in mc.items() if dayn.get(c, 0) >= min_days}
        ordered = sorted(mature.items(), key=lambda kv: -kv[1])
        picked = ordered[800:1800]              # 剔除前800近似中证800
        rows_by_date[D] = [(qmt_code(c), v, i + 801)
                           for i, (c, v) in enumerate(picked)]
        log("  stage3 %s 满1年=%d 剔除800 选出=%d"
            % (D, len(mature), len(rows_by_date[D])))
    return rows_by_date


# =================== 阶段 4：三源融合 + 交付 ===================

def stage4_deliver(rows_by_date, ledger, out_dir, log):
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(out_dir, "qmt_sectors_v2"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "ledger_only"), exist_ok=True)

    dates = sorted(rows_by_date)

    def ledger_at(sym, T):
        return set(c for c, d in ledger.get(sym, {}).items() if d <= T)

    long_rows, stats = [], []
    for D in dates:
        l1000 = ledger_at("000852", D)
        l800 = ledger_at("000300", D) | ledger_at("000905", D)
        base = rows_by_date[D]
        confirmed = sum(1 for c, _, _ in base if c in l1000)
        stats.append((D, len(base), len(l1000), confirmed))

        io.open(os.path.join(out_dir, "qmt_sectors_v2",
                             "csi1000_%s.txt" % D.replace("-", "")),
                "w", encoding="utf-8", newline="").write(
                    ",".join(sorted(c for c, _, _ in base)))
        if l1000:
            io.open(os.path.join(out_dir, "ledger_only",
                                 "ledger_%s.txt" % D.replace("-", "")),
                    "w", encoding="utf-8", newline="").write(
                        ",".join(sorted(l1000)))

        for c, mc, rk in base:
            if c in l800:
                ev = "CONFLICT"
            elif c in l1000:
                ev = "official"
            else:
                ev = "model"
            long_rows.append("%s,%s,%s,%d,%.2f,%s"
                             % (D, c.replace(".", ""), c, rk, mc, ev))

    io.open(os.path.join(out_dir, "csi1000_history_v2.csv"),
            "w", encoding="utf-8-sig").write(
                "date,code,qmt_code,rank,avg_mcap_yi,evidence\n" + "\n".join(long_rows))

    # 宽表
    piv = defaultdict(dict)
    for line in long_rows:
        p = line.split(",")
        piv[p[2]][p[0]] = 1
    wl = [",".join(["qmt_code"] + dates)]
    for qc in sorted(piv):
        wl.append(",".join([qc] + ["1" if piv[qc].get(d) else "0" for d in dates]))
    io.open(os.path.join(out_dir, "csi1000_history_v2_wide.csv"),
            "w", encoding="utf-8-sig").write("\n".join(wl))

    log("stage4 交付完成 -> %s (%d 期)" % (out_dir, len(dates)))
    for s in stats:
        log("  %s  base=%d ledger=%d confirmed=%d (%.1f%%)"
            % (s[0], s[1], s[2], s[3], 100.0 * s[3] / max(1, s[1])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="000852")
    ap.add_argument("--out", default="./csi1000_history_v2")
    ap.add_argument("--work", default="./_csi_work")
    ap.add_argument("--stage", type=int, default=0, help="0=全跑；4=只重跑融合")
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    lines = []

    def log(*a):
        s = " ".join(str(x) for x in a)
        lines.append(s)
        print(s)

    led = stage0_ledger(log)
    if led:
        ev = sorted({d for m in led.values() for d in m.values()})
        log("官方真实调仓日共 %d 个：%s ~ %s" % (len(ev), ev[0], ev[-1]))
        dates = [d for d in FALLBACK_REBALANCE_DATES if ev[0] <= d <= ev[-1]] or \
                FALLBACK_REBALANCE_DATES
    else:
        dates = FALLBACK_REBALANCE_DATES

    if args.stage <= 3:
        share_p = os.path.join(args.work, "_eq_share.pkl")
        px_p = os.path.join(args.work, "_sina_px.pkl")
        prod_p = os.path.join(args.work, "_prod.pkl")

        if os.path.exists(prod_p) and args.stage not in (1, 2, 3):
            prod = pickle.load(io.open(prod_p, "rb"))
            rows_by_date = {k: [tuple(x) for x in v] for k, v in prod.items()}
        else:
            import akshare as ak
            codes = [r["代码"] for r in ak.stock_info_a_code_name().to_dict("records")]
            log("全A代码数 = %d" % len(codes))
            share = stage1_equity(codes, share_p, log)
            px = stage2_prices(list(share.keys()), px_p, log)
            rows_by_date = stage3_rebuild(share, px, dates, log)
            pickle.dump(rows_by_date, io.open(prod_p, "wb"), protocol=4)
    else:
        prod = pickle.load(io.open(os.path.join(args.work, "_prod.pkl"), "rb"))
        rows_by_date = {k: [tuple(x) for x in v] for k, v in prod.items()}

    stage4_deliver(rows_by_date, led, args.out, log)
    io.open(os.path.join(args.work, "_rebuild.log"), "w",
            encoding="utf-8").write("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
