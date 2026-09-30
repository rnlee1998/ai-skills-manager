# QMT 内置 Python 策略框架 API 库

> 本文件由两处参考工程实际策略代码归纳整理：
> 1. `D:\WorkSpace\Myrepo\quant`（demo.py、test.py、get_20200526_data.py、multi_factor.py、bolling/ 下 6 个策略文件，排除 ETF 轮动策略）
> 2. `D:\WorkSpace\softwares\QMT_test\国金QMT交易端模拟\python`（`_PyContextInfo.py` 官方 ContextInfo 封装层 + A策略.py、PY组合模型.py、PY模型回测示例.py、PY简单示例.py、机器学习回测示例.py、ARIMA预测.py、CMRA/DASTD/HSIGMA/STOA/STOM/STOQ.py、股本营收资产.py 等明文策略；其余策略文件被 QMT 平台加密无法读取，但 API 均已包含在 `_PyContextInfo.py` 中）
>
> 这些 API 均为 **QMT 完整版内置 Python 环境**（非 miniQMT 的 xtquant SDK）的用法，适用于回测与实盘策略编写。

---

## 1. 策略生命周期函数

| 函数 | 说明 | 参考出处 |
|------|------|----------|
| `init(ContextInfo)` | 初始化函数，策略启动时调用一次。设置股票池、账户 ID、持仓字典、参数等 | 全部文件 |
| `handlebar(ContextInfo)` | K 线回调函数，每根 K 线触发一次（tick/1m/5m/30m/1d 等），交易逻辑写在这里 | 全部文件 |
| `after_init(ContextInfo)` | 初始化完成后调用（用于数据下载/预计算） | `bolling/test.py` |
| `stop(ContextInfo)` | 策略停止时调用 | 官方文档 |

```python
def init(ContextInfo):
    ContextInfo.s = ContextInfo.get_sector('000300.SH')   # 股票池
    ContextInfo.set_universe(ContextInfo.s)
    ContextInfo.accountID = 'testS'                        # 回测资金账户ID
    ContextInfo.holdings = {i: 0 for i in ContextInfo.s}   # 持仓手数字典
    ContextInfo.money = ContextInfo.capital                # 初始资金

def handlebar(ContextInfo):
    d = ContextInfo.barpos
    if d > 60 and d % 20 == 0:   # 每20根K线调仓一次
        pass  # 交易逻辑
```

---

## 2. ContextInfo 常用属性

| 属性 | 类型 | 读写 | 说明 | 参考出处 |
|------|------|------|------|----------|
| `ContextInfo.barpos` | int | 只读 | 当前 K 线序号（0 起），用于时间判断 | 全部 |
| `ContextInfo.s` | list | 只读 | 股票池代码列表（如 `['000792.SZ']`） | 全部 |
| `ContextInfo.stockcode` | str | 只读 | 主图合约 6 位代码（如 `'600886'`），不含交易所 | STOM.py、A策略.py 等 |
| `ContextInfo.market` | str | 只读 | 主图合约市场（`'SH'`/`'SZ'`） | 同上 |
| `ContextInfo.period` | str | 只读 | 当前运行周期（如 `'1d'`/`'30m'`/`'1m'`） | test.py |
| `ContextInfo.dividend_type` | str | 只读 | 当前主图复权方式（如 `'front'`） | PY简单示例.py |
| `ContextInfo.capital` | float | 可写 | 初始资金 | demo.py、机器学习回测示例.py |
| `ContextInfo.benchmark` | str | 可写 | 基准标的代码（如 `'000300.SH'`） | PY模型回测示例.py |
| `ContextInfo.do_back_test` | bool | 可写 | 是否处于回测模式（实盘为 False，此时才执行 paint 绘图） | demo.py 等 |
| `ContextInfo.start` / `ContextInfo.end` | str | 可写 | 回测起止时间，格式 `'2025-10-01 00:00:00'` | bolling 策略 |
| `ContextInfo.refresh_rate` | int | 可写 | 刷新频率 | 官方封装 |
| `ContextInfo.data_info_level` | int | 可写 | 数据详细级别 | 官方封装 |
| `ContextInfo.request_id` | int | 只读 | 请求 ID | 官方封装 |
| `ContextInfo.stockcode_in_rzrk` | str | 只读 | 融资融券代码 | 官方封装 |
| `ContextInfo.in_pythonworker` | bool | 只读 | 是否运行在 Python worker 中 | 官方封装 |
| `ContextInfo.current_bar` | int | 只读 | 当前 K 线 | 官方封装 |
| `ContextInfo.time_tick_size` | int | 只读 | tick 时间粒度 | 官方封装 |
| `ContextInfo.accountID` / `ContextInfo.accID` | str | 自定义 | 资金账户 ID（下单与查询用，回测常用 `'testS'` / `'test'`） | 全部 |
| `ContextInfo.init_cash` | float | 自定义 | 初始现金（test.py 年化计算用） | test.py |

> 自定义状态可随意挂载到 ContextInfo 上，如 `ContextInfo.holdings`、`ContextInfo.buypoint`、`ContextInfo.buy_date`、`ContextInfo.total_fee` 等，跨 K 线保留。
> 常用拼接：`ContextInfo.stockcode + '.' + ContextInfo.market` 得到完整代码（STOM.py、机器学习回测示例.py 等）。

---

## 3. ContextInfo 数据方法

### 3.1 `set_universe(stock_list)` / `get_universe()` / `set_account(account_id, account_type='')`
```python
ContextInfo.set_universe(['000001.SZ', '600519.SH'])
stocks = ContextInfo.get_universe()          # 获取当前股票池
ContextInfo.set_account('testS')             # 切换资金账户
```
> 参考出处：全部文件、官方封装。`get_history_data` 等旧接口按股票池索引取数，须先 `set_universe`。

