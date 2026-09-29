# -*- coding: utf-8 -*-
"""
涨停复盘看板生成器 (limit_up_review.py)
========================================
数据源（优先级）：
  1. 同花顺问财 (pywencai)  —— 免费，需 WENCAI_COOKIE；自带「涨停原因类别」列，最适合涨停原因分析。
  2. 同花顺 iFinD (ifind-finance-data) —— 付费，需 MCP 密钥；作为备选（见 SKILL.md 说明）。

功能：
  - 自动计算「上一交易日」（遇周末/节假日自动回退到最近一个交易日）。
  - 获取该交易日涨停股票，剔除创业板(300/301)、科创板(688)、京市(8/4) 开头股票。
  - 对每只涨停股分类涨停原因：题材热点 / 政策利好 / 业绩预增 / 资金驱动 / 并购重组 / 新股次新 / 其他。
  - 生成单个响应式 HTML 看板（卡片 + 汇总统计），手机端可读。

用法：
  python limit_up_review.py                 # 上一交易日，问财实时数据
  python limit_up_review.py --demo          # 使用内置样例数据（无需 cookie，用于预览布局）
  python limit_up_review.py --date 2026-08-27
  python limit_up_review.py --output result.html
  python limit_up_review.py --cookie-env WENCAI_COOKIE
"""

import argparse
import datetime
import html
import os
import sys

# ---------------------------------------------------------------------------
# 1. 配置：剔除板块前缀 & 原因分类规则
# ---------------------------------------------------------------------------
# 剔除：创业板 300/301（均 30 开头）、科创板 688、京市（北交所）8 / 4 开头
EXCLUDE_PREFIXES = ("30", "688", "8", "4")

# 原因分类：按优先级匹配（命中即归类，保留原始原因文本展示）
CATEGORY_RULES = [
    ("并购重组", ["重组", "并购", "借壳", "资产注入", "股权", "要约", "定增"]),
    ("新股次新", ["新股", "次新", "上市"]),
    ("业绩预增", ["业绩", "预增", "扭亏", "净利", "营收", "一季报", "中报", "三季报",
                "年报", "高送转", "分红", "一季", "半年报", "季报"]),
    ("政策利好", ["政策", "利好", "规划", "扶持", "补贴", "国务院", "发改委", "工信部",
                "央行", "证监会", "改革", "试点", "方案", "会议", "纲要"]),
    ("资金驱动", ["主力", "净流入", "龙虎榜", "机构", "游资", "北向", "融资", "资金"]),
]
DEFAULT_CATEGORY = "题材热点"

# 分类配色（浅色主题，移动端友好）
CATEGORY_COLORS = {
    "题材热点": "#2563eb",
    "政策利好": "#16a34a",
    "业绩预增": "#d97706",
    "资金驱动": "#db2777",
    "并购重组": "#7c3aed",
    "新股次新": "#0891b2",
    "其他":     "#64748b",
}

# 问财返回列 -> 规范字段名（关键词模糊匹配，兼容列名微调）
COLUMN_ALIASES = {
    "code":       ["股票代码"],
    "name":       ["股票简称"],
    "price":      ["最新价", "现价"],
    "pct":        ["涨跌幅"],
    "limit_price":["涨停价"],
    "reason":     ["涨停原因类别", "涨停原因", "涨停原因类型"],
    "industry":   ["所属行业", "行业"],
    "concept":    ["所属概念", "概念"],
    "fd_amount":  ["涨停封单额", "封单额"],
    "fd_count":   ["涨停封单量", "封单量"],
    "open_times": ["涨停开板次数", "开板次数"],
    "first_time": ["首次涨停时间"],
    "last_time":  ["最后涨停时间", "最终涨停时间"],
    "limit_type": ["涨停类型"],
    "days_boards":["几天几板", "连板天数"],
    "turnover":   ["换手率", "成交额"],
    "total_mv":   ["总市值"],
    "float_mv":   ["流通市值"],
}


