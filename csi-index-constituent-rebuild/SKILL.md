---
name: csi-index-constituent-rebuild
description: 重建中证系列指数（中证1000/800/500/300/2000 及中证全指）的**历史成分股**，用于 QMT 等平台的历史回测股票池。当用户提出「QMT 取不到中证1000历史成分股」「要 2017 至今的中证1000成分股」「回测用历史指数成分股」「index constituent history」「成分股前视偏差」等需求时使用。核心方法是用 akshare `index_stock_cons` 的官方『纳入日期』账本获取真实调仓日与高置信成分，用外部数据源（东财历史股本 × 新浪未复权价）做一年日均总市值重建，再融合输出 QMT 板块文件。**但首选是 PTrade `get_index_stocks(index_code, 'YYYYMMDD')` 直接导出真实历史快照（见正文『首选方案』），只有在拿不到 PTrade 时才走本技能的 akshare + 市值重建。**
agent_created: true
---

# 中证指数历史成分股重建

## ★ 首选方案：PTrade 直接导真数据（2026-09-23 实测，先看这节）

**下面「第一步」说的『没有任何免费数据源公开历史成分股快照』，只对**公网**数据源成立。
券商端 PTrade 有真数据 —— 优先走这条路，别再花几小时做重建。**

```python
# 在 PTrade 研究模块（不是回测模块）里跑
get_index_stocks('000852.SS', '20210615')   # → 该日的 1000 只成分股 list
```

**API 口径（三个坑，全踩过）**：
1. `date` 必须是 **`'YYYYMMDD'` 紧凑格式**；**研究模块不传 date 会默认取当前日期**
   —— 传错格式或不传，极可能静默回退成当前名单
2. `get_trade_days(start, end)` 入参却是 **`'YYYY-MM-DD'` 带横杠**格式，两套口径并存
3. 指数代码尾缀必须是 `.SS`；文件只能写在 `get_research_path()` 下；
   **研究沙盒禁用部分标准模块**（`import` 即报「被禁止使用」）→ 路径拼接/二分查找/
   文件大小要手写，其余 try-import 降级

**已验证的事实（131 期实测）**：
- 覆盖 **2018-12-14 ~ 2026-09-15，共 131 期**，每期精确 1000 只；沪深300/中证500 同时可导
- 通过 **6 类独立检验**：三指数零重叠（0/60 违规）/ 科创板数量时间线不可伪造
  （`0→19→41→…→126→122`）/ 公开新闻逐项吻合 / 官方台账**下一个快照 16/16 = 100%** /
  缺口股票 100% 等于下次新增 / 第三方源 100/100 命中
- **唯一特性：快照滞后官方调仓 2~50 天**（数据服务同步延迟）。方向**偏旧** →
  无前视偏差，恰好等于「当时实盘能拿到的最新名单」，回测反而更真实

**已落盘、可直接复用的资产（无需重跑）**：