### 3.2 板块与股票池
```python
s = ContextInfo.get_sector('000300.SH')              # 指数成分股（参数为指数代码）
s = ContextInfo.get_stock_list_in_sector('沪深A股')   # 板块成分股（中文板块名）
s = ContextInfo.get_stock_list_in_sector('上证50')
s = ContextInfo.get_stock_list_in_sector('上证期权', '20200101')  # 第2参可传日期字符串
ContextInfo.create_sector('my_sector', ['000001.SZ']) # 创建自定义板块
inds = ContextInfo.get_industry('银行')               # 行业成分股
```
> 参考出处：PY模型回测示例.py（`get_stock_list_in_sector('上证50')`）、test.py、官方封装。
> `get_stock_list_in_sector(sectorname, real_timetag=-1)` 第 2 参可传 `'YYYYMMDD'` 字符串或毫秒时间戳，取历史时点成分。

### 3.3 `get_bar_timetag(barpos)` / `get_tick_timetag()` — 时间戳
```python
nowDate = timetag_to_datetime(ContextInfo.get_bar_timetag(ContextInfo.barpos), '%Y%m%d%H%M%S')
tick_ts = ContextInfo.get_tick_timetag()   # 当前 tick 毫秒时间戳
```
> 参考出处：全部文件。返回毫秒级时间戳，需配合全局函数 `timetag_to_datetime` 转字符串。

### 3.4 `get_market_data_ex(...)` — **批量获取多标的 K 线数据（核心，推荐）**
```python
market_data = ContextInfo.get_market_data_ex(
    ['close'],                    # 字段列表，可多字段：['open','high','low','close','volume']
    ContextInfo.s,                # 股票代码列表
    end_time=bar_date,            # 截止时间字符串，如 '20200526150000'
    period='1d',                  # 周期：'1d'/'30m'/'5m'/'1m'/'tick'
    count=1,                      # 获取K线根数
    dividend_type='front_ratio',  # 复权：'front_ratio'=前复权，'front' 亦可
    fill_data=True,               # 缺失数据填充
    subscribe=False               # 是否订阅实时行情（回测/历史取数设 False）
)
```
**完整签名**（官方封装）：`get_market_data_ex(fields=[], stock_code=[], period='follow', start_time='', end_time='', count=-1, dividend_type='follow', fill_data=True, subscribe=True)`
**返回值**：`dict {股票代码: pandas.DataFrame}`，DataFrame 的 index 为时间戳（stime 列），列名为字段名。
> 内部实现：封装层将 `fields` 与 `stime` 拼为 DataFrame 并以 stime 为索引，底层调用 `get_market_data2`。
> 可用 `get_market_data_ex_ori(...)` 获取原始 dict 结构（不转 DataFrame）。

**常用处理模式**（参考出处：multi_factor.py、get_20200526_data.py、test.py）：
```python
if '000792.SZ' in market_data and not market_data['000792.SZ'].empty:
    open_list = market_data['000792.SZ']['open'].tolist()
    if len(open_list) > 0:
        open_price = open_list[-1]   # 最新一根K线的开盘价
```

### 3.5 `get_market_data(...)` — 旧接口，**返回类型随参数组合变化**
**完整签名**（官方封装）：`get_market_data(fields, stock_code=[], start_time='', end_time='', skip_paused=True, period='follow', dividend_type='follow', count=-1)`

**返回类型规则**（重要，来自官方封装逻辑）：

| 参数组合 | 返回类型 |
|---------|---------|
| 单字段 + 单代码 + 无时间范围 + `count=-1` | **标量**（最新值） |
| 单代码 + 无时间范围 | `Series`（index=fields） |
| 多代码 + 无时间范围 | `DataFrame`（index=stock_code, columns=fields） |
| 单代码 + 指定时间范围或 `count>=0` | `DataFrame`（index=时间, columns=fields），需 `sort_index()` |
| 多代码 + 指定时间范围或 `count>=0` | `Panel`（items=代码） |

```python
# 1) 单代码+时间范围 → DataFrame（机器学习回测示例.py：用 start_time/end_time 训练集）
df = ContextInfo.get_market_data(['open','high','low','close','volume'],
                                 stock_code=[ContextInfo.stock],
                                 start_time='20160101', end_time='20170101',
                                 dividend_type='front')
df = df.sort_index()            # index 为日期字符串
close_series = df['close']

# 2) 单代码+count → DataFrame（HSIGMA.py：取252根）
closes = ContextInfo.get_market_data(fields=['close'], stock_code=["000300.SH"],
                                     end_time=lastdate, count=252)
close_values = closes['close'].values

# 3) 无 stock_code → 当前主图合约（PY简单示例.py：随主图周期/复权）
close = ContextInfo.get_market_data(['close'], period=ContextInfo.period,
                                    dividend_type=ContextInfo.dividend_type)
```
> 官方封装会打印提示："get_market_data接口版本较老，推荐使用get_market_data_ex替代"。
> 机器学习回测示例.py 用 `dividend_type='front'`；quant 参考工程用 `'front_ratio'`，两者均为前复权，视 QMT 版本兼容。

### 3.6 `get_history_data(count, period, field, index)` — 获取历史数据序列
```python
# 第4参 index 为股票池序号（0起），返回 dict {股票代码: [数值列表]}
data_high = ContextInfo.get_history_data(22, '1d', 'high', 3)
data_close60 = ContextInfo.get_history_data(62, '1d', 'close', 3)
close_list = data_close60['000300.SH']   # 按代码取值
```
> 参考出处：demo.py（`get_history_data(1,'1d','open',3)`、`get_history_data(22,'1d','high',3)`）、PY组合模型.py、DASTD.py。
> **注意**：第 4 参数是股票池**索引**而非代码，需先 `set_universe` 建立股票池。返回按股票代码为 key 的 dict。
> 官方封装签名：`get_history_data(len, period, field, dividend_type='none', skip_paused=True)`，省略索引时取主图合约（A策略.py 中 `get_history_data(60, currentperiod, 'close', 0)`，0 即主图）。

### 3.7 `get_local_data(...)` — 本地数据（不订阅服务器）
```python
# 签名：get_local_data(stock_code='', start_time='19700101', end_time='22010101', period='follow', divid_type='none', count=-1)
data = ContextInfo.get_local_data('000001.SZ', '20230101', '20241231', '1d', 'none', -1)
```
> 官方封装提示："get_local_data接口版本较老，推荐使用get_market_data_ex替代，参数subscribe设置为False"。