# ---------------------------------------------------------------------------
# 2. 交易日计算
# ---------------------------------------------------------------------------
def previous_trading_day(from_date=None):
    """返回 from_date 之前最近的一个非周末日期（节假日由查询回退兜底）。"""
    d = from_date or datetime.date.today()
    d = d - datetime.timedelta(days=1)
    while d.weekday() >= 5:  # 5=周六 6=周日
        d -= datetime.timedelta(days=1)
    return d


def _skip_weekend(d):
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d


# ---------------------------------------------------------------------------
# 3. 数据获取（问财）
# ---------------------------------------------------------------------------
def _load_cookie(env_name):
    cookie = os.environ.get(env_name, "")
    if cookie:
        return cookie
    path = os.path.expanduser("~/.wencai_cookie")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def fetch_limit_up(target_date, cookie, max_back=12):
    """
    用问财查询 target_date 的涨停股票，自动跳过无数据的非交易日。
    返回 (DataFrame, 实际使用的交易日 date)。无 cookie 或全失败返回 (None, target_date)。
    """
    import pywencai  # 延迟导入，demo 模式无需依赖

    d = target_date
    last_err = None
    for _ in range(max_back):
        q = "%d年%d月%d日涨停" % (d.year, d.month, d.day)
        try:
            df = pywencai.get(
                query=q, cookie=cookie, no_detail=True,
                perpage=100, loop=True, retry=3, sleep=1,
            )
        except Exception as e:  # noqa: BLE001
            last_err = e
            df = None
        if df is not None and not getattr(df, "empty", True):
            return df, d
        d = _skip_weekend(d - datetime.timedelta(days=1))
    if last_err:
        sys.stderr.write("[warn] 问财查询异常: %s\n" % last_err)
    return None, target_date


def map_columns(df):
    found = {}
    for canon, aliases in COLUMN_ALIASES.items():
        for a in aliases:
            if a in df.columns:
                found[canon] = a
                break
    return found


# ---------------------------------------------------------------------------
# 4. 过滤 & 分类
# ---------------------------------------------------------------------------
def is_excluded(code):
    code = str(code).strip()
    return code[:3] in EXCLUDE_PREFIXES or code[:2] in EXCLUDE_PREFIXES or code[0] in EXCLUDE_PREFIXES


def classify(reason, industry="", concept=""):
    text = "%s %s %s" % (reason or "", industry or "", concept or "")
    for cat, kws in CATEGORY_RULES:
        for kw in kws:
            if kw in text:
                return cat
    return DEFAULT_CATEGORY


def _to_float(v):
    try:
        if v is None:
            return 0.0
        return float(str(v).replace(",", "").replace("%", "").strip())
    except Exception:  # noqa: BLE001
        return 0.0


def _fmt_money(v):
    """封单额等：自动转换为 亿 / 万。"""
    x = _to_float(v)
    if x >= 1e8:
        return "%.2f亿" % (x / 1e8)
    if x >= 1e4:
        return "%.1f万" % (x / 1e4)
    if x == 0:
        return "-"
    return "%.0f" % x


def normalize_rows(df, colmap):
    rows = []
    for _, r in df.iterrows():
        def g(k):
            val = r[colmap[k]] if k in colmap else ""
            if hasattr(val, "iloc"):  # 容错：极少数情况返回的是单列 Series
                try:
                    return val.iloc[0]
                except Exception:  # noqa: BLE001
                    return ""
            return val
        code = str(g("code")).strip()
        if not code or is_excluded(code):
            continue
        reason = str(g("reason") or "")
        industry = str(g("industry") or "")
        concept = str(g("concept") or "")
        cat = classify(reason, industry, concept)
        rows.append({
            "code": code,
            "name": str(g("name") or ""),
            "price": _to_float(g("price")),
            "pct": _to_float(g("pct")),
            "limit_price": _to_float(g("limit_price")),
            "reason": reason,
            "industry": industry,
            "concept": concept,
            "fd_amount": _fmt_money(g("fd_amount")),
            "open_times": str(g("open_times") or "-"),
            "first_time": str(g("first_time") or "-"),
            "last_time": str(g("last_time") or "-"),
            "limit_type": str(g("limit_type") or "-"),
            "days_boards": str(g("days_boards") or "-"),
            "category": cat,
        })
    return rows


