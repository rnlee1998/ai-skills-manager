---
name: limit-up-review
version: 1.0.0
description: 复盘股票涨停的技能。自动获取「上一交易日」涨停股票，剔除创业板(300/301)/科创板(688)/京市(8/4) 后，对主板涨停股按题材热点/政策利好/业绩预增/资金驱动/并购重组/新股次新分类，并生成单个响应式 HTML 看板（卡片+汇总统计，手机端可读）。
---

# 涨停复盘看板 (limit-up-review)

一键生成上一交易日「主板涨停股」复盘看板。自动过滤创业板/科创板/京市，归纳涨停原因，输出移动端友好的 HTML。

## 触发条件

当用户要求「复盘涨停」「涨停板分析」「昨天/今日涨停股」「涨停原因汇总」「涨停股看板」等，且本质是对 A 股涨停个股做**复盘、分类、统计与可视化**时，调用本技能。

## 数据来源（优先级）

1. **同花顺问财 (pywencai)** —— 免费，仅需 Cookie；问财「涨停」板块自带「涨停原因类别」列，最契合「原因分类」需求。**默认且首选。**
2. **同花顺 iFinD (ifind-finance-data)** —— 付费，需 MCP 密钥；当问财不可用（无 Cookie / 限流 / 字段缺失）时的备选方案（见文末「iFinD 备选」）。

## 环境准备（问财路径）

1. 安装 Python 依赖（建议在受管 venv 中）：
   ```bash
   <managed_python> -m venv <managed_venv>
   <managed_venv>/bin/pip install pywencai --upgrade
   ```
   pywencai 内部执行 JS，需本机 Node.js v16+（环境已具备）。
2. 获取问财 Cookie：
   - 浏览器登录 https://www.iwencai.com → F12 → Network → 执行任意查询 → 复制发往 `iwencai.com` 请求的 `Cookie` 头。
   - 写入环境变量 `WENCAI_COOKIE`，或写入文件 `~/.wencai_cookie`。**不要硬编码 Cookie 字符串。**

## 执行流程

1. **确定交易日**：脚本自动计算「上一交易日」（跳过周末；若当日无数据会自动向前回退到最近交易日，兼容节假日）。
2. **拉取数据**：用问财查询 `{YYYY}年{M}月{D}日涨停`，`no_detail=True, perpage=100, loop=True`。
3. **过滤**：剔除代码以 `30`(300/301 创业板)、`688`(科创板)、`8`/`4`(京市) 开头的股票，仅留主板及其他符合条件股票。
4. **原因分类**：基于「涨停原因类别 / 所属行业 / 所属概念」文本，按优先级匹配归类为
   `并购重组 > 新股次新 > 业绩预增 > 政策利好 > 资金驱动 > 题材热点(默认)`。原始原因文本保留展示。
5. **生成 HTML**：单文件响应式看板，含汇总卡片、原因分布柱状图、板块 TOP 分布、可按分类筛选的涨停股票卡片。

## 调用方式

脚本位于本技能 `scripts/limit_up_review.py`。在受管 venv 中运行：

```bash
# 上一交易日，问财实时数据（需 WENCAI_COOKIE）
<managed_venv>/bin/python <skill_dir>/scripts/limit_up_review.py

# 指定交易日
<managed_venv>/bin/python <skill_dir>/scripts/limit_up_review.py --date 2026-08-27

# 无 Cookie 时预览布局（内置样例数据，不联网）
<managed_venv>/bin/python <skill_dir>/scripts/limit_up_review.py --demo

# 指定输出路径
<managed_venv>/bin/python <skill_dir>/scripts/limit_up_review.py --output 涨停复盘.html
```

- 输出文件默认命名为 `涨停复盘_YYYYMMDD.html`，位于当前工作目录。
- 生成后用 `present_files` 将 HTML 呈现给用户（内置浏览器预览面板，可直接在手机/桌面查看）。

## 容错与提示

- 未配置 Cookie：脚本退出码 2 并提示配置方法；可改用 `--demo` 先看布局。
- 问财返回空（非交易日/限流）：退出码 3；自动回退逻辑已覆盖多数节假日，仍为空则提示用户。
- 列名缺失：退出码 4，打印实际列名，便于调整 `COLUMN_ALIASES` 映射。
- 批量/高频调用问财建议间隔 ≥ 2 秒，避免被封禁。

## HTML 看板组成（响应式）

- 顶部：交易日、主板涨停总数、已剔除板块提示。
- 汇总卡片：涨停总数、原因分类数、最多原因、最多板块。
- 原因分布：各分类数量柱状图（配色区分）。
- 板块 TOP：涨停股最多的行业分布柱状图。
- 明细卡片：每只股票名称/代码、现价、涨幅、原因标签、行业、几天几板、封单额、首次涨停时间；顶部按钮可按分类筛选。
- `@media (max-width:600px)`：汇总改 2 列、卡片改单列，保证手机可读。

## iFinD 备选方案（无问财 Cookie 时）

若用户具备 iFinD MCP 密钥（写入 `ifind-finance-data/mcp_config.json`），可在 `stock` 服务调用智能选股/涨停相关工具获取涨停列表，再做同样的过滤与分类。若走此路径，请将 `limit_up_review.py` 中 `fetch_limit_up` 替换为 iFinD `call("stock", "stock_selection", {...})` 的返回，并保证输出 DataFrame 含 `COLUMN_ALIASES` 所列字段（中文列名）。其余过滤/分类/HTML 逻辑完全复用。

## 合规

本看板仅用于收盘后复盘与学习，不构成任何投资建议。页面已标注风险提示。