### 3.8 `get_close_price(market, stockCode, realTimetag, period, dividType)` — **指定时间戳取收盘价**
```python
# 签名：get_close_price(market, stockCode, realTimetag, period=86400000, dividType=0)
now = ContextInfo.get_bar_timetag(ContextInfo.barpos)
hs300c = ContextInfo.get_close_price("SH", "000300", now, 86400000)   # 当前时刻沪深300收盘
c = ContextInfo.get_close_price(ContextInfo.market, ContextInfo.stockcode, now, 86400000)
```
> 参考出处：A策略.py。**period 单位是毫秒**，常用映射（A策略.py 内置字典）：
> `{'1d':86400000, '1m':60000, '5m':300000, '15m':900000, '30m':1800000, '60m':3600000}`
> 注意 market 与 stockCode 分开传（如 `"SH","000300"`），不是完整代码。

### 3.9 交易日期与时间
```python
dates = ContextInfo.get_trading_dates('000001.SZ', '20230101', '20241231', 250, '1d')  # 交易日列表
loc = ContextInfo.get_date_location('20230101')    # 日期在K线中的位置
```

### 3.10 利率/换手/量能
```python
rf = ContextInfo.get_risk_free_rate(ContextInfo.barpos)   # 按barpos取无风险利率（年化百分数，CMRA.py 除100/12 转月）
turn = ContextInfo.get_turn_over_rate('000001.SZ')         # 单标的换手率
df = ContextInfo.get_turnover_rate(['000001.SZ'], '20230101', '20240101')  # 批量换手率 DataFrame
sv = ContextInfo.get_svol('000001.SZ')    # 主动买量
bv = ContextInfo.get_bvol('000001.SZ')    # 主动卖量
lc = ContextInfo.get_last_close('000001.SZ')   # 最新收盘价
lv = ContextInfo.get_last_volume('000001.SZ')  # 最新成交量
```
> 参考出处：CMRA.py、HSIGMA.py（`get_risk_free_rate(d_index)` 按 barpos 循环取）、官方封装。

### 3.11 净值与回测
```python
nv = ContextInfo.get_net_value(ContextInfo.barpos)   # 当前净值
idx = ContextInfo.get_back_test_index()              # 回测索引
```

### 3.12 全推行情快照
```python
ticks = ContextInfo.get_full_tick(['000001.SZ', '600519.SH'])   # 全推快照 dict
```

---

## 4. 财务与基本面数据

### 4.1 `get_financial_data(...)` — **两种调用方式**

**方式一（新式，推荐）**：字段列表 + 股票列表 + 起止日期
```python
# 签名：get_financial_data(fieldList, stockList, startDate, endDate, report_type='report_time', pos=-1)
# 返回 Series / DataFrame / Panel，规则同 get_market_data（1股1期→Series，1股多期→DataFrame(index=日期)，多股→按股分组）
df = ContextInfo.get_financial_data(['CAPITALSTRUCTURE.circulating_capital'],
                                    ['000001.SZ'], '20200101', '20210101')
```
> 参考出处：STOM.py、STOA.py（`get_financial_data(['CAPITALSTRUCTURE.circulating_capital'], [ContextInfo.stock], time_region, date)`）。

**方式二（旧式）**：表名 + 字段名 + market + code + barpos，返回单值
```python
# 字段名格式：表名.字段名（新式） / 分传表名、字段名（旧式）
cap = ContextInfo.get_financial_data('CAPITALSTRUCTURE', 'total_capital', ContextInfo.market, ContextInfo.stockcode, ContextInfo.barpos)
inc = ContextInfo.get_financial_data('PERSHAREINDEX', 'inc_revenue', ContextInfo.market, ContextInfo.stockcode, ContextInfo.barpos)
bps = ContextInfo.get_financial_data('PERSHAREINDEX', 's_fa_bps', ContextInfo.market, ContextInfo.stockcode, ContextInfo.barpos)
```
> 参考出处：股本营收资产.py、STOM.py、STOQ.py。第 3、4 参为市场与代码（分开），第 5 参为 barpos 索引。

**常用财务表**：`CAPITALSTRUCTURE`（股本结构：circulating_capital 流通股本、total_capital 总股本）、`PERSHAREINDEX`（每股指标：inc_revenue 主营收入、s_fa_bps 每股净资产）。
**`report_type`**：`'report_time'`（报告期，默认）/ `'announce_time'`（公告期）。

### 4.2 `get_raw_financial_data(fieldList, stockList, startDate, endDate, report_type='report_time', data_type='dict')`
> 官方封装。返回原始 dict 数据（`{'field':..., 'stock':..., 'date':..., 'value':...}`），不转 pandas。

### 4.3 `get_factor_data(field_list, stock_list, start_date, end_date)` — 因子数据
```python
# 返回规则同 get_financial_data：1股1期→Series，1股多期→DataFrame，多股→dict {code: DataFrame}
data = ContextInfo.get_factor_data(['PE', 'PB'], ['000001.SZ'], '20200101', '20210101')
```

### 4.4 龙虎榜 / 十大股东 / 股东户数
```python
lhb = ContextInfo.get_longhubang(['000001.SZ'], '20230101', '20240101')   # 龙虎榜 DataFrame
# 字段：stockCode/stockName/date/reason/close/SpreadRate/TurnoverVolume/Turnover_Amount/buyTraderBooth/sellTraderBooth

top10 = ContextInfo.get_top10_share_holder(['000001.SZ'], 'flow_holder', '20230101', '20240101')
# data_name: 'flow_holder'（流通股东）/ 'holder'（全部股东）；返回 Series/DataFrame/Panel

holders = ContextInfo.get_holder_num(['000001.SZ'], '20230101', '20240101')   # 股东户数 DataFrame
```

