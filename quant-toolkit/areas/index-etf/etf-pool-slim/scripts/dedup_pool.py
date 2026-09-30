# -*- coding: utf-8 -*-
"""ETF 候选池相关性去重瘦身。

流程：折算校正 -> 相关矩阵 -> 层次聚类分组 -> 组内择优代表 -> 输出对照表。

用法:
  python dedup_pool.py --dir cache3 --spot etf_spot.csv --out slim_out \
      --cut 0.90 --keep 510050,510300,510500,512100,563300

要点:
  * 组内保证 min(两两 r) >= cut（complete linkage），避免 single linkage 的链式误合并。
  * --keep 中的标的互不合并（保持宽基市值梯度），但可被其它标的并入。
"""
import os
import sys
import glob
import argparse
import numpy as np
import pandas as pd

SPLIT_THRESH = 0.25      # |对数日收益| 超过此值视为份额折算/拆分事件
WIN = 750                # 相关性窗口（交易日）
MINP = 400               # 每对最少重叠样本
AMT_WIN = 20             # 日均成交额窗口
TOL = 0.30               # 组内择优的"近似并列"z 单位
RESID_R = 0.90           # 残余高相关披露阈值


# ----------------------------------------------------------------- 1. 读数据
def load_prices(dirpath):
    """读 <code>.csv（含 日期/收盘/成交额，兼容 date/close/amount）。"""
    frames = {}
    for p in sorted(glob.glob(os.path.join(dirpath, "*.csv"))):
        code = os.path.splitext(os.path.basename(p))[0]
        if not code.isdigit():
            continue
        df = pd.read_csv(p)
        cols = list(df.columns)

        def pick(cands, default_i):
            for c in cands:
                if c in cols:
                    return c
            return cols[default_i] if 0 <= default_i < len(cols) else None

        dcol = pick(["日期", "date"], 0)
        ccol = pick(["收盘", "close"], 1)
        acol = pick(["成交额", "amount"], -1)
        if dcol is None or ccol is None:
            continue

        use = [dcol, ccol] + ([acol] if acol and acol not in (dcol, ccol) else [])
        df = df[use].copy()
        df.columns = ["date", "close"] + (["amount"] if len(use) == 3 else [])
        df["date"] = pd.to_datetime(df["date"].astype(str).str[:10], errors="coerce")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        if "amount" in df:
            df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        df = (df.dropna(subset=["date", "close"])
                .query("close > 0")
                .drop_duplicates("date")
                .sort_values("date")
                .set_index("date"))
        if len(df) >= 60:
            frames[code] = df
    return frames


def load_spot(path):
    """读全市场快照，返回 {代码: 规模(亿)}。"""
    if not path or not os.path.isfile(path):
        return {}
    df = pd.read_csv(path, dtype={"代码": str})
    col = next((c for c in ["总市值", "流通市值", "最新份额"] if c in df.columns), None)
    if col is None:
        return {}
    df[col] = pd.to_numeric(df[col], errors="coerce")
    return dict(zip(df["代码"].astype(str).str.zfill(6), df[col] / 1e8))


# ------------------------------------------------- 2. 折算校正 + 3. 相关矩阵
def build_panel(frames):
    rets, amts, splits = {}, {}, []
    for code, df in frames.items():
        c = df["close"].to_numpy(float)
        r = np.zeros(len(c))
        r[1:] = np.diff(np.log(c))
        bad = np.where(np.abs(r) > SPLIT_THRESH)[0]
        for i in bad:
            splits.append({
                "代码": code,
                "日期": str(df.index[i])[:10],
                "前收": round(float(c[i - 1]), 4),
                "收盘": round(float(c[i]), 4),
                "原始日收益": round(float(c[i] / c[i - 1] - 1), 6),
                "处理": "置 0（份额折算/拆分校正）",
            })
        r[bad] = 0.0
        rets[code] = pd.Series(r, index=df.index)
        if "amount" in df:
            amts[code] = float(df["amount"].tail(AMT_WIN).mean())
    return pd.DataFrame(rets), amts, pd.DataFrame(splits)


def corr_matrix(R, win=WIN, minp=MINP):
    c = R.tail(win).corr(min_periods=minp)
    M = c.to_numpy(dtype=float).copy()          # pandas 3.0: .values 只读
    M = np.nan_to_num(M, nan=0.0)
    np.fill_diagonal(M, 1.0)
    return pd.DataFrame(M, index=c.index, columns=c.columns)