| 路径 | 内容 |
|---|---|
| `D:\WorkSpace\Myrepo\quant\csi1000_history\ptrade_download_csi1000.py` | 导出脚本（伪造 PTrade 环境 37/37 端到端测试通过） |
| `...\csi1000_halfyear\` | **16 期半年度名单**（长表 + summary + QMT 板块 txt × 16） |
| `...\ptrade_verified\` | 131 期月度快照 + csi300(68期) + csi500(60期) + 滞后对照表 + 131 个单期 txt |
| `...\中证1000历史成分数据验证报告_20260923.md` | 完整验证报告（含误判复盘） |

**归并成半年一期的口径**（中证系列官方调仓本来就是半年一次：
每年 6 月、12 月的第二个星期五的下一交易日，期内偶有 1~3 只的临时调整）：

> 期别边界 = 官方调仓生效日；**每期取该期内「第一个完整覆盖本期官方调仓」的快照**
> （判据 `ledger(T) ⊆ snapshot(S)`，取期内最早的 S）。
> 既准确反映本期调仓（台账覆盖率 100%），又无前视。
> ⚠️ **不要取期内最后一个快照** —— 那是期末名单，用于期初即构成前视。

### 真伪判定：5 步法（判定第三方给的"历史成分股"是否可信）

① 日期形态（真实调仓日是半年频、日期逐年浮动；伪数据是整齐网格）
② 每期只数（真实会有缺额；伪数据恒等于理论值）
③ 换手量分布（真实换手浮动；伪数据出现固定的「整块交换」）
④ 对官方台账覆盖率（**必须 100%**）
⑤ 相似度矩阵 + 时点错位（每期与全部官方台账比对，看它挂在哪个锚点上）

> ⚠️ **第 ④ 步的铁律：只能在双方都有数据的日期上比较。**
> 曾因拿「数据里根本不存在的调仓日」去算覆盖率 → 得 0% → 把**真数据**误判为
> 「当前名单向前平移的伪快照」，删了报告又重写。**日期缺失 ≠ 数据错误。**

## 这个技能解决什么问题

QMT 免费版**取不到中证1000（`000852`）的历史成分股**，`sectorChange.txt` 只有
沪深300/中证500 且冻结在 2017-12-11；`sectorWeightData.txt` 只有当日快照。
直接把 `get_stock_list_in_sector('中证1000')` 用在历史回测里会造成**严重前视偏差**
（拿今天的成分股跑三年前的行情）。

本技能给出经过验证的重建流程与降级策略。

## 第一步：先接受这个前提（省下几小时的试错）

**没有任何免费数据源公开中证系列指数的历史成分股快照。** 已穷举验证：

| 数据源 | 结论 | 细节 |
|---|---|---|
| 中证指数官网 OSS | ✗ | `https://csi-web-dev.oss-cn-shanghai-finance-1-pub.aliyuncs.com/static/html/csindex/public/uploads/file/autofile/cons/000852cons.xls` 只有**当日**快照（约 213 KB） |
| 中证官网 API | ✗ | `https://www.csindex.com.cn/csindex-home/indexInfo/index-basic-info/000852` 可用；`index-feature` 可用；**无成分股历史端点**。`/data-service/sector-change` 只返回板块涨跌 |
| 新浪历史成分股页 | ✗ | `vip.stock.finance.sina.com.cn/corp/go.php/vII_HistoryComponent/indexid/{idx}.phtml` 有纳入/剔除日期，但**只到 2010-07-01，且没有 000852 页面** |
| 东方财富 | ✗ | `RPT_INDEX_TS_COMPONENT` 只有当前（`filter=(TYPE="7")` → 中证1000；TYPE 映射 1=沪深300 / 3=中证500 / 7=中证1000 / 13=中证2000）。HIS 类表返回「报表配置不存在」 |
| QMT `sectorChange.txt` | △ | 只有 `000016.SH` / `000300.SH` / `000905.SH`，**冻结在 2017-12-11** |
| QMT `sectorWeightData.txt` | △ | 有 `SH000852` 当日 1000 只 + 权重，**仅当日快照，且质量差**（见下） |
| **akshare `index_stock_cons`** | **✓ 最有价值** | 见「关键突破口」 |

**实测 QMT 本地 `SH000852` 段质量不佳**：与 akshare 官方名单 Jaccard 仅 30.2%，
与市值重建仅 27.1%，而 akshare 名单与市值重建达 51.8%。**不要拿 QMT 本地那份做回测股票池。**

## 关键突破口：akshare 官方『纳入日期』账本

```python
import akshare as ak          # 需 1.18+，用 factorhub 的 venv 跑
d = ak.index_stock_cons(symbol="000852")   # 中证1000
d = ak.index_stock_cons(symbol="000300")   # 沪深300
d = ak.index_stock_cons(symbol="000905")   # 中证500
# 列：品种代码 / 品种名称 / 纳入日期
```

它返回**当前在册的成分股**，并附带每只股票**最后一次被纳入的日期**——而这个日期
是**官方真实调仓日**（中证1000 自 2014-10-17 起共 38 个）。

三条已验证的铁律（务必理解，决定能做什么不能做什么）：

1. **`ledger(T) ⊂ 当前名单` 恒成立**，且 `ledger(T)` 规模从 44（2014）单调升到 772（2026）。
   → 这是**下界，不是全集**。规模小不等于"当年成分股少"，而是**早期在名单里、后来被剔除的
   股票拿不到**（接口按当前名单逐股回溯，已剔除的不返回）。
2. **`ledger300(T)`、`ledger500(T)`、`ledger1000(T)` 在任意时点两两交集恒为 0**
   → 三张表来自同一个中证指数族（中证800 = 沪深300 ∪ 中证500；中证1000 = 中证全指 − 中证800），
   **可以做集合运算**。
3. **`ledger800(T) ∩ 当前1000 = 0`（所有 T）** → 账本无跨层污染。