### 4.5 市值 / 股本 / 指数权重
```python
small = ContextInfo.get_smallcap()          # 小盘股列表
mid = ContextInfo.get_midcap()              # 中盘股列表
large = ContextInfo.get_largecap()          # 大盘股列表
fc = ContextInfo.get_float_caps('000001.SZ')   # 流通股本
ts = ContextInfo.get_total_share('000001.SZ')  # 总股本
w = ContextInfo.get_weight_in_index('000300.SH', '000001.SZ')   # 在指数中的权重
fin = ContextInfo.get_finance('000001.SZ')     # 财务数据
```

### 4.6 北向资金 / 港股通
```python
nf = ContextInfo.get_north_finance_change('1d')      # 北向资金变动
st = ContextInfo.get_hkt_statistics('00700.HK')       # 港股通统计
dt = ContextInfo.get_hkt_details('00700.HK')          # 港股通明细
```

### 4.7 产品（基金/资管）份额
```python
ps = ContextInfo.get_product_share('F000001', -1)         # 产品份额
pv = ContextInfo.get_product_asset_value('F000001', -1)   # 产品净值
pi = ContextInfo.get_product_init_share('F000001')        # 产品初始份额
```

---

## 5. ContextInfo 绘图方法

### 5.1 `paint(name, data, index, drawStyle, selectcolor='', limit='')` — 绘制指标线/点
```python
ContextInfo.paint('profit_ratio', profit, -1, 0)          # 4参：名称、值、-1、线型0
ContextInfo.paint('指数', ContextInfo.zhishu, -1, 0, 'noaxis')   # 5参：'noaxis'=不显示坐标轴
```
> 参考出处：全部文件。官方封装签名 `paint(name, data, index, drawStyle, selectcolor='', limit='')`：
> `limit='noaxis'` 隐藏坐标轴、`limit='nodraw'` 只计算不画（drawStyle 强制为 7）。
> `index=-1` 表示当前 K 线位置，`index` 也可传具体 barpos（A策略.py 用 `d`）。

### 5.2 `draw_text(condition, position, text)` — 图上标注文字
```python
ContextInfo.draw_text(1, 0.5, '买入')     # 满足条件(1)时在0.5位置标'买入'
ContextInfo.draw_text(1, 0.6, '卖出')
```
> 参考出处：A策略.py（买卖点标注）、test.py。官方封装签名 `draw_text(condition, position, text, limit='')`，`limit='noaxis'` 可选。

### 5.3 其他绘图函数（官方封装）
```python
ContextInfo.draw_vertline(condition, price1, price2, color='', limit='')   # 竖线
ContextInfo.draw_icon(condition, position, type, limit='')                 # 图标（type 为图标编号）
ContextInfo.draw_number(cond, price, number, precision, limit='')          # 数字标注
ContextInfo.get_function_line()        # 当前代码行号（内部调试用）
```
> `condition` 为真时绘制；`limit='noaxis'` 表示不占用坐标轴。

---

## 6. 全局数据函数

### 6.1 `timetag_to_datetime(timetag, format)` — 时间戳转日期字符串
```python
bar_date = timetag_to_datetime(ContextInfo.get_bar_timetag(ContextInfo.barpos), '%Y%m%d%H%M%S')
current_date = timetag_to_datetime(ContextInfo.get_bar_timetag(ContextInfo.barpos), '%Y%m%d')
```
> 参考出处：全部文件。常用格式：`'%Y%m%d%H%M%S'`（精确到秒）、`'%Y%m%d'`（仅日期）、`'%Y-%m-%d'`。

### 6.2 `download_history_data(stock, period, start, end)` — 下载历史数据
```python
download_history_data('000001.SZ', '1d', '20230101', '20241231')
```
> 参考出处：bolling/test.py（在 `after_init` 中先下载数据再计算）。

### 6.3 `ext_data(name, code, i, ContextInfo)` — 获取扩展数据（VBA/自建因子）
```python
atr_value = ext_data('atr', 'SH600886', 0, ContextInfo)   # 单值
adtm_value = ext_data('adtm', k[-2:] + k[0:6], 0, ContextInfo)
```
> 参考出处：multi_factor.py、bolling 策略。`name` 为扩展数据名；`code` 格式为 `交易所前缀+6位代码`（如 `'SH600886'`）；`i` 通常传 0。返回值可能为 None，需判空。

### 6.4 `ext_data_rank(name, code, i, ContextInfo)` — 获取扩展数据排名
```python
rank1 = ext_data_rank('atr', k[-2:] + k[0:6], 0, ContextInfo)
rank2 = ext_data_rank('adtm', k[-2:] + k[0:6], 0, ContextInfo)
rank_total[k] = 0.5 * rank1[k] - 0.5 * rank2[k]   # 多因子加权
```
> 参考出处：demo.py。参数同 `ext_data`。

### 6.5 其他全局函数（官方封装）
```python
resume_context_info(ContextInfo)      # 恢复上次K线上下文（回测状态持久化用）
request_general_file(strReq, callback)  # 请求通用文件，callback(result, error_code, error_info)
sync_transaction_from_external(operation, data_type, account_id, account_type, data_list)
    # 外部同步交易数据（内部按bson编码、1000条/批切片）
```
> 这些为官方封装层提供的高级函数，一般策略不需要直接调用。

---

## 7. 全局交易函数

### 7.1 `order_shares(code, volume, style, price, ContextInfo, accountID)` — 按股数下单（正买负卖）
```python
order_shares(k, -shares, 'fix', open_price, ContextInfo, ContextInfo.accountID)  # 卖出
order_shares(k, shares, 'fix', open_price, ContextInfo, ContextInfo.accountID)   # 买入
```
> 参考出处：demo.py、multi_factor.py、bolling 策略、A策略.py、PY组合模型.py、机器学习回测示例.py、PY模型回测示例.py。
> **注意**：`ContextInfo` 后还可传 `accountID`（第 6 参）。`style` 用 `'fix'` 或 `'FIX'` 均可（限价单，大小写不敏感）。