# --------------------------------------------------------------- 4. 分组
def group(corr, cut, keep, method="complete"):
    """层次聚类分组。complete linkage 保证组内 min(两两 r) >= cut。"""
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform

    codes = list(corr.columns)
    M = corr.to_numpy(dtype=float).copy()
    M = np.nan_to_num(M, nan=0.0)
    M = (M + M.T) / 2.0
    np.fill_diagonal(M, 1.0)
    np.clip(M, -1.0, 1.0, out=M)
    D = np.sqrt(2.0 * (1.0 - M))
    D = (D + D.T) / 2.0
    np.fill_diagonal(D, 0.0)

    if len(codes) < 2:
        return [codes] if codes else []

    Z = linkage(squareform(D, checks=False), method=method)
    thr = float(np.sqrt(2.0 * (1.0 - cut)))
    lab = fcluster(Z, t=thr, criterion="distance")

    def rv(a, b):
        return float(np.nan_to_num(corr.at[a, b], nan=0.0))

    comps = {}
    for c, l in zip(codes, lab):
        comps.setdefault(l, []).append(c)

    kept = [c for c in keep if c in codes]

    def make(members):
        members = sorted(members)
        sub = corr.loc[members, members].to_numpy(float).copy()
        iu = np.triu_indices(len(members), 1)
        rr = sub[iu] if len(members) > 1 else np.array([])
        return {
            "成员": members,
            "候选数": len(members),
            "组内平均r": float(rr.mean()) if len(rr) else np.nan,
            "组内最小r": float(rr.min()) if len(rr) else np.nan,
            "组内最大r": float(rr.max()) if len(rr) else np.nan,
        }

    groups = []
    for members in comps.values():
        ks = [c for c in members if c in kept]
        if len(ks) <= 1:
            groups.append(make(members))
            continue
        # 同一簇里出现 >=2 个 keep 成员：各自独立成组，
        # 非 keep 成员归入相关性最高的那个 keep（保持市值梯度不塌缩）
        sub = {k: [k] for k in ks}
        for c in members:
            if c in kept:
                continue
            k = max(ks, key=lambda k: (rv(c, k), k))
            sub[k].append(c)
        groups.extend(make(v) for v in sub.values())
    return groups


# ------------------------------------------------------- 5. 组内择优代表
def zs(v):
    v = np.asarray(v, float)
    m = np.isfinite(v)
    out = np.full(v.shape, -9.0)
    if m.sum() >= 2:
        mu, sd = v[m].mean(), v[m].std(ddof=0)
        out[m] = (v[m] - mu) / sd if sd > 0 else 0.0
    return out


def pick_reps(groups, corr, scale, amt):
    """流动性/规模优先；近似并列(±TOL)时选与已选代表相关性最低者。"""
    codes = list(corr.columns)
    sc = zs(np.log(np.array([scale.get(c, np.nan) for c in codes], float)))
    am = zs(np.log(np.array([amt.get(c, np.nan) for c in codes], float)))
    liq = {c: float(np.nan_to_num(0.5 * s + 0.5 * a, nan=-9.0))
           for c, s, a in zip(codes, sc, am)}

    def rv(a, b):
        return float(np.nan_to_num(corr.at[a, b], nan=0.0))

    # 强候选组先选，避免弱组抢占名额
    groups = sorted(groups, key=lambda g: -max(liq.get(c, -9.0) for c in g["成员"]))

    chosen, out = [], []
    for g in groups:
        mem = g["成员"]
        best = max(liq.get(c, -9.0) for c in mem)
        near = [c for c in mem if liq.get(c, -9.0) >= best - TOL]
        if len(near) == 1 or not chosen:
            rep = max(near, key=lambda c: (liq.get(c, -9.0), -int(c)))
        else:
            rep = min(near, key=lambda c: (max(rv(c, o) for o in chosen),
                                           -liq.get(c, -9.0), int(c)))
        chosen.append(rep)
        others = [o for o in chosen if o != rep]
        sv, av = scale.get(rep, np.nan), amt.get(rep, np.nan)
        out.append({
            **g,
            "代表代码": rep,
            "规模(亿)": sv,
            "日均成交额(亿)": av / 1e8 if np.isfinite(av) else np.nan,
            "与池内其他代表最大r": max(rv(rep, o) for o in others) if others else np.nan,
        })
    return out


