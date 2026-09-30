---
name: qmt
description: "QMT开发工程师 - 迅投QMT量化交易终端Python策略开发、回测与实盘交易，支持A股/期货/期权全品种。当用户要求编写QMT策略、QMT量化策略、迅投QMT策略、QMT回测、QMT实盘交易代码、QMT选股策略、QMT技术指标策略时必须调用此技能。"
version: 1.5.0
homepage: http://dict.thinktrader.net/freshman/rookie.html
metadata: {"clawdbot":{"emoji":"🖥️","requires":{"bins":["python3"]}}}
agent_created: true
---

# QMT开发工程师（迅投量化交易终端）

[QMT](http://www.thinktrader.net)（Quant Market Trading）是迅投科技开发的专业量化交易平台。提供完整的桌面客户端，内置Python策略开发、回测引擎和实盘交易功能，支持中国证券市场全品种。

> ⚠️ **需要通过券商开通QMT权限**。QMT仅在Windows上运行。可通过国金、华鑫、中泰、东方财富等券商获取。

> 📚 **API 库参考（必读）**：编写策略时请先查阅 [`references/qmt_api_reference.md`](references/qmt_api_reference.md) — 该文件从真实 QMT 策略工程（`D:\WorkSpace\Myrepo\quant` + `D:\WorkSpace\softwares\QMT_test\国金QMT交易端模拟\python`）归纳整理了全部内置 API 接口的**实际签名、参数约定、返回值与典型调用模式**，含：
> - ContextInfo **完整方法索引**（官方封装 `_PyContextInfo.py` 全量约 100 个接口，覆盖行情/财务/期权/期货/订阅/定时/回测设置/绘图）
> - `get_market_data` 返回类型规则（标量/Series/DataFrame/Panel 随参数组合变化）、`get_financial_data` 新旧两种调用方式
> - 交易：`passorder`、`order_shares`、`get_trade_detail_data`、`ext_data`/`ext_data_rank`、交易对象字段、代码格式转换、T+1 与手续费处理
> - 高级接口：`subscribe_quote` 行情订阅、`schedule_run` 定时任务、`bsm_price`/`bsm_iv` 期权定价、`get_close_price` 指定时间戳取价等
> 本文档仅列核心用法，细节以 API 库为准。

## 两种运行模式

| 模式 | 说明 |
|---|---|
| **QMT（完整版）** | 完整桌面GUI，内置Python编辑器、图表和回测引擎 |
| **miniQMT** | 极简模式 — 通过外部Python使用xtquant SDK（参见 `miniqmt` skill） |

## 内置Python策略框架

QMT提供事件驱动策略框架，内置Python运行时（类似聚宽/米筐）。

### 策略生命周期

```python
def init(ContextInfo):
    """初始化函数 - 策略启动时调用一次，用于设置股票池和参数"""
    ContextInfo.set_universe(['000001.SZ', '600519.SH'])

def handlebar(ContextInfo):
    """K线处理函数 - 每根K线触发一次（tick/1m/5m/1d等），在此编写交易逻辑"""
    close = ContextInfo.get_market_data(['close'], stock_code='000001.SZ', period='1d', count=20)
    # 在此编写交易逻辑

def stop(ContextInfo):
    """停止函数 - 策略停止时调用"""
    pass
```

### 获取行情数据（内置）

```python
def handlebar(ContextInfo):
    # 获取最近20根K线的收盘价（旧接口；stock_code 传列表，返回 DataFrame，详见 API 库 §3.5）
    data = ContextInfo.get_market_data(
        ['open', 'high', 'low', 'close', 'volume'],
        stock_code=['000001.SZ'],
        period='1d',
        count=20
    )

    # ===== 批量获取多标的K线（参考工程最常用，推荐）=====
    bar_date = timetag_to_datetime(ContextInfo.get_bar_timetag(ContextInfo.barpos), '%Y%m%d%H%M%S')
    market_data = ContextInfo.get_market_data_ex(
        ['close'],                    # 字段列表
        ContextInfo.s,                # 股票代码列表，一次取全池
        end_time=bar_date,            # 截止时间
        period='1d',                  # 周期：'1d'/'30m'/'5m'
        count=20,
        dividend_type='front_ratio',  # 前复权
        fill_data=True,
        subscribe=False
    )
    # 返回 dict {代码: DataFrame}，用 .empty 判空、.tolist() 取值
    close_list = market_data['000001.SZ']['close'].tolist()

    # 获取历史数据（第4参是股票池索引0起，返回 {代码: [数值]})
    history = ContextInfo.get_history_data(20, '1d', 'close', 0)

    # 获取指数成分股（如沪深300）
    stocks = ContextInfo.get_sector('000300.SH')

    # 获取板块股票列表
    stocks = ContextInfo.get_stock_list_in_sector('沪深A股')

    # 获取财务数据（新式：字段列表+股票列表+起止日期，返回 DataFrame/Series；详见 API 库 §4.1）
    fin = ContextInfo.get_financial_data(
        ['CAPITALSTRUCTURE.total_capital'], ['000001.SZ'], '20230101', '20241231')
```

### 下单（内置）

```python
def handlebar(ContextInfo):
    # 限价买入100股，价格11.50（参考工程：第6参可传 accountID）
    order_shares('000001.SZ', 100, 'fix', 11.50, ContextInfo, ContextInfo.accountID)

    # 限价卖出100股，价格12.00（负数为卖出）
    order_shares('000001.SZ', -100, 'fix', 12.00, ContextInfo, ContextInfo.accountID)

    # 按目标金额买入（10万元）
    order_target_value('000001.SZ', 100000, 'fix', 11.50, ContextInfo)

    # 通用下单 passorder（23买/24卖，1101=股票，参考工程推荐用法）
    passorder(23, 1101, ContextInfo.accountID, '000001.SZ', 5, -1, 100, ContextInfo)

    # 撤单
    cancel('order_id', ContextInfo)
```

### 查询持仓与账户

```python
def handlebar(ContextInfo):
    # 获取持仓信息（注意：完整代码需拼接交易所后缀，见API库§7.2）
    positions = get_trade_detail_data('your_account', 'stock', 'position')
    for pos in positions:
        print(pos.m_strInstrumentID, pos.m_nVolume, pos.m_dInstrumentValue)

    # 获取委托信息
    orders = get_trade_detail_data('your_account', 'stock', 'order')

    # 获取账户资产信息
    account = get_trade_detail_data('your_account', 'stock', 'account')
```

## 回测

QMT内置回测引擎：

1. 在内置Python编辑器中编写策略
2. 设置回测参数（日期范围、初始资金、手续费、滑点）
3. 点击"运行回测"
4. 查看结果：资金曲线、最大回撤、夏普比率、交易记录

### 回测参数设置

```python
def init(ContextInfo):
    ContextInfo.capital = 1000000          # 初始资金
    ContextInfo.set_commission(0.0003)     # 手续费率
    ContextInfo.set_slippage(0.01)         # 滑点
    ContextInfo.set_benchmark('000300.SH') # 基准指数
```

## 完整示例：双均线策略

```python
import numpy as np

def init(ContextInfo):
    ContextInfo.stock = '000001.SZ'
    ContextInfo.set_universe([ContextInfo.stock])
    ContextInfo.fast = 5    # 快速均线周期
    ContextInfo.slow = 20   # 慢速均线周期

def handlebar(ContextInfo):
    stock = ContextInfo.stock
    bar_date = timetag_to_datetime(ContextInfo.get_bar_timetag(ContextInfo.barpos), '%Y%m%d%H%M%S')
    # 获取最近slow+1根K线的收盘价（参考工程用法：get_market_data_ex 返回 {code: DataFrame}）
    data = ContextInfo.get_market_data_ex(
        ['close'], [stock], end_time=bar_date, period='1d',
        count=ContextInfo.slow + 1, dividend_type='front_ratio',
        fill_data=True, subscribe=False)

    if stock not in data or data[stock].empty:
        return
    closes = data[stock]['close'].tolist()
    if len(closes) < ContextInfo.slow:
        return  # 数据不足，跳过

    # 计算当前和前一根K线的快慢均线值
    ma_fast = np.mean(closes[-ContextInfo.fast:])
    ma_slow = np.mean(closes[-ContextInfo.slow:])
    prev_fast = np.mean(closes[-ContextInfo.fast-1:-1])
    prev_slow = np.mean(closes[-ContextInfo.slow-1:-1])

    # 查询当前持仓
    positions = get_trade_detail_data(ContextInfo.accID, 'stock', 'position')
    holding = any(p.m_strInstrumentID == stock and p.m_nVolume > 0 for p in positions)

    # 金叉信号：快速均线上穿慢速均线，买入
    if prev_fast <= prev_slow and ma_fast > ma_slow and not holding:
        order_shares(stock, 1000, 'fix', closes[-1], ContextInfo)

    # 死叉信号：快速均线下穿慢速均线，卖出
    elif prev_fast >= prev_slow and ma_fast < ma_slow and holding:
        order_shares(stock, -1000, 'fix', closes[-1], ContextInfo)
```


## 数据覆盖范围

| 类别 | 内容 |
|---|---|
| **股票** | A股（沪、深、北交所）、港股通 |
| **指数** | 所有主要指数 |
| **期货** | 中金所、上期所、大商所、郑商所、能源中心、广期所 |
| **期权** | ETF期权、股票期权、商品期权 |
| **ETF** | 所有交易所交易基金 |
| **债券** | 可转债、国债 |
| **周期** | Tick、1分钟、5分钟、15分钟、30分钟、1小时、日、周、月 |
| **Level 2** | 逐笔委托、逐笔成交（取决于券商权限） |
| **财务** | 资产负债表、利润表、现金流量表、关键指标 |

## QMT vs miniQMT vs Ptrade 对比

| 特性 | QMT | miniQMT | Ptrade |
|---|---|---|---|
| **厂商** | 迅投科技 | 迅投科技 | 恒生电子 |
| **Python** | 内置（版本受限） | 外部（任意版本） | 内置（版本受限） |
| **界面** | 完整GUI | 极简 | 完整（网页端） |
| **回测** | 内置 | 需自行实现 | 内置 |
| **部署** | 本地 | 本地 | 券商服务器（云端） |
| **外网访问** | 支持 | 支持 | 不支持（仅内网） |

## 使用技巧

- QMT仅在**Windows**上运行。
- 内置Python版本由QMT固定，无法安装任意pip包（参考工程使用 pandas/numpy/scipy，均内置）。
- 策略文件头部统一 `#coding:gbk`。
- 股票代码格式：行情/下单用 `6位代码.交易所`（`'600886.SH'`/`'000001.SZ'`）；扩展数据用 `交易所前缀+6位代码`（`'SH600886'`），转换方式 `k[-2:] + k[0:6]`。
- 回测资金账户ID常用 `'testS'`/`'test'`；实盘替换为券商资金账号。
- 批量行情**优先用 `get_market_data_ex` 一次取全池**，避免循环内逐只请求导致缓慢。
- A股**整手**交易：`vol = int(cash / price / 100) * 100`。
- **T+1** 规则：记录买入日期 `ContextInfo.buy_date[code] = current_date`，当日买入不可卖出。
- 手续费估算：买入=佣金(最低5元)+过户费，卖出另加印花税（见 API 库 §10.3）。
- 如需不受限的Python环境，使用**miniQMT**模式配合`xtquant` SDK（见 xtdata.md / xttrader.md）。
- 策略文件存储在QMT安装目录中。
- 文档：http://dict.thinktrader.net/freshman/rookie.html
- 也支持VBA接口用于Excel集成。

---

## 进阶示例

> ⚠️ **行情获取提示**：以下进阶示例为教学简化写法。实际开发中：
> - 批量取多标的行情统一使用 `ContextInfo.get_market_data_ex`（返回 `{代码: DataFrame}`），见 [API 库 §3.5](references/qmt_api_reference.md)，可一次取全池避免逐只请求。
> - `ContextInfo.get_history_data(count, period, field, index)` 第4参为**股票池索引**，返回 `{代码: [数值]}` 字典，需按代码取值，不能直接当 list 用。

### 多股票轮动策略

```python
import numpy as np

def init(ContextInfo):
    # 设置股票池：银行龙头股
    ContextInfo.stock_pool = ['601398.SH', '601939.SH', '601288.SH', '600036.SH', '601166.SH']
    ContextInfo.set_universe(ContextInfo.stock_pool)
    ContextInfo.hold_num = 2  # 最多持有2只股票

def handlebar(ContextInfo):
    # 计算每只股票的20日收益率
    momentum = {}
    for stock in ContextInfo.stock_pool:
        closes = ContextInfo.get_history_data(21, '1d', 'close', stock_code=stock)
        if len(closes) >= 21:
            ret = (closes[-1] - closes[0]) / closes[0]  # 20日收益率
            momentum[stock] = ret

    # 按动量排序，选择前N只股票
    sorted_stocks = sorted(momentum.items(), key=lambda x: x[1], reverse=True)
    target_stocks = [s[0] for s in sorted_stocks[:ContextInfo.hold_num]]

    # 获取当前持仓
    positions = get_trade_detail_data(ContextInfo.accID, 'stock', 'position')
    holding = {p.m_strInstrumentID: p.m_nVolume for p in positions if p.m_nVolume > 0}

    # 卖出不在目标列表中的股票
    for stock, vol in holding.items():
        if stock not in target_stocks:
            closes = ContextInfo.get_history_data(1, '1d', 'close', stock_code=stock)
            if len(closes) > 0:
                order_shares(stock, -vol, 'fix', closes[-1], ContextInfo)

    # 买入目标股票
    account = get_trade_detail_data(ContextInfo.accID, 'stock', 'account')
    if account:
        cash = account[0].m_dAvailable
        per_stock_cash = cash / ContextInfo.hold_num  # 等权分配
        for stock in target_stocks:
            if stock not in holding:
                closes = ContextInfo.get_history_data(1, '1d', 'close', stock_code=stock)
                if len(closes) > 0 and closes[-1] > 0:
                    vol = int(per_stock_cash / closes[-1] / 100) * 100  # 向下取整到整手
                    if vol >= 100:
                        order_shares(stock, vol, 'fix', closes[-1], ContextInfo)
```


### RSI策略

```python
import numpy as np

def init(ContextInfo):
    ContextInfo.stock = '000001.SZ'
    ContextInfo.set_universe([ContextInfo.stock])
    ContextInfo.rsi_period = 14     # RSI周期
    ContextInfo.oversold = 30       # 超卖阈值
    ContextInfo.overbought = 70     # 超买阈值

def handlebar(ContextInfo):
    stock = ContextInfo.stock
    closes = ContextInfo.get_history_data(ContextInfo.rsi_period + 2, '1d', 'close', stock_code=stock)

    if len(closes) < ContextInfo.rsi_period + 1:
        return

    # 计算RSI
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-ContextInfo.rsi_period:])
    avg_loss = np.mean(losses[-ContextInfo.rsi_period:])

    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    # 查询持仓
    positions = get_trade_detail_data(ContextInfo.accID, 'stock', 'position')
    holding = any(p.m_strInstrumentID == stock and p.m_nVolume > 0 for p in positions)

    # RSI超卖 — 买入
    if rsi < ContextInfo.oversold and not holding:
        order_shares(stock, 1000, 'fix', closes[-1], ContextInfo)

    # RSI超买 — 卖出
    elif rsi > ContextInfo.overbought and holding:
        order_shares(stock, -1000, 'fix', closes[-1], ContextInfo)
```

### 布林带策略

```python
import numpy as np

def init(ContextInfo):
    ContextInfo.stock = '600519.SH'
    ContextInfo.set_universe([ContextInfo.stock])
    ContextInfo.boll_period = 20    # 布林带周期
    ContextInfo.boll_std = 2        # 标准差倍数

def handlebar(ContextInfo):
    stock = ContextInfo.stock
    closes = ContextInfo.get_history_data(ContextInfo.boll_period + 1, '1d', 'close', stock_code=stock)

    if len(closes) < ContextInfo.boll_period:
        return

    # 计算布林带
    recent = closes[-ContextInfo.boll_period:]
    mid = np.mean(recent)                          # 中轨
    std = np.std(recent)                           # 标准差
    upper = mid + ContextInfo.boll_std * std       # 上轨
    lower = mid - ContextInfo.boll_std * std       # 下轨
    price = closes[-1]                             # 当前价格

    positions = get_trade_detail_data(ContextInfo.accID, 'stock', 'position')
    holding = any(p.m_strInstrumentID == stock and p.m_nVolume > 0 for p in positions)

    # 价格触及下轨 — 买入
    if price <= lower and not holding:
        order_shares(stock, 1000, 'fix', price, ContextInfo)

    # 价格触及上轨 — 卖出
    elif price >= upper and holding:
        order_shares(stock, -1000, 'fix', price, ContextInfo)
```

## 定时任务

```python
def init(ContextInfo):
    ContextInfo.stock = '000001.SZ'
    ContextInfo.set_universe([ContextInfo.stock])

def handlebar(ContextInfo):
    import datetime
    now = ContextInfo.get_bar_timetag(ContextInfo.barpos)
    dt = datetime.datetime.fromtimestamp(now / 1000)
    # 仅在每変14:50执行调仓逻辑
    if dt.hour == 14 and dt.minute == 50:
        pass  # 执行调仓
```

## 常见错误处理

| 错误 | 原因 | 解决方法 |
|------|------|----------|
| 账户未登录 | QMT未连接券商 | 检查QMT登录状态，确认券商账户已连接 |
| 委托失败 | 资金不足或超出涨跌停 | 检查可用资金和委托价格 |
| 数据为空 | 股票代码错误或停牌 | 校验代码格式（如`000001.SZ`），检查是否停牌 |
| Python版本不兼容 | 内置Python版本受限 | 改用miniQMT模式 |
| 策略运行缓慢 | 数据量过大 | 减少`get_history_data`的count参数 |

## 内置函数参考

> 📚 完整 API 库（实际签名、参数、返回值、代码格式约定、交易字段、典型调用模式）见 [`references/qmt_api_reference.md`](references/qmt_api_reference.md)，以下为核心速查。

### 行情数据函数

| 函数 | 说明 | 返回值 |
|------|------|--------|
| `ContextInfo.get_market_data_ex(fields, stock_list, end_time, period, count, dividend_type, fill_data, subscribe)` | **批量获取多标的K线（核心）** | dict {代码: DataFrame} |
| `ContextInfo.get_market_data(fields, stock_code, period, count)` | 获取单标的K线数据 | dict/DataFrame |
| `ContextInfo.get_history_data(count, period, field, index)` | 获取历史数据序列，第4参为股票池索引 | dict {代码: list} |
| `ContextInfo.get_sector(index_code)` | 获取指数成分股（如`'000300.SH'`） | list |
| `ContextInfo.get_stock_list_in_sector(sector)` | 获取板块成分股（如`'沪深A股'`） | list |
| `ContextInfo.get_bar_timetag(barpos)` | 获取K线时间戳（毫秒） | int |
| `ContextInfo.get_financial_data(fieldList, stockList, startDate, endDate, report_type)` | 财务数据（新式：字段列表+股票列表+起止日期；旧式：表名,字段名,market,code,barpos→单值） | Series/DataFrame/Panel 或单值 |
| `ContextInfo.get_instrument_detail(stock_code)` | 获取合约详情（30字段） | dict |
| `ContextInfo.get_full_tick(stock_list)` | 获取全推行情快照 | dict |
| `ContextInfo.get_total_asset()` | 获取当前总资产 | float |
| `ContextInfo.get_close_price(market, code, timetag, period_ms, dividType)` | 指定时间戳收盘价（period为毫秒） | float |
| `ContextInfo.get_turnover_rate(stock_list, start, end)` | 批量换手率 | DataFrame |
| `ContextInfo.get_risk_free_rate(barpos)` | 无风险利率（年化百分数） | float |
| `ContextInfo.get_trading_dates(code, s, e, count, period)` | 交易日列表 | list |
| `ContextInfo.get_local_data(...)` | 本地K线数据（不订阅） | dict |
| `timetag_to_datetime(timetag, fmt)` | 时间戳转日期字符串（如`'%Y%m%d%H%M%S'`） | str |
| `download_history_data(stock, period, start, end)` | 下载历史数据（如`'1d','20230101','20241231'`） | None |
| `ext_data(name, code, i, ContextInfo)` | 获取扩展数据/自建因子（code格式`'SH600886'`） | float |
| `ext_data_rank(name, code, i, ContextInfo)` | 获取扩展数据排名 | float |

### 交易函数

| 函数 | 说明 |
|------|------|
| `order_shares(code, volume, style, price, ContextInfo, accountID)` | 按股数下单（正买负卖，参考工程第6参传accountID） |
| `order_target_value(code, value, style, price, ContextInfo)` | 按目标市值下单 |
| `order_lots(code, lots, style, price, ContextInfo)` | 按手数下单 |
| `order_percent(code, percent, style, price, ContextInfo)` | 按组合比例下单 |
| `passorder(opType, orderType, accountid, code, prType, price, volume, ContextInfo)` | 通用下单：opType 23买/24卖，orderType 1101股票 |
| `cancel(order_id, ContextInfo)` | 撤单 |
| `get_trade_detail_data(account, market, data_type)` | 查询交易数据（account/position/order/deal） |

### 绘图函数

| 函数 | 说明 |
|------|------|
| `ContextInfo.paint(name, value, -1, 0, 'noaxis')` | 绘制指标线/净值曲线（实盘模式下 `not do_back_test` 时调用；第5参可选`'noaxis'`/`'nodraw'`） |
| `ContextInfo.draw_text(cond, pos, '文字')` | 图上标注文字（如买入'开'/卖出'平'） |
| `ContextInfo.draw_vertline(cond, p1, p2, color)` | 绘制竖线 |
| `ContextInfo.draw_icon(cond, pos, type)` | 绘制图标（type为编号） |
| `ContextInfo.draw_number(cond, price, num, precision)` | 数字标注 |

### 行情订阅与定时任务

| 函数 | 说明 |
|------|------|
| `ContextInfo.subscribe_quote(code, period, dividend_type, result_type, callback)` | 订阅单标的K线推送，返回subID；result_type: 'dict'/'list'/默认DataFrame |
| `ContextInfo.subscribe_whole_quote(code_list, callback)` | 全推订阅一篮子标的 |
| `ContextInfo.unsubscribe_quote(subID)` | 退订 |
| `ContextInfo.schedule_run(func, time_point, repeat_times, interval, name)` | 定时任务（time_point支持datetime或'%Y%m%d%H%M%S'，interval为timedelta） |
| `ContextInfo.cancel_schedule_run(key)` | 取消定时任务 |
| `ContextInfo.run_time(funcname, intervalday, time, exchange)` | 旧式定时运行（如`run_time('f', 1, '14:50')`） |

### 回测设置与期权

| 函数 | 说明 |
|------|------|
| `ContextInfo.set_slippage(True, '0.001')` / `get_slippage()` | 设置/查询滑点 |
| `ContextInfo.set_commission(0, '0.0003')` / `get_commission()` | 设置/查询手续费 |
| `ContextInfo.get_option_list('510050.SH', '202603', 'C', True)` | 期权列表（标的,到期,类型C/P,仅可交易） |
| `ContextInfo.bsm_price('C', price, strike, rf, sigma, days)` | BSM期权定价 |
| `ContextInfo.bsm_iv('C', price, strike, opt_price, rf, days)` | 隐含波动率 |
| `ContextInfo.get_main_contract(market)` | 期货主力合约（如'SHFE'） |

### 交易数据类型

| data_type | 说明 | 常用字段 |
|-----------|------|----------|
| `'position'` | 持仓 | `m_strInstrumentID`（代码，不含后缀）, `m_strExchangeID`（交易所）, `m_strInstrumentName`（名称）, `m_nVolume`（数量）, `m_dOpenPrice`（成本价）, `m_dLastPrice`（最新价）, `m_dInstrumentValue`（市值）, `m_dPositionProfit`（持仓盈亏） |
| `'order'` | 委托 | `m_strOrderSysID`（委托号）, `m_nVolumeTraded`（成交量）, `m_dLimitPrice`（委托价） |
| `'deal'` | 成交 | `m_strTradeID`（成交号）, `m_dPrice`（成交价）, `m_nVolume`（成交量） |
| `'account'` | 账户 | `m_dAvailable`（可用资金）, `m_dBalance`（总资产）, `m_dInstrumentValue`（持仓市值） |

> ⚠️ 持仓代码拼接：`m_strInstrumentID` 不含交易所后缀，完整代码需 `i.m_strInstrumentID + '.' + i.m_strExchangeID`（如 `'000001' + '.' + 'SZ'` → `'000001.SZ'`）。

## 进阶示例：MACD策略

```python
import numpy as np

def init(ContextInfo):
    ContextInfo.stock = '600519.SH'
    ContextInfo.set_universe([ContextInfo.stock])

def handlebar(ContextInfo):
    stock = ContextInfo.stock
    closes = ContextInfo.get_history_data(60, '1d', 'close', stock_code=stock)
    if len(closes) < 35:
        return
    closes = np.array(closes, dtype=float)

    def ema(data, period):
        result = np.zeros_like(data)
        result[0] = data[0]
        k = 2 / (period + 1)
        for i in range(1, len(data)):
            result[i] = data[i] * k + result[i-1] * (1 - k)
        return result

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    dif = ema12 - ema26
    dea = ema(dif, 9)

    positions = get_trade_detail_data(ContextInfo.accID, 'stock', 'position')
    holding = any(p.m_strInstrumentID == stock and p.m_nVolume > 0 for p in positions)

    # 金叉：DIF上穿DEA
    if dif[-2] <= dea[-2] and dif[-1] > dea[-1] and not holding:
        order_shares(stock, 1000, 'fix', closes[-1], ContextInfo)
    # 死叉：DIF下穿DEA
    elif dif[-2] >= dea[-2] and dif[-1] < dea[-1] and holding:
        order_shares(stock, -1000, 'fix', closes[-1], ContextInfo)
```

## 进阶示例：止盈止损策略

```python
import numpy as np

def init(ContextInfo):
    ContextInfo.stock = '000001.SZ'
    ContextInfo.set_universe([ContextInfo.stock])
    ContextInfo.entry_price = 0
    ContextInfo.stop_loss = 0.05      # 止损5%
    ContextInfo.take_profit = 0.10    # 止盈10%

def handlebar(ContextInfo):
    stock = ContextInfo.stock
    closes = ContextInfo.get_history_data(21, '1d', 'close', stock_code=stock)
    if len(closes) < 21:
        return
    price = closes[-1]
    ma20 = np.mean(closes[-20:])

    positions = get_trade_detail_data(ContextInfo.accID, 'stock', 'position')
    pos = None
    for p in positions:
        if p.m_strInstrumentID == stock and p.m_nVolume > 0:
            pos = p
            break

    if pos is None:
        if price > ma20:
            order_shares(stock, 1000, 'fix', price, ContextInfo)
            ContextInfo.entry_price = price
    else:
        if ContextInfo.entry_price > 0:
            pnl = (price - ContextInfo.entry_price) / ContextInfo.entry_price
            if pnl <= -ContextInfo.stop_loss:
                order_shares(stock, -pos.m_nVolume, 'fix', price, ContextInfo)
                ContextInfo.entry_price = 0
            elif pnl >= ContextInfo.take_profit:
                order_shares(stock, -pos.m_nVolume, 'fix', price, ContextInfo)
                ContextInfo.entry_price = 0
```

---

---

## 🤖 AI Agent 高阶使用指南

对于 AI Agent，在使用该量化/数据工具时应遵循以下高阶策略和最佳实践，以确保任务的高效完成：

### 1. 数据校验与错误处理
在获取数据或执行操作后，AI 应当主动检查返回的结果格式是否符合预期，以及是否存在缺失值（NaN）或空数据。
* **示例策略**：在通过 API 获取数据框（DataFrame）后，使用 `if df.empty:` 进行校验；捕获 `Exception` 以防网络或接口错误导致进程崩溃。

### 2. 多步组合分析
AI 经常需要进行宏观经济分析或跨市场对比。应善于将当前接口与其他数据源或工具组合使用。
* **示例策略**：先获取板块或指数的宏观数据，再筛选成分股，最后对具体标的进行深入的财务或技术面分析，形成完整的决策链条。

### 3. 构建动态监控与日志
对于交易和策略类任务，AI 可以定期拉取数据并建立监控机制。
* **示例策略**：使用循环或定时任务检查特定标的的异动（如涨跌停、放量），并在发现满足条件的信号时输出结构化日志或触发预警。

---

## 社区与支持

由 **大佬量化** 维护 — 量化交易教学与策略研发团队。

微信客服: **bossquant1** · [Bilibili](https://space.bilibili.com/48693330) · 搜索 **大佬量化** — 微信公众号 / Bilibili / 抖音