def build_stats(rows):
    by_cat = {}
    by_industry = {}
    for r in rows:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
        ind = r["industry"] or "未知"
        by_industry[ind] = by_industry.get(ind, 0) + 1
    top_industries = sorted(by_industry.items(), key=lambda x: -x[1])[:8]
    return {
        "total": len(rows),
        "by_cat": by_cat,
        "top_industries": top_industries,
    }


# ---------------------------------------------------------------------------
# 5. HTML 生成（响应式 / 移动端友好）
# ---------------------------------------------------------------------------
CSS = """
:root{
  --bg:#f5f7fa; --card:#ffffff; --ink:#1f2937; --muted:#6b7280;
  --line:#e5e7eb; --accent:#2563eb; --up:#dc2626;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
  background:var(--bg);color:var(--ink);line-height:1.5;font-size:14px}
.wrap{max-width:980px;margin:0 auto;padding:16px}
header.top{background:linear-gradient(135deg,#1e3a8a,#2563eb);color:#fff;border-radius:14px;
  padding:18px 18px;box-shadow:0 4px 14px rgba(30,58,138,.18)}
header.top h1{margin:0 0 6px;font-size:20px}
header.top .meta{opacity:.92;font-size:13px}
header.top .badge{display:inline-block;background:rgba(255,255,255,.18);border-radius:8px;
  padding:2px 8px;margin-right:6px;margin-top:6px;font-size:12px}
.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0}
.summary .s{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:12px;text-align:center}
.summary .s .n{font-size:22px;font-weight:700;color:var(--accent)}
.summary .s .l{font-size:12px;color:var(--muted);margin-top:2px}
.section{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:14px;margin-bottom:14px}
.section h2{margin:0 0 10px;font-size:16px;display:flex;align-items:center;gap:8px}
.section h2 .dot{width:10px;height:10px;border-radius:50%}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.filters button{border:1px solid var(--line);background:#fff;color:var(--ink);
  border-radius:20px;padding:6px 12px;font-size:13px;cursor:pointer}
.filters button.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.catbar{display:flex;flex-direction:column;gap:8px;margin-bottom:6px}
.catrow{display:flex;align-items:center;gap:10px;font-size:13px}
.catrow .name{width:78px;color:var(--muted);flex:none}
.catrow .track{flex:1;background:#eef2f7;border-radius:8px;height:18px;overflow:hidden}
.catrow .fill{height:100%;border-radius:8px}
.catrow .cnt{width:34px;text-align:right;flex:none;font-weight:600}
.cards{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;
  box-shadow:0 1px 3px rgba(0,0,0,.04)}
.card .hd{display:flex;justify-content:space-between;align-items:baseline;gap:6px}
.card .nm{font-weight:700;font-size:15px}
.card .cd{color:var(--muted);font-size:12px}
.card .pp{text-align:right}
.card .pp .pr{font-size:16px;font-weight:700;color:var(--up)}
.card .pp .pc{font-size:12px;color:var(--up)}
.tag{display:inline-block;border-radius:6px;color:#fff;font-size:11px;padding:1px 7px;margin-top:6px}
.card .row2{display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px 12px;
  margin-top:8px;font-size:12px;color:var(--muted)}
.card .rs{margin-top:8px;font-size:12px;background:#f1f5f9;border-radius:8px;padding:6px 8px;color:#334155}
.card .rs b{color:var(--ink)}
.card .ft{margin-top:6px;font-size:11px;color:var(--muted)}
footer{color:var(--muted);font-size:12px;text-align:center;padding:6px 0 24px}
@media (max-width:600px){
  .summary{grid-template-columns:repeat(2,1fr)}
  .cards{grid-template-columns:1fr}
  header.top h1{font-size:18px}
}
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>涨停复盘看板 - {date}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <h1>📈 涨停复盘看板</h1>
    <div class="meta">交易日：<b>{date}</b>（上个交易日）　共 <b>{total}</b> 只主板涨停</div>
    <div>
      <span class="badge">已剔除：创业板300/301</span>
      <span class="badge">科创板688</span>
      <span class="badge">京市8/4</span>
    </div>
  </header>

  <div class="summary">
    <div class="s"><div class="n">{total}</div><div class="l">涨停总数(主板)</div></div>
    <div class="s"><div class="n">{cat_n}</div><div class="l">原因分类数</div></div>
    <div class="s"><div class="n">{top_cat}</div><div class="l">最多原因分类</div></div>
    <div class="s"><div class="n">{top_ind}</div><div class="l">最多涨停板块</div></div>
  </div>

  <div class="section">
    <h2><span class="dot" style="background:var(--accent)"></span>涨停原因分布</h2>
    <div class="catbar">{catbars}</div>
  </div>

  <div class="section">
    <h2><span class="dot" style="background:#16a34a"></span>涨停板块 TOP{ind_n}</h2>
    <div class="catbar">{indbars}</div>
  </div>

  <div class="section">
    <h2><span class="dot" style="background:#d97706"></span>涨停股票明细</h2>
    <div class="filters" id="filters">{filter_btns}</div>
    <div class="cards" id="cards">{cards}</div>
  </div>

  <footer>数据来源：同花顺问财（iFinD 备选）　|　生成时间：{gen}　|　本看板仅供复盘参考，不构成投资建议</footer>
</div>
<script>
var DATA = {json};
function render(cat){
  var box=document.getElementById('cards'); box.innerHTML='';
  DATA.filter(function(r){return cat==='全部'||r.category===cat;})
    .forEach(function(r){
      var el=document.createElement('div'); el.className='card';
      el.innerHTML=
        '<div class=\"hd\"><div><span class=\"nm\">'+r.name+'</span> '+
        '<span class=\"cd\">'+r.code+'</span></div>'+
        '<div class=\"pp\"><div class=\"pr\">'+r.price.toFixed(2)+'</div>'+
        '<div class=\"pc\">+'+r.pct.toFixed(2)+'%</div></div></div>'+
        '<span class=\"tag\" style=\"background:'+r.color+'\">'+r.category+'</span>'+
        '<div class=\"row2\"><span>行业：'+r.industry+'</span>'+
        '<span>'+r.days_boards+'</span></div>'+
        '<div class=\"row2\"><span>封单：'+r.fd_amount+'</span>'+
        '<span>首板：'+r.first_time+'</span></div>'+
        (r.reason? '<div class=\"rs\"><b>涨停原因：</b>'+r.reason+'</div>':'')+
        '<div class=\"ft\">涨停价 '+r.limit_price.toFixed(2)+'　开板 '+r.open_times+' 次</div>';
      box.appendChild(el);
    });
}
document.getElementById('filters').addEventListener('click',function(e){
  if(e.target.tagName!=='BUTTON')return;
  document.querySelectorAll('#filters button').forEach(function(b){b.className='';});
  e.target.className='active'; render(e.target.dataset.cat);
});
render('全部');
</script>
</body>
</html>
"""


