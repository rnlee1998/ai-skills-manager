# 中证指数历史成分股 —— 数据源探测原始记录

本文件记录各数据源的**实际探测命令与返回**，避免后续重复试错。
探测时间：2026-09-22。

## 环境前提

- 代理：`HTTP_PROXY` / `HTTPS_PROXY` = `http://127.0.0.1:59980`（环境变量已设置）
- **代理会让东财 `push2his.eastmoney.com` / `push2.eastmoney.com` 报 ProxyError**
  → 行情走新浪，不走东财 push2。
- `datacenter-web.eastmoney.com` 走代理正常（需 `Referer: https://data.eastmoney.com/`）。
- 新浪、中证官网走代理正常。
- PowerShell 5.1 语法注意：`try/catch` 不能当表达式写在 `@()` 里。

## 1. 中证指数官网

### 1.1 官方 OSS（只有当日快照）

```
https://csi-web-dev.oss-cn-shanghai-finance-1-pub.aliyuncs.com/static/html/csindex/public/uploads/file/autofile/cons/000852cons.xls
```
- 返回：HTTP 200，213,504 B，1000 只当日成分股
- 另有 `closeweight/000852closeweight.xls`（231,424 B，带权重）
- **无任何按日期归档的历史目录**

### 1.2 csindex-home API（可用，但无成分股历史端点）

| 端点 | 结果 |
|---|---|
| `/csindex-home/indexInfo/index-basic-info/000852` | 200，完整指数元信息 |
| `/csindex-home/indexInfo/index-feature/000852` | 200，`consNum:1000.0`，`calMkvMedian:"68.04"` |
| `/csindex-home/index/weight/top10new/000852` | 200，前十大权重 |
| `/csindex-home/data-service/sector-change` | 200，但**只有板块涨跌幅，不是成分股** |

URL 形态：`https://www.csindex.com.cn/csindex-home/{module}/{method}/{indexCode}`
（代码放路径末尾，不带斜杠/查询参数）

**结论：不存在历史成分股端点。**

## 2. 新浪

### 2.1 历史成分股页（死路）

```
https://vip.stock.finance.sina.com.cn/corp/go.php/vII_HistoryComponent/indexid/{idx}.phtml
```
- 有「纳入日期」「剔除日期」两列，**但只到 2010-07-01**
- **没有 `000852` 的页面**

### 2.2 未复权日线（可用，主力数据源）

```
https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600519&scale=240&ma=no&datalen=2900
```
- 返回 **原始未复权** 日线 OHLCV
- 验证：茅台 2020-01-02 = 1130.000，2021-02-18 = 2471.000 → 与真实成交价一致，**未复权**
- `scale=240` = 日线；`datalen=6000` 可回溯到 IPO
- 性能：约 0.4 s/股，330 KB/股；5769 只约 750 s（10 线程）

### 2.3 akshare 新浪口径成分股（关键）

```python
import akshare as ak
ak.index_stock_cons(symbol="000852")
```
→ 1000 行 × 3 列：`品种代码` / `品种名称` / `纳入日期`
→ 底层即 2.1 的页面数据，`纳入日期` 为**官方真实调仓日**。**这是最大发现。**

## 3. 东方财富

### 3.1 当前成分股（可用，需分页）

```
https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_INDEX_TS_COMPONENT&filter=(TYPE="7")&pageSize=500&pageNumber=1
Referer: https://data.eastmoney.com/
```
- TYPE 映射：`1`=沪深300，`3`=中证500，`7`=中证1000，`13`=中证2000
- ⚠️ **`pageSize` 服务端硬顶 500**，传 1000 只会返回 500，必须显式分页
- 字段：`SECUCODE, SECURITY_CODE, SECURITY_NAME_ABBR, CLOSE_PRICE, TOTAL_SHARES, FREE_SHARES, FREE_CAP, INDUSTRY, REGION, EPS, BPS, ROE, PE, WEIGHT`
- ⚠️ `TOTAL_SHARES` / `FREE_SHARES` 单位是**亿股**，`FREE_CAP` 单位是**亿元**
  → `TOTAL_SHARES × CLOSE_PRICE` 直接得亿元市值