**能可靠回答的问题**：「这只股票在 T 时点**肯定**在名单里吗」→ 答「在」可信（`纳入日 ≤ T`）。
**不能可靠回答**：「T 时点名单里**没有**这只」→ 不可信。

## 重建方法（全集）

只有市值重建能给全集：

```
一年日均总市值 = mean( 历史总股本 × 未复权收盘价 )   # 对该期前 12 个月
→ 剔除中证800（前 800）→ 按市值降序取前 1000
```

两个数据源（均在 `scripts/` 中有可复用实现）：

- **历史总股本**：东财 `RPT_F10_EH_EQUITY`
  `https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_F10_EH_EQUITY&filter=(SECUCODE="600519.SH")&columns=SECUCODE,SECURITY_CODE,END_DATE,CHANGE_REASON,TOTAL_SHARES,LISTED_A_SHARES`
  → 返回该股**每一次股本变动的日期与总股本**（茅台可回溯到 2001 上市前）。
  **只能单只查**——`in (...)` 语法会静默只返回第一只，必须逐股循环。
- **未复权日线收盘价**：新浪
  `https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600519&scale=240&ma=no&datalen=6000`
  → **原始未复权** OHLCV（`datalen=6000` 可到 IPO），约 0.4 s/股，走代理正常。
  用未复权价 × 当时总股本，天然避开复权跳空。

**做中证800剔除时的降级顺序**（中证官方用「自由流通市值 + 行业均衡」，排名跨度可达 1→1721，
不是简单的 1→800，所以只能用近似）：
1. 2017-12-11 及之前 → QMT `sectorChange.txt` 的精确 300+500（事件重放）
2. 最新一期 → 东财当前官方 300+500 名单
3. 其余期 → 日均总市值前 800（近似，标注 `confidence=medium`）

**实测准确率**：2017 ≈ 24.8% → 2026-06 ≈ **79.6%**（对比当日官方 1000 只）。
早期数字低是**必然**的——2017 的名单与 2026 的名单本就重合很少，不代表方法失效。

## 已知误差来源（必须在交付报告里声明）