# ------------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="日线目录，每个标的 <code>.csv")
    ap.add_argument("--spot", default="", help="全市场快照 CSV（含 代码/总市值）")
    ap.add_argument("--out", default="slim_out")
    ap.add_argument("--cut", type=float, default=0.90, help="合并阈值（组内最小 r）")
    ap.add_argument("--keep", default="", help="逗号分隔，强制互不合并的代码")
    ap.add_argument("--linkage", default="complete",
                    choices=["complete", "average", "single"],
                    help="层次聚类方式；complete 最保守（默认）")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    keep = [x.strip().zfill(6) for x in a.keep.split(",") if x.strip()]

    frames = load_prices(a.dir)
    if not frames:
        sys.exit("没有读到任何行情文件，检查 --dir")
    scale = load_spot(a.spot)
    if not scale:
        print("!! 未提供 --spot 规模快照，组内择优退化为'仅按成交额 + 降重叠'")

    R, amt, splits = build_panel(frames)
    corr = corr_matrix(R)
    groups = group(corr, a.cut, keep, method=a.linkage)
    reps = pick_reps(groups, corr, scale, amt)

    reps.sort(key=lambda g: (g["候选数"] == 1,
                             -(g["规模(亿)"] if np.isfinite(g["规模(亿)"]) else 0.0)))
    for i, g in enumerate(reps, 1):
        g["组ID"] = f"G{i:02d}"

    rnd = lambda v, n=3: round(v, n) if np.isfinite(v) else ""

    gdf = pd.DataFrame([{
        "组ID": g["组ID"], "代表代码": g["代表代码"], "候选数": g["候选数"],
        "成员": "、".join(g["成员"]),
        "组内平均r": rnd(g["组内平均r"]),
        "组内最小r": rnd(g["组内最小r"]),
        "组内最大r": rnd(g["组内最大r"]),
        "与池内其他代表最大r": rnd(g["与池内其他代表最大r"]),
        "规模(亿)": rnd(g["规模(亿)"], 2),
        "日均成交额(亿)": rnd(g["日均成交额(亿)"]),
    } for g in reps])

    mrows = []
    for g in reps:
        for c in g["成员"]:
            if c == g["代表代码"]:
                continue
            mrows.append({
                "被合并": c, "并入": g["代表代码"], "组ID": g["组ID"],
                "与代表的相关性r": round(float(np.nan_to_num(corr.at[c, g["代表代码"]], nan=0.0)), 3),
                "规模(亿)": rnd(scale.get(c, np.nan), 2),
                "日均成交额(亿)": rnd(amt.get(c, np.nan) / 1e8 if np.isfinite(amt.get(c, np.nan)) else np.nan),
            })
    mdf = pd.DataFrame(mrows)

    final = [g["代表代码"] for g in reps]
    rrows = []
    for i, x in enumerate(final):
        for y in final[i + 1:]:
            r = float(np.nan_to_num(corr.at[x, y], nan=0.0))
            if r >= RESID_R:
                rrows.append({"a": x, "b": y, "r": round(r, 3),
                              "处理": "待确认（可能刻意保留，也可能需合并）"})
    rdf = pd.DataFrame(rrows)

    gdf.to_csv(os.path.join(a.out, "groups.csv"), index=False, encoding="utf-8-sig")
    mdf.to_csv(os.path.join(a.out, "merged.csv"), index=False, encoding="utf-8-sig")
    rdf.to_csv(os.path.join(a.out, "residual.csv"), index=False, encoding="utf-8-sig")
    splits.to_csv(os.path.join(a.out, "splits.csv"), index=False, encoding="utf-8-sig")
    R.to_csv(os.path.join(a.out, "returns_adj.csv"), encoding="utf-8")

    n0, n1 = len(frames), len(reps)
    print(f"池容量: {n0} -> {n1}  (-{100*(1-n1/n0):.1f}%)")
    print(f"合并组: {sum(1 for g in reps if g['候选数'] > 1)} 个，被合并标的: {len(mdf)} 只")
    print(f"折算事件: {len(splits)}（含历史）  残余 r>={RESID_R}: {len(rdf)} 对")
    print(f"输出目录: {os.path.abspath(a.out)}")


if __name__ == "__main__":
    main()