### 7.2 `passorder(opType, orderType, accountid, orderCode, prType, price, volume, ContextInfo)` — 通用下单（推荐）
```python
# 买入：opType=23，卖出：opType=24；orderType=1101 表示股票
passorder(23, 1101, C.accountid, stock, 5, -1, vol, C)   # 市价/最优价买入
passorder(24, 1101, C.accountid, stock, 5, -1, holding_vol, C)  # 卖出
```
> 参考出处：test.py、get_20200526_data.py。
> 参数速记：`passorder(买23/卖24, 1101股票, 账户, 代码, 价格类型5, 价格-1, 数量, ContextInfo)`。
> `prType=5` + `price=-1` 为按对手价/最新价成交的常用组合（配合限价时 prType 取对应类型并传价格）。

### 7.3 `get_trade_detail_data(accountid, market, data_type)` — 查询账户/持仓/委托/成交
```python
account = get_trade_detail_data(C.accountid, 'stock', 'account')[0]   # 账户资金
pos_list = get_trade_detail_data(C.accountid, 'stock', 'position')    # 持仓列表
orders   = get_trade_detail_data(C.accountid, 'stock', 'order')       # 委托列表
deals    = get_trade_detail_data(C.accountid, 'stock', 'deal')        # 成交列表
```
> 参考出处：全部文件。`market='stock'`（股票），`data_type` 大小写均可（'position'/'POSITION' 均验证可用，PY模型回测示例.py 用大写 `"POSITION"`）。

### 7.4 自定义持仓查询封装（官方示例通用写法）
```python
def get_holdings(accountid, datatype):
    holdinglist = {}
    resultlist = get_trade_detail_data(accountid, datatype, "POSITION")
    for obj in resultlist:
        holdinglist[obj.m_strInstrumentID + "." + obj.m_strExchangeID] = obj.m_nVolume
    return holdinglist
```
> 参考出处：PY模型回测示例.py、PY组合模型.py。返回 `{完整代码: 持仓股数}`。

---

## 8. 交易数据对象字段（get_trade_detail_data 返回值）

### 8.1 `'account'` 账户资金
| 字段 | 说明 |
|------|------|
| `m_dBalance` | 总资产（含持仓市值） |
| `m_dAvailable` | 可用资金 |
| `m_dInstrumentValue` | 持仓总市值 |

```python
account = get_trade_detail_data(C.accountid, 'stock', 'account')[0]
total_asset = account.m_dBalance
available_cash = account.m_dAvailable
total_value = account.m_dInstrumentValue
```
> 参考出处：test.py。

### 8.2 `'position'` 持仓
| 字段 | 说明 |
|------|------|
| `m_strInstrumentID` | 证券代码（如 `'000001'`，不含交易所） |
| `m_strInstrumentName` | 证券名称 |
| `m_strExchangeID` | 交易所（如 `'SZ'`/`'SH'`） |
| `m_nVolume` | 持仓数量（股） |
| `m_dOpenPrice` | 成本价 |
| `m_dLastPrice` | 最新价 |
| `m_dInstrumentValue` | 持仓市值 |
| `m_dPositionProfit` | 持仓盈亏 |

```python
pos_list = get_trade_detail_data(C.accountid, 'stock', 'position')
holdings = {i.m_strInstrumentID + '.' + i.m_strExchangeID: i.m_nVolume
            for i in pos_list if i.m_nVolume > 0}
for dt in pos_list:
    print(f"{dt.m_strInstrumentName} 成本:{dt.m_dOpenPrice:.2f} 最新:{dt.m_dLastPrice:.2f} "
          f"市值:{dt.m_dInstrumentValue:.2f} 盈亏:{dt.m_dPositionProfit:.2f}")
```
> 参考出处：test.py。注意 `m_strInstrumentID` 不含交易所后缀，需拼接 `m_strExchangeID` 得到完整代码。

### 8.3 `'order'` 委托
| 字段 | 说明 |
|------|------|
| `m_strOrderSysID` | 委托编号 |
| `m_nVolumeTraded` | 已成交量 |
| `m_dLimitPrice` | 委托价格 |

### 8.4 `'deal'` 成交
| 字段 | 说明 |
|------|------|
| `m_strTradeID` | 成交编号 |
| `m_dPrice` | 成交价 |
| `m_nVolume` | 成交量 |

---

## 9. 行情订阅与推送

```python
# 订阅单个标的K线，result_type 决定回调数据结构：'dict'/'list'/其他(默认DataFrame)
def on_quote(data):
    print(data)   # data 为 {stock_code: DataFrame/…}，含 'time' 字段时表示新推送

sub_id = ContextInfo.subscribe_quote('000001.SZ', period='1d', dividend_type='follow',
                                     result_type='dict', callback=on_quote)

# 全推订阅（一篮子标的）
sub_id2 = ContextInfo.subscribe_whole_quote(['000001.SZ', '600519.SH'], callback=on_quote)

ContextInfo.unsubscribe_quote(sub_id)      # 退订
subs = ContextInfo.get_all_subscription()  # 查看当前订阅
```
> 参考出处：官方封装 `_PyContextInfo.py`。`subscribe_quote` 返回 subID（>0 成功），内部以 `stime` 为索引组织数据。
> 交易实时主推示例.py 为官方订阅示例（文件被加密，用法以官方封装为准）。

---

## 10. 定时任务

### 10.1 `schedule_run(func, time_point, repeat_times, interval, name)` — 定时任务（新，推荐）
```python
import datetime as dt

def my_task(ContextInfo):
    pass  # 定时执行的任务

# 单次定时：明天 14:50 执行
ContextInfo.schedule_run(my_task, dt.datetime(2026, 8, 26, 14, 50, 0))

# 重复执行：从指定时间起，每 5 分钟执行 1 次（repeat_times=1），命名任务
ContextInfo.schedule_run(my_task, '20260826145000', repeat_times=1,
                         interval=dt.timedelta(minutes=5), name='task1')

ContextInfo.cancel_schedule_run(key)   # 取消任务（key 为返回的 id 或 name）
```
> 参考出处：官方封装。`time_point` 支持 `datetime` 对象或 `'%Y%m%d%H%M%S'` 字符串；`interval` 为 `datetime.timedelta`。