- 中证800 剔除是近似（见上）
- **流动性筛选缺失**：官方剔除「成交额排名后 20%」
- **ST 筛选缺失**：官方剔除 ST/*ST
- 送转带来的股本变动日与真实生效日可能有 1-2 日错位

## 如何量化「重建快照 vs 真实快照」的差距（必做，别拍脑袋）

**没有任何历史时点的官方真值**，所以差距必须靠三个可测量夹逼，不要给单一数字：

| 指标 | 定义 | 含换手噪声？ |
|---|---|---|
| **A. 确证召回率** | 对 `ledger(T)`（确定在场集合），抓到了多少 | ❌ 纯净，只含方法误差 |
| **B. 确证误纳率** | `recon(T) ∩ ledger800(T)`，违反互斥约束 | ❌ 纯净，100% 确证是错 |
| C. 与官方当前真值匹配率 | 与当日官方名单重合度 | ✅ 含多年累计换手 |

### 关键：用「时间错位检验」把换手噪声剥离

指标 C 天然混了真实换手。剥离方法：用第 i 期重建去匹配第 i+k 期账本，
看匹配率随 k 的衰减率：

```
基准期 k=0     k=1     k=2     k=3
2024-12-16  90.0%   86.0%   79.5%   72.7%
2024-06-17  88.0%   86.4%   78.4%   72.6%
```

- 每错位 1 期（半年）额外衰减约 **2~3 个百分点** → 反推单期真实换手约 10%
- 若 C 的失配率远大于 `k × 单期衰减` 的累积值，说明失配主要来自**真实换手**
  而非方法误差（实测 9 年失配 39.5%，其中约 85~90% 归因于换手）

### 实测结论（中证1000，2017-2026）

| 时段 | 预期准确率 | 每 1000 只错误数 | 构成 |
|---|---|---|---|
| **2024 至今** | **约 88~90%** | 100~120 | 漏选 ~100，误纳 ~23 |
| 2022 ~ 2024 | 约 85~88% | 120~150 | 漏选 ~120，误纳 ~28 |
| 2019 ~ 2021 | 约 80~85% | 150~200 | 漏选 ~180，误纳 ~28 |
| 2017 ~ 2018 | 约 70~80%（区间很宽） | 200~300 | 统计噪声主导 |

**误差方向偏好**：用「市值前 800」近似中证800，边界股票易张冠李戴，
把实际属中证800（市值更大、更稳）的股票放进 1000
→ **回测收益偏乐观的概率大于偏悲观**，建议解读时对收益率打 5~10% 折扣。

## 融合输出（推荐交付形态）

三源融合，逐股标注证据等级：

| `evidence` | 含义 | 建议 |
|---|---|---|
| `official` | 官方账本佐证（`纳入日 ≤ 该期时点`） | 高置信 |
| `model` | 仅模型推断 | 中置信 |
| `CONFLICT` | 该期**仍属中证800**却被选进1000 | **明确噪声，建议剔除** |

同时输出「纯官方证据」版（`ledger_only/`），供保守策略只跑高置信子集。

两种使用姿势：
1. **只要高置信** → 读 `ledger_only/`（纯官方证据），代价是池子不完整
2. **要完整但要干净** → 读主 CSV，**剔除 `evidence == CONFLICT` 的行**，剩 95~98% 可靠

## 交付物清单

写入 `<项目>/csi1000_history_v2/`：

- `csi1000_history_v2.csv` — 长表：`date,code,qmt_code,rank,avg_mcap_yi,evidence`
- `csi1000_history_v2_wide.csv` — 宽表：股票 × 期，0/1
- `qmt_sectors_v2/csi1000_YYYYMMDD.txt` — **QMT 可直接用**，逗号分隔 `600007.SH,600017.SH,...`
- `ledger_only/ledger_YYYYMMDD.txt` — 纯官方证据名单（下界，干净）
- `sector_switch_by_date_v2.csv` — 日期区间 → 板块文件映射
- `ledger_rebalance_dates.txt` — 官方真实调仓日全表
- `accuracy_report_v2.md` — 方法论 + 逐期置信度 + 偏差声明

## 接入 QMT 策略（消除前视偏差）

把 `_get_csi1000()` 里对 `get_stock_list_in_sector('中证1000')` 的调用换成按日期读文件：

```python
import os

SECTOR_DIR = r'D:\WorkSpace\Myrepo\quant\csi1000_history_v2\qmt_sectors_v2'

def _get_csi1000_by_date(C, date_str):
    """date_str: 'YYYYMMDD'；返回该时点生效的中证1000股票池。"""
    files = sorted(os.listdir(SECTOR_DIR))              # csi1000_YYYYMMDD.txt
    usable = [f for f in files if f[8:16] <= date_str]
    if not usable:
        return []
    path = os.path.join(SECTOR_DIR, usable[-1])         # 最近一次调仓后生效的名单
    with open(path, 'r', encoding='utf-8') as fp:
        return [c.strip() for c in fp.read().split(',') if c.strip()]
```

在 `handlebar` 里用 `context.now` 推 `date_str` 调用即可。

## QMT 板块文件格式（两个都要知道）

- `datadir\Sector\指数成分股板块\中证1000` — **纯逗号分隔** `600007.SH,600017.SH,...`
  → 这是自定义板块文件的格式，本技能的交付文件照此格式
- `datadir\Weight\sectorWeightData.txt` — 段头 `SH000852;` 后跟 `600007.SH,0.052;` 重复
  （**GBK 编码**，598 个段）
  ⚠️ 解析坑：按 `;` split 后**首个 token 同时含段头和第一条成分**，必须先剥离段头，
  否则会解析出 0 只。

## 本机环境注意

- 用 factorhub 的 venv：`D:\WorkSpace\Myrepo\quant\factorhub\.venv\Scripts\python.exe`
  （或 `D:\WorkSpace\Myrepo\quant\.workbuddy\venv\Scripts\python.exe`），两者都有 akshare/pandas。
- Bash 工具在本机不可用（`ls`/`cd`/`dirname` 全部 `command not found`），**一律用 PowerShell**。
- PowerShell stdout 不回显，必须 `Set-Content` 到临时文件再 Read。
- 涉及中文/正则的脚本一律写 `.py` 跑，别在 PowerShell 里拼。

## 参考

- `references/source_probe_log.md` — 各数据源探测的原始命令与返回，避免重复试错
- `scripts/rebuild_csi_history.py` — 端到端重建脚本（可改 `INDEX_CODE` 复用到其他中证指数）
- `scripts/measure_snapshot_error.py` — 三指标夹逼法量化「重建快照 vs 真实快照」差距