### 3.2 历史股本变动（可用，主力数据源）

```
https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_F10_EH_EQUITY&filter=(SECUCODE="600519.SH")&columns=SECUCODE,SECURITY_CODE,END_DATE,CHANGE_REASON,TOTAL_SHARES,LISTED_A_SHARES
```
- 返回该股**每一次股本变动的日期 + 总股本**（茅台可回溯到 2001 上市前）
- ⚠️ **只能单只查**：`filter=(SECUCODE in ("600519.SH","000001.SZ"))` 会**静默只返回第一只**
  → 必须逐股循环（5574 只 / 8 线程 ≈ 152 s）
- ⚠️ `END_DATE` 返回是**字符串**，与价格日期（int）比较前必须转 int

### 3.3 push2 行情（不可用）

`push2his.eastmoney.com`、`push2.eastmoney.com` → **ProxyError**
（`_diag1.py` 实测；`trust_env=False` 则 ConnectionError）

## 4. QMT 本地文件

### 4.1 `datadir\Weight\sectorWeightData.txt`

- 1,774,843 B，**GBK 编码**，`;` 分隔，598 个段
- 格式：段头 `SH000852;` 后跟 `600007.SH,0.052;` 重复
- 段规模：`SH000300`=300、`SH000905`=500、`SH000852`=1000、`SH000016`=50、`SH000001`=2009
- ⚠️ **解析坑**：按 `;` split 后**首个 token 同时包含段头和第一条成分**
  （如 `SH000852;600007.SH,0.052`），必须先剥离段头，否则解析出 0 只。
- **仅当日快照**，且实测与 akshare 官方名单 Jaccard 仅 30.2% → **质量存疑，勿做回测股票池**

### 4.2 `datadir\Weight\sectorChange.txt`

- 154,947 B，**UTF-8**
- 格式：`000016.SH;20040102,600030.SH,中信证券,1;...`，末位 `1`=纳入 / `0`=剔除
- **只有 3 个段**：`000016.SH`(354)、`000300.SH`(1514)、`000905.SH`(2722)
- **全部事件截止 2017-12-11，之后完全冻结**（19 个后续日期 0 变动）
- **无 `000852` 段**

### 4.3 `datadir\Sector\指数成分股板块\中证1000`

- 9.8 KB，**纯逗号分隔** `600007.SH,600017.SH,...`
- → **这是 QMT 自定义板块文件格式，交付文件照此格式**

## 5. 其他（均失败）

| 尝试 | 结果 |
|---|---|
| 腾讯 `web.ifzq.gtimg.cn/appstock/app/fqkline/get` | 6 种参数格式全部返回 `"param error"` |
| baostock 批量取价 | 高频调用后被限流（2500 只只返回 154 只）；单只 0.1 s 可恢复 |
| 东财 HIS 类报表 | 返回「报表配置不存在」 |
| 同花顺 / 雪球 / 巨潮 | 被阻断或不存在对应接口 |

## 6. 关键量化结论汇总

- **官方当前 1000 只 vs 市值重建（一年日均总市值法）**：
  - 单日市值排名法：46.6%
  - **一年日均市值法：70.6%**（关键改进）
  - 逐期：2017 ≈ 24.8% → 2026-06 ≈ **79.6%**
- **指数层级关系验证**：CSI1000 ∩ HS300 = 0，∩ CSI500 = 0，∩ CSI2000 = 0
- **中证800 市值排名跨度**：官方 800 实际覆盖市值排名 **1 → 1721**
  （因官方用自由流通市值 + 行业均衡排序，故「前 800」只是近似）
- **官方 CSI1000 特征**：流通/总股本比中位数 **0.91**；市值 min 43.9亿 / median 121.3亿 / max 1135.3亿
- **akshare 账本三铁律**（见 SKILL.md）：
  1. `ledger(T) ⊂ 当前名单`
  2. 三张账本任一时点两两交集 = 0
  3. `ledger800(T) ∩ 当前1000 = 0`（所有 T）
- **三方 Jaccard**：akshare账本∩市值重建 = **51.8%**；QMT∩账本 = 30.2%；QMT∩重建 = 27.1%