### 10.2 `run_time(funcname, intervalday, time, exchange='SH')` — 定时运行（旧）
```python
ContextInfo.run_time('my_func', 1, '14:50', 'SH')   # 每隔1天14:50执行 my_func（需另定义 def my_func(ContextInfo)）
```
> 参考出处：官方封装。`exchange` 默认 'SH'。

---

## 11. 回测参数设置（滑点/手续费）

```python
ContextInfo.set_slippage(True, '0.001')     # 启用滑点，幅度0.001（第1参为开关，第2参为滑点值）
slip = ContextInfo.get_slippage()           # 查询滑点设置
ContextInfo.set_commission(0, '0.0003')     # 设置手续费（第1参类型，第2参费率）
comm = ContextInfo.get_commission()         # 查询手续费
```
> 参考出处：官方封装。`set_slippage(True)` 只传 1 参时 b_flag 即滑点值；`set_commission(费率)` 同理。

---

## 12. 期权 API

```python
# 1) 期权列表：object=标的完整代码, dedate=到期月(6位'202603')或日期(8位), opttype='C'/'P', isavailavle=是否仅可交易
opts = ContextInfo.get_option_list('510050.SH', '202603', 'C', True)

# 2) 期权→标的：返回 {标的代码: [期权代码]}
undl_map = ContextInfo.get_option_undl_data()          # 全部期权按标的归类
undl = ContextInfo.get_option_undl(opt_code)           # 单期权对应标的

# 3) BSM 定价 / 隐含波动率
price = ContextInfo.bsm_price('C', target_price, strike_price, risk_free, sigma, days)   # 期权理论价
iv = ContextInfo.bsm_iv('C', target_price, strike_price, option_price, risk_free, days) # 隐含波动率

# 4) 其他
iv2 = ContextInfo.get_option_iv(opt_code)               # 期权IV
detail = ContextInfo.get_option_detail_data(opt_code)   # 期权详情
```
> 参考出处：官方封装。`bsm_price(optType, targetPrice, strikePrice, riskFree, sigma, days, dividend=0)`，targetPrice 可为数值或 list。
> 合约详情 `get_instrumentdetail(opt_code)` 的 `ExtendInfo` 含 `OptUndlCode`/`OptUndlMarket`/`optType`（'CALL'/'PUT'），期权代码形如 `10004567.SH` 或含 `.IF` 的中金所期权。
> 板块名：`'上证期权'`、`'深证期权'`、`'中金所'`、`'过期上证期权'` 等。

---

## 13. 期货与合约 API

```python
# 主力合约 / 历史合约
main = ContextInfo.get_main_contract('SHFE')            # 主力合约（参数为市场，如 'SHFE'/'DCE'/'CZCE'/'CFFEX'）
his = ContextInfo.get_his_contract_list('SHFE')         # 历史合约列表

# 合约乘数 / 合约到期
mult = ContextInfo.get_contract_multiplier('rb2601.SHF')   # 合约乘数
expire = ContextInfo.get_contract_expire_date('rb2601.SHF')# 到期日
open_date = ContextInfo.get_open_date('600000.SH')         # 上市日期

# 合约详情（30个字段）
inst = ContextInfo.get_instrument_detail('000001.SZ')
# 字段：ExchangeID/InstrumentID/InstrumentName/ProductID/ProductName/ExchangeCode/RzrkCode/UniCode/
#      CreateDate/OpenDate/ExpireDate/TradingDay/PreClose/SettlementPrice/UpStopPrice/DownStopPrice/
#      FloatVolumn/TotalVolumn/FloatVolume/TotalVolume/LongMarginRatio/ShortMarginRatio/PriceTick/
#      VolumeMultiple/MainContract/LastVolume/InstrumentStatus/IsTrading/IsRecent/HSGTFlag
```
> 参考出处：官方封装。`get_instrument_detail` 与 `get_instrumentdetail` 等价。
> 类型判断：`ContextInfo.is_future(market)`、`ContextInfo.is_stock(stock)`、`ContextInfo.is_fund(stock)`、`ContextInfo.is_suspended_stock(stock, type=0)`。

---

## 14. 股票代码格式与转换约定

| 场景 | 格式 | 示例 |
|------|------|------|
| 行情/下单（`get_market_data_ex`/`passorder`/`order_shares`） | `6位代码.交易所` | `'600886.SH'`、`'000001.SZ'` |
| 指数代码（`get_sector`） | `6位代码.交易所` | `'000300.SH'` |
| 扩展数据代码（`ext_data`/`ext_data_rank`） | `交易所前缀+6位代码` | `'SH600886'` |
| 持仓对象拼接 | `m_strInstrumentID + '.' + m_strExchangeID` | `'000001' + '.' + 'SZ'` |
| 主图合约拼接 | `ContextInfo.stockcode + '.' + ContextInfo.market` | `'600886' + '.' + 'SH'` |
| `get_close_price` 参数 | market 与 stockCode 分开传 | `("SH", "000300", timetag, 86400000)` |
| 期权代码 | 8位数字+交易所（或含 `.IF`） | `'10004567.SH'` |

```python
# 常用转换：完整代码 → 扩展数据代码（参考出处：multi_factor.py 等）
ext_code = k[-2:] + k[0:6]   # '600886.SH' → 'SH600886'
```

---

## 15. 其他工具接口（官方封装）

```python
ContextInfo.load_stk_list(dirfile, namefile)        # 从本地文件加载股票列表
ContextInfo.load_stk_vol_list(dirfile, namefile)    # 从本地文件加载股票量列表
factors = ContextInfo.get_divid_factors('000001.SZ', '20230101')   # 复权因子
st = ContextInfo.get_his_st_data('000001.SZ')       # 历史ST状态
idx = ContextInfo.get_his_index_data('000300.SH')   # 历史指数成分权重
etf = ContextInfo.get_ETF_list('SH', '510300', [])  # ETF列表
svol = ContextInfo.get_svol('000001.SZ')            # 主动买量
bvol = ContextInfo.get_bvol('000001.SZ')            # 主动卖量
# 资金分配辅助：按市值比例分配资金 → 返回可买数量
qty = ContextInfo.get_scale_and_stock(total_money, stock_value, '000001.SZ')
rank = ContextInfo.get_scale_and_rank([...])        # 列表排名
# 历史交易数据
his = ContextInfo.get_tradedatafromerds('stock', 'testS', '20230101', '20240101')
```