def generate_html(rows, date_label, output):
    stats = build_stats(rows)
    max_cat = max(stats["by_cat"].values()) if stats["by_cat"] else 1
    max_ind = max([c for _, c in stats["top_industries"]] or [1])

    # 分类柱状
    catbars = []
    for cat, cnt in sorted(stats["by_cat"].items(), key=lambda x: -x[1]):
        color = CATEGORY_COLORS.get(cat, "#64748b")
        pct = int(round(cnt / max_cat * 100))
        catbars.append(
            '<div class="catrow"><div class="name">%s</div>'
            '<div class="track"><div class="fill" style="width:%d%%;background:%s"></div></div>'
            '<div class="cnt">%d</div></div>' % (cat, pct, color, cnt))
    catbars = "".join(catbars) if catbars else '<div class="name">无数据</div>'

    # 板块柱状
    indbars = []
    for ind, cnt in stats["top_industries"]:
        pct = int(round(cnt / max_ind * 100))
        indbars.append(
            '<div class="catrow"><div class="name">%s</div>'
            '<div class="track"><div class="fill" style="width:%d%%;background:#0ea5e9"></div></div>'
            '<div class="cnt">%d</div></div>' % (html.escape(ind), pct, cnt))
    indbars = "".join(indbars) if indbars else '<div class="name">无数据</div>'

    # 明细 JSON（供前端渲染）
    import json
    js_rows = []
    for r in rows:
        js_rows.append({
            "code": r["code"], "name": html.escape(r["name"]),
            "price": r["price"], "pct": r["pct"], "limit_price": r["limit_price"],
            "industry": html.escape(r["industry"] or "-"),
            "reason": html.escape(r["reason"] or ""),
            "fd_amount": html.escape(r["fd_amount"]),
            "first_time": html.escape(r["first_time"]),
            "open_times": html.escape(r["open_times"]),
            "days_boards": html.escape(r["days_boards"]),
            "category": r["category"], "color": CATEGORY_COLORS.get(r["category"], "#64748b"),
        })
    json_str = json.dumps(js_rows, ensure_ascii=False)

    # 过滤按钮
    cats = ["全部"] + [c for c, _ in sorted(stats["by_cat"].items(), key=lambda x: -x[1])]
    filter_btns = "".join(
        '<button data-cat="%s"%s>%s</button>' % (c, ' class="active"' if c == "全部" else "",
                                                  c if c != "全部" else "全部(%d)" % len(rows))
        for c in cats)

    top_cat = max(stats["by_cat"].items(), key=lambda x: x[1])[0] if stats["by_cat"] else "-"
    top_ind = stats["top_industries"][0][0] if stats["top_industries"] else "-"

    # 用 replace 注入（避免 .format 解析脚本中的字面大括号）
    out = TEMPLATE
    out = out.replace("{css}", CSS)
    out = out.replace("{date}", date_label)
    out = out.replace("{total}", str(stats["total"]))
    out = out.replace("{cat_n}", str(len(stats["by_cat"])))
    out = out.replace("{top_cat}", html.escape(top_cat))
    out = out.replace("{top_ind}", html.escape(top_ind))
    out = out.replace("{catbars}", catbars)
    out = out.replace("{ind_n}", str(len(stats["top_industries"])))
    out = out.replace("{indbars}", indbars)
    out = out.replace("{filter_btns}", filter_btns)
    out = out.replace("{cards}", "")
    out = out.replace("{json}", json_str)
    out = out.replace("{gen}", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    with open(output, "w", encoding="utf-8") as f:
        f.write(out)
    return output, stats


# ---------------------------------------------------------------------------
# 6. 样例数据（demo，无需 cookie）
# ---------------------------------------------------------------------------
def demo_rows():
    raw = [
        ("600123", "华能新材", 12.34, 10.04, "国企改革+电力", "电力", "国企改革", "1.20亿", "0", "09:31", "首板"),
        ("000625", "长安智造", 18.90, 10.02, "新能源汽车+华为概念", "汽车整车", "华为汽车", "2.45亿", "1", "09:45", "2连板"),
        ("601288", "农银能源", 7.56, 10.01, "光伏补贴政策利好", "电力设备", "光伏", "0.88亿", "0", "10:02", "首板"),
        ("600519", "黔茅股份", 1680.0, 10.00, "半年报业绩预增+高分红", "白酒", "业绩", "3.10亿", "0", "09:35", "首板"),
        ("000001", "平安银行", 11.22, 9.99, "主力资金净流入+银行", "银行", "金融", "1.65亿", "2", "11:20", "首板"),
        ("603019", "中科曙光", 45.67, 10.00, "国产替代+算力", "计算机设备", "信创", "2.01亿", "0", "09:40", "3连板"),
        ("601318", "中国平安", 48.90, 10.00, "保险新政利好", "保险", "金融", "1.10亿", "0", "09:50", "首板"),
        ("600276", "恒瑞医药", 52.30, 10.01, "创新药+并购重组预期", "化学制药", "创新药", "1.88亿", "1", "10:15", "首板"),
        ("000333", "美的集团", 65.40, 10.00, "家电以旧换新政策", "白色家电", "消费", "2.30亿", "0", "09:38", "首板"),
        ("601857", "中国石油", 9.80, 9.98, "油气提价+央企改革", "石油石化", "中字头", "0.95亿", "0", "10:30", "首板"),
        ("003816", "中国广核", 4.12, 10.03, "核电核准开工", "电力", "中字头", "0.70亿", "0", "09:42", "首板"),
        ("600900", "长江电力", 28.50, 10.00, "业绩预增+高股息", "电力", "水电", "1.40亿", "0", "09:33", "首板"),
        ("000100", "TCL科技", 4.56, 10.02, "面板涨价+半导体", "光学光电子", "面板", "1.75亿", "1", "10:05", "首板"),
        ("601628", "中国人寿", 36.70, 9.99, "险资举牌+资金驱动", "保险", "金融", "1.20亿", "0", "11:00", "首板"),
        ("600030", "中信证券", 22.10, 10.00, "券商并购重组预期", "证券", "金融", "2.60亿", "0", "09:55", "首板"),
        ("000651", "格力电器", 39.80, 10.01, "业绩预增+分红", "白色家电", "消费", "1.95亿", "0", "09:36", "首板"),
    ]
    rows = []
    for code, name, price, pct, reason, ind, concept, fd, ot, ft, db in raw:
        rows.append({
            "code": code, "name": name, "price": price, "pct": pct,
            "limit_price": round(price / (1 + pct / 100), 2),
            "reason": reason, "industry": ind, "concept": concept,
            "fd_amount": fd, "open_times": ot, "first_time": ft,
            "last_time": "-", "limit_type": "-", "days_boards": db,
            "category": classify(reason, ind, concept),
        })
    return rows


# ---------------------------------------------------------------------------
# 7. 主流程
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="涨停复盘看板生成器")
    ap.add_argument("--date", help="指定交易日 YYYY-MM-DD（默认=上一交易日）")
    ap.add_argument("--output", default=None, help="输出 HTML 路径")
    ap.add_argument("--demo", action="store_true", help="使用内置样例数据（无需 cookie）")
    ap.add_argument("--cookie-env", default="WENCAI_COOKIE", help="问财 cookie 环境变量名")
    args = ap.parse_args()

    if args.date:
        y, m, d = (int(x) for x in args.date.split("-"))
        target = datetime.date(y, m, d)
    else:
        target = previous_trading_day()

    date_label = target.strftime("%Y-%m-%d")

    if args.demo:
        rows = demo_rows()
        print("[demo] 使用样例数据，共 %d 条" % len(rows))
    else:
        cookie = _load_cookie(args.cookie_env)
        if not cookie:
            sys.stderr.write("未找到问财 Cookie（环境变量 %s 或 ~/.wencai_cookie）。\n"
                             "请配置后重试；或加 --demo 预览布局。\n" % args.cookie_env)
            sys.exit(2)
        df, used = fetch_limit_up(target, cookie)
        if df is None or getattr(df, "empty", True):
            sys.stderr.write("问财查询无结果，可能该日非交易日或 cookie 失效。\n")
            sys.exit(3)
        colmap = map_columns(df)
        if "code" not in colmap or "name" not in colmap:
            sys.stderr.write("问财返回缺少必要列，实际列名：%s\n" % list(df.columns))
            sys.exit(4)
        rows = normalize_rows(df, colmap)
        date_label = used.strftime("%Y-%m-%d")
        print("[live] 实际交易日 %s，过滤后 %d 只主板涨停" % (date_label, len(rows)))

    if not rows:
        sys.stderr.write("过滤后无符合条件股票（主板涨停为空）。\n")
        sys.exit(5)

    output = args.output or ("涨停复盘_%s.html" % date_label.replace("-", ""))
    path, stats = generate_html(rows, date_label, output)
    print("已生成看板：%s" % os.path.abspath(path))
    print("涨停总数(主板)：%d　分类：%s" % (stats["total"], stats["by_cat"]))


if __name__ == "__main__":
    main()
