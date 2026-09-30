---
name: quant-toolkit
description: 统一的量化投资工具集，合并了原先分散的多个量化 skill。覆盖：1)数据源(akshare/baostock/同花顺iFinD/问财)取行情财务成分股；2)QMT/MiniQMT/Ptrade 实盘与策略开发；3)因子检验/因子库审计/策略归因/策略采集；4)中证指数历史成分股重建与ETF池去重瘦身；5)回测日志归因与涨停复盘；6)机构级研报生成与黄金宏观复盘。当用户做量化分析、取数、写QMT策略、因子检验、回测归因、ETF池管理、涨停复盘、个股研报、黄金宏观复盘，或提及 akshare/baostock/qmt/miniqmt/ptrade/问财/因子/策略/回测/ETF/涨停/研报/黄金 等关键词时，调用本技能。
---

# 量化工具集 quant-toolkit

本技能把原先 18 个分散的量化/金融 skill 合并为 **一个**，按 6 个能力域组织在 `areas/` 下。
每个原 skill 的内容**原样保留**在其子目录中，**零内容损失**。

## 使用方式（重要）

本 SKILL.md 只做「能力索引 + 触发分发」。当某个任务落入下面某一域时：
1. 先确认命中哪个子技能（看触发条件）；
2. 用 Read 工具打开对应 `areas/<域>/<skill>/SKILL.md`，按其完整指令执行；
3. 子技能里的 `references/`、`scripts/`、`demo_project/` 等相对路径在子目录内依然有效，照常调用。

> 不要凭本文件的摘要直接动手，细节以被调用的子 SKILL.md 为准。

## 能力域与触发条件

### ① 数据源（免费/开源取数）
触发：需要 A股/期货/基金/宏观等行情、财务、成分股、资金流数据；提到 akshare / baostock / 同花顺iFinD / 问财 / 自然语言选股。
| 子技能 | 路径 | 适用 |
|---|---|---|
| akshare | `areas/data-sources/akshare/SKILL.md` | 全品类金融数据（股票/期货/期权/基金/外汇/债券/指数/加密货币） |
| baostock | `areas/data-sources/baostock/SKILL.md` | 免费免注册 A股历史行情/财务/交易日历 |
| ifind-finance-data | `areas/data-sources/ifind-finance-data/SKILL.md` | 同花顺 iFinD 专业数据（含日内 L1） |
| pywencai | `areas/data-sources/pywencai/SKILL.md` | 中文自然语言查询 A股/指数/基金/港美股/可转债 |

### ② QMT / MiniQMT / Ptrade 实盘与策略开发
触发：写 QMT 策略、xtquant、迅投、MiniQMT、Ptrade、实盘交易、回测、选股/技术指标策略。
| 子技能 | 路径 | 适用 |
|---|---|---|
| qmt（权威源） | `areas/qmt-trading/qmt__skillhub/SKILL.md` | 迅投 QMT Python 策略开发/回测/实盘，A股期货期权全品种。**以本目录为 QMT 主源**（含 `references/qmt_api_reference.md`） |
| qmt-docs（补充） | `areas/qmt-trading/qmt-docs/SKILL.md` | QMT Python 开发指南与 API 参考补充材料 |
| miniqmt | `areas/qmt-trading/miniqmt/SKILL.md` | MiniQMT（XtQuant SDK）行情获取与交易下单 |
| ptrade | `areas/qmt-trading/ptrade/SKILL.md` | 恒生 Ptrade，策略运行在券商服务器 |

### ③ 因子与策略分析
触发：因子检验、因子库审计、回测归因、策略采集、截面排序、多因子打分、信号预测力检验。
| 子技能 | 路径 | 适用 |
|---|---|---|
| cross-section-factor-fit | `areas/factor-strategy/cross-section-factor-fit/SKILL.md` | 检验「截面排序因子」能否匹配执行型策略，给适配评级 |
| factor-library-audit | `areas/factor-strategy/factor-library-audit/SKILL.md` | FactorHub 因子库全库截面审计 + 四道严谨性闸门 + 看板部署 |
| quant-strategy-attribution | `areas/factor-strategy/quant-strategy-attribution/SKILL.md` | 回测归因诊断 / 信号前瞻预测力统计检验 |
| quant-strategy-collector | `areas/factor-strategy/quant-strategy-collector/SKILL.md` | 量化策略全自动采集整理（研报/论文→标准化文档） |

### ④ 指数与 ETF 池管理
触发：历史成分股重建、回测股票池、ETF/基金池去重瘦身、同质化审查。
| 子技能 | 路径 | 适用 |
|---|---|---|
| csi-index-constituent-rebuild | `areas/index-etf/csi-index-constituent-rebuild/SKILL.md` | 中证系列（1000/800/500/300/2000/全指）历史成分股重建 |
| etf-pool-slim | `areas/index-etf/etf-pool-slim/SKILL.md` | 按近3年收益相关性对 ETF/基金池去重瘦身 |

### ⑤ 回测日志与复盘
触发：分析回测日志、收益归因、涨停复盘、看板生成。
| 子技能 | 路径 | 适用 |
|---|---|---|
| ma20-backtest-log-analysis | `areas/backtest-review/ma20-backtest-log-analysis/SKILL.md` | MA20 策略逐日回测日志归因（收益来源/集中度/择时效率/交易成本） |
| limit-up-review | `areas/backtest-review/limit-up-review/SKILL.md` | 上一交易日涨停股复盘 + 响应式 HTML 看板 |

### ⑥ 个股与宏观研究
触发：研报生成、个股深度分析、黄金宏观复盘、金价看盘。
| 子技能 | 路径 | 适用 |
|---|---|---|
| equity-researcher | `areas/research/equity-researcher/SKILL.md` | 机构级投研报告（A股/港股/美股，速览3-5页 / 深度≥25页） |
| gold-macro-review | `areas/research/gold-macro-review/SKILL.md` | 黄金宏观指标复盘看盘（三地金价 + 6 项核心指标） |

## 工作约定（跨域通用）

- **Python 运行时**（脚本默认）：`C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe`
- 涉及中文/正则/统计的脚本一律用 managed Python 跑，显式 `encoding="utf-8"` 读写；结果落临时文件用 Read 读回（PowerShell stdout 不回显）。
- **QMT 权限硬约束**：用户仅有 **QMT 免费版**，没有 L2/VIP 数据额度。取数方案默认以免费版能取到的为准（行情 1d/1m/5m/tick、复权、财务三表 + PERSHAREINDEX + CAPITALSTRUCTURE、板块成分、交易日历等）；不要把「从付费源拉数据」当默认路径。
- 文件操作优先用 Read/Write/Edit；需要正则/批量处理时用 Python 脚本。
- 本机共享仓库根目录：`D:\WorkSpace\Myrepo\ai-skills`（通过 junction 被各 AI 应用引用）。