---

## 16. ContextInfo 完整方法索引（官方封装 _PyContextInfo.py 全量）

| 分类 | 方法 |
|------|------|
| 账户/股票池 | `set_account(account_id, account_type='')` `set_universe(list)` `get_universe()` |
| 状态判断 | `is_last_bar()` `is_new_bar()` `is_stock(s)` `is_fund(s)` `is_future(m)` `is_suspended_stock(s, type=0)` |
| K线数据 | `get_market_data_ex(...)` `get_market_data_ex_ori(...)` `get_market_data(...)` `get_history_data(...)` `get_local_data(...)` `get_full_tick(list)` `get_bar_timetag(i)` `get_tick_timetag()` `get_close_price(m,k,t,p,d)` |
| 时间/日期 | `get_trading_dates(code,s,e,count,period)` `get_date_location(date)` |
| 量/价/换手 | `get_last_close(s)` `get_last_volume(s)` `get_svol(s)` `get_bvol(s)` `get_turn_over_rate(s)` `get_turnover_rate(list,st,ed)` |
| 财务/因子 | `get_financial_data(...)` `get_raw_financial_data(...)` `get_factor_data(...)` `get_finance(s)` `get_top10_share_holder(...)` `get_holder_num(...)` `get_longhubang(...)` |
| 市值/股本 | `get_smallcap()` `get_midcap()` `get_largecap()` `get_float_caps(s)` `get_total_share(s)` `get_weight_in_index(idx,code)` |
| 利率 | `get_risk_free_rate(index)` |
| 板块/行业 | `get_sector(name,ts)` `get_industry(name,ts)` `get_stock_list_in_sector(name,ts)` `create_sector(name,list)` |
| 合约/标的 | `get_stock_type(s)` `get_stock_name(s)` `get_open_date(s)` `get_contract_expire_date(s)` `get_contract_multiplier(s)` `get_main_contract(m)` `get_his_contract_list(m)` `get_instrument_detail(s)` `get_instrumentdetail(s)` |
| 期权 | `get_option_list(obj,dedate,type,avail)` `get_option_undl(opt)` `get_option_undl_data(ref)` `get_option_detail_data(opt)` `get_option_iv(opt)` `bsm_price(...)` `bsm_iv(...)` |
| 资金/资产 | `get_net_value(barpos)` `get_back_test_index()` `get_total_asset()` `get_scale_and_stock(...)` `get_scale_and_rank(list)` |
| 北向/港股通 | `get_north_finance_change(period)` `get_hkt_statistics(s)` `get_hkt_details(s)` |
| 产品 | `get_product_share(code,idx)` `get_product_asset_value(code,idx)` `get_product_init_share(code)` |
| 历史交易 | `get_tradedatafromerds(atype,aid,st,ed)` |
| 复权 | `get_divid_factors(code,date)` |
| 文件导入 | `load_stk_list(dir,name)` `load_stk_vol_list(dir,name)` |
| 订阅 | `subscribe_quote(...)` `subscribe_whole_quote(...)` `unsubscribe_quote(id)` `get_all_subscription()` |
| 定时 | `run_time(func,days,time,ex)` `schedule_run(func,ts,repeat,interval,name)` `cancel_schedule_run(key)` |
| 回测设置 | `set_slippage(...)` `get_slippage()` `set_commission(...)` `get_commission()` |
| 绘图 | `paint(...)` `draw_text(...)` `draw_vertline(...)` `draw_icon(...)` `draw_number(...)` `get_function_line()` |
| 其他 | `get_his_st_data(s)` `get_his_index_data(s)` `get_ETF_list(m,s,types)` `get_function_line()` |

---

## 17. 关键参数约定

| 参数 | 取值 | 说明 |
|------|------|------|
| `period` | `'tick'`/`'1m'`/`'5m'`/`'30m'`/`'1d'`/`'follow'` | K 线周期；`'follow'`=跟随主图 |
| `period`（get_close_price 第4参） | 毫秒数 | `'1d':86400000, '1m':60000, '5m':300000, '15m':900000, '30m':1800000, '60m':3600000` |
| `dividend_type` | `'front_ratio'`/`'front'`/`'none'`/`'follow'` | 前复权/不复权/跟随主图（两版本均验证可用） |
| `fill_data` | `True`/`False` | 是否填充缺失 K 线 |
| `subscribe` | `False` | 回测/历史数据获取时设 False，不订阅行情 |
| `style` | `'fix'`/`'FIX'` | 限价单（大小写均可） |
| `opType` | `23`=买入，`24`=卖出 | passorder 操作类型 |
| `orderType` | `1101` | 股票 |
| `report_type` | `'report_time'`/`'announce_time'` | 财务数据报告期/公告期 |
| `data_type`（get_trade_detail_data） | `'account'`/`'position'`/`'order'`/`'deal'` | 大小写均可（`'POSITION'` 验证可用） |

---

## 18. 典型调用模式（从参考工程提炼）

### 18.1 标准调仓流程
```python
def handlebar(ContextInfo):
    d = ContextInfo.barpos
    bar_date = timetag_to_datetime(ContextInfo.get_bar_timetag(d), '%Y%m%d%H%M%S')

    # 1. 批量取行情（一次调用取全池）
    market_data = ContextInfo.get_market_data_ex(
        ['open'], ContextInfo.s, end_time=bar_date, period='1d', count=1,
        dividend_type='front_ratio', fill_data=True, subscribe=False)

    # 2. 计算信号 → buy/sell 字典 {代码: 0/1}

    # 3. 卖出
    if ContextInfo.holdings[k] > 0 and sells[k] == 1:
        order_shares(k, -shares, 'fix', open_price, ContextInfo, ContextInfo.accountID)

    # 4. 买入（整手计算）
    shares = int(money_dist / open_price) // 100 * 100
    order_shares(k, shares, 'fix', open_price, ContextInfo, ContextInfo.accountID)
```

### 18.2 一次性批量取数提速（参考出处：test.py）
```python
# 股票池 ∪ 持仓，一次 get_market_data_ex 取所有标的，避免循环内逐只请求
all_stocks = list(set(C.stock_pool) | set(holdings.keys()))
market_data = C.get_market_data_ex(['close'], all_stocks, end_time=bar_date,
                                   period=C.period, count=max(C.line1, C.line2) + 1,
                                   subscribe=False)
```

### 18.3 指定时间戳取价（对冲/相对强弱，参考出处：A策略.py）
```python
period_ms = {'1d':86400000, '1m':60000, '5m':300000, '15m':900000, '30m':1800000, '60m':3600000}
now = ContextInfo.get_bar_timetag(ContextInfo.barpos)
hold_start = ContextInfo.get_bar_timetag(ContextInfo.barpos - ContextInfo.HoldCircle)
stock_now = ContextInfo.get_close_price(ContextInfo.market, ContextInfo.stockcode, now, period_ms[ContextInfo.period])
stock_then = ContextInfo.get_close_price(ContextInfo.market, ContextInfo.stockcode, hold_start, period_ms[ContextInfo.period])
rel_change = (stock_now - stock_then) / stock_then   # 持仓期间个股涨跌幅
```

### 18.4 机器学习取数（参考出处：机器学习回测示例.py）
```python
# 训练集：按日期区间取整段K线 → DataFrame
df = ContextInfo.get_market_data(['open','high','low','close','volume'],
                                 stock_code=[ContextInfo.stock],
                                 start_time='20160101', end_time='20170101',
                                 dividend_type='front').sort_index()
# 预测特征：按 count 取最近N根
feat = ContextInfo.get_market_data(['open','high','low','close','volume'],
                                   stock_code=[ContextInfo.stock],
                                   end_time=end_date, count=15, skip_paused=False,
                                   dividend_type='front').sort_index()
```

### 18.5 交易成本估算（参考出处：multi_factor.py、bolling 策略）
```python
sell_fee = max(0.0001 * open_price * shares, 5) + 0.00001 * open_price * shares + 0.0005 * open_price * shares
buy_fee = max(0.0001 * open_price * shares, 5) + 0.00001 * open_price * shares
```

### 18.6 T+1 规则控制（参考出处：bollinger_band_strategy_5m.py、resonance_strategy.py）
```python
ContextInfo.buy_date[k] = current_date          # 买入时记录日期
if k in ContextInfo.buy_date and ContextInfo.buy_date[k] == current_date:
    can_sell = False    # 当日买入不可卖
```

### 18.7 因子选股（参考出处：multi_factor.py、demo.py）
```python
factor1[k] = ext_data('atr', k[-2:] + k[0:6], 0, ContextInfo)
factor2[k] = ext_data('adtm', k[-2:] + k[0:6], 0, ContextInfo)
norm1 = stats.zscore(list(factor1.values()))
rank_total = {k: 0.5 * norm1[i] - 0.5 * norm2[i] for ...}
sorted_stocks = sorted(rank_total.items(), key=lambda x: x[1], reverse=True)
selected = [s[0] for s in sorted_stocks[:5]]
```

### 18.8 指标计算（参考出处：bolling 策略，pandas 实现）
```python
def calculate_boll(close_series, window=20):
    ma = close_series.rolling(window).mean()
    std = close_series.rolling(window).std()
    return ma, ma + 2 * std, ma - 2 * std

def calculate_macd(close_series, fast=12, slow=26, signal=9):
    ema_fast = close_series.ewm(span=fast, adjust=False).mean()
    ema_slow = close_series.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    return dif, dea, (dif - dea) * 2

def calculate_kdj(high, low, close, n=9, m1=3, m2=3):
    lowest_low = low.rolling(n).min()
    highest_high = high.rolling(n).max()
    rsv = (close - lowest_low) / (highest_high - lowest_low) * 100
    k = rsv.ewm(alpha=1/m1, adjust=False).mean()
    d = k.ewm(alpha=1/m2, adjust=False).mean()
    return k, d, 3 * k - 2 * d
```

---

## 19. 文件与运行约定

- 策略文件头部使用 `#coding:gbk`（参考工程统一约定，`_PyContextInfo.py` 为 `#coding:utf-8`）。
- 回测资金账户 ID 常用 `'testS'` 或 `'test'`；实盘替换为券商资金账号。
- 回测时间在 QMT 界面上设置；也可在 `init` 中显式指定：`ContextInfo.start = '2025-10-01 00:00:00'`、`ContextInfo.end = '2025-12-31 00:00:00'`。
- 实盘模式下 `ContextInfo.do_back_test` 为 False，此时才执行 `paint` 绘图。
- 依赖库：`pandas`、`numpy`、`scipy.stats`、`sklearn`、`statsmodels`（QMT 内置环境已含 sklearn/statsmodels，机器学习/ARIMA 示例可直接运行）。
- 参考工程中交易/持仓状态用 `ContextInfo` 挂载属性跨 K 线保存（`ContextInfo.holdings`、`ContextInfo.money` 等）。
- 周期毫秒映射字典（A策略.py）：`{'1d':86400000,'1m':60000,'5m':300000,'15m':900000,'30m':1800000,'60m':3600000}`。
- `timetag_to_datetime` 输入为**毫秒**时间戳，内部先 `/1000` 再格式化。

## 20. 与 miniQMT（xtquant）的区别

| 维度 | QMT 内置（本文件） | miniQMT（xtquant，见 xtdata.md / xttrader.md） |
|------|-------------------|----------------------------------------------|
| 入口 | `init`/`handlebar` 回调 + 全局函数 | `xtdata`/`XtQuantTrader` 类实例方法 |
| 下单 | `order_shares`/`passorder` | `order_stock`（XtQuantTrader） |
| 行情 | `ContextInfo.get_market_data_ex` | `xtdata.get_market_data_ex` |
| 运行环境 | QMT 内置 Python（版本受限） | 外部 Python（任意版本） |
