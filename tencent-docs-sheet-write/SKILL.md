---
name: tencent-docs-sheet-write
description: 向在线腾讯文档「表格」(tencentsheet) 定位并写入数据块。解决「宿主给的 tdoc file_id 带 300000000_ 假前缀导致 invalid file_id」「get_cell_data 不传范围只回 A1」「百分比列存储为小数」这几个高频坑。当用户说「把数据填到腾讯文档表格」「写进十渠表格/在线表格」「更新腾讯文档里的表」「@tdoc 引用表格」「把截图数据整理进在线表格」，或需要读/写 docs.qq.com/sheet 链接时使用。
agent_created: true
---

# 腾讯文档在线表格读写（sheet）

> 适用：腾讯文档**表格**（`docs.qq.com/sheet/...`，`ext=tencentsheet`）。
> **不是** Word/智能文档——那些走 `doc.*` / `smartcanvas.*`，混用报 `400016`。
> 底层是 `tencent-docs` 插件的 `tencentdocs.py`。先读该插件的 `SKILL.md` 与 `references/auth.md`。

## 0. 前置：鉴权

```bash
cd "<tencent-docs skill 目录>"
<python> tencentdocs.py tdoc_init
# READY            → 继续
# ERROR:no_token   → 连接器未启用。让用户在「连接器管理」启用腾讯文档，
#                    并【重开会话】——只点连接、不重开，当前会话常常仍拿不到票据。
```
票据由宿主注入，不落盘。Windows 下 `<python>` 用 managed 绝对路径；
该目录用 `cd &&` 链式调用，别依赖 bash 的 `dirname`（本机 shell 包装有 bug）。

## 0.5 传参：**绝对不要用 Windows PowerShell 直接传 JSON**

PowerShell 会把 JSON 里的双引号吞掉，中文还会 GBK 乱码。实测：

```powershell
# ❌ 这样传，脚本收到的是 {search_key:閲忓寲绛栫暐}（引号全丢 + 中文乱码）
<python> tencentdocs.py tdoc_call tencent-docs manage.search_file '{"search_key":"量化策略"}'
# → ERROR:bad_args_json：args 必须是合法的 JSON 对象字符串
```

✅ **正确做法：用本 skill 自带的 `scripts/td_call.py` + JSON 作业文件。**
它用 `subprocess(list)` 传参（Windows 下走 `CreateProcessW` + `list2cmdline`），
引号与中文都保真；还自动做两件必要的事：

1. 剥掉 `jsonrpc` 外壳，直接输出内层结果 —— 否则整个返回是一行超长 JSON，Read 会按 2000 字符截断，看不到内容
2. 把 `csv_data` 落成**真换行**的 `.csv` —— 否则 `\n` 是转义字符，整张表挤在一行

```bash
# jobs.json（UTF-8）：
# [ {"tool":"manage.search_file","args":{"search_key":"量化策略"}},
#   {"tool":"sheet.get_cell_data","args":{...,"return_csv":true}},
#   {"raw":["tdoc_init"]} ]          ← 顶层子命令用 raw
<python> scripts/td_call.py jobs.json
# → 读同目录的 _td_out.txt；csv 存成 _td_out_<调用序号>.csv（多行，可直接 Read）
```

> ⚠️ **`_td_out.txt` 每次运行都会被覆盖**，且 csv 文件名带的是**该调用在 jobs 数组里的
> 下标**（第 4 条调用 → `_td_out_3.csv`，不是固定 `_td_out_0.csv`）。
> **每跑一次就立刻读输出**，别「连跑两个 jobs 文件再一起读」——前一次的返回值会被后一次冲掉，
> 尤其是 `set_cell_style` 这类「只能靠 `error:""` 判定成功」的调用，丢了就无法事后确认。
> 若已经丢失：样式类调用是**幂等**的，重跑一次并当场读输出即可，不会叠加副作用。

> ⚠️ **子进程必须强制 UTF-8**（`td_call.py` 已内置）：Windows 下 `tencentdocs.py` 的 stdout
> 默认是 GBK，只要响应里出现 GBK 编不出的字符就会 `print(rsp)` 处抛
> `UnicodeEncodeError: 'gbk' codec can't encode character '\xa0'`，**整条调用白跑**且
> `_td_out.txt` 里只有 traceback。实测触发场景：读一张较长的表（返回体含**不间断空格
> `\xa0`**，通常是腾讯文档表格里的对齐填充）。脚本已设 `PYTHONIOENCODING=utf-8` +
> `PYTHONUTF8=1`；若手工调 `tencentdocs.py`，务必自己带上这两个环境变量。

> **瞬时网络故障**：偶发 `code:102 tcp client transport ReadFrame ... i/o timeout`。
> 这是隧道超时，**直接原样重试同一调用即可**，不要改参数、也不要以为是参数写错了。

> 一个 jobs 文件可放任意多条调用，**按顺序执行** —— 适合把
> 「读全表 → 批量写值 → 上色设格式 → 回读校验」一整轮串起来跑，省往返。

## 1. 拿到**真实** file_id（最容易翻车的一步）

宿主在 `@tdoc#...` 引用里给的 ID **可能带假前缀**，例如：

```
@tdoc#300000000_cLDQxcYTUyjb   ← 300000000_ 是壳，不是文档 ID 的一部分
真实 file_id = cLDQxcYTUyjb
```

带前缀直接调 `manage.query_file_info` 会返回：
`code:400001, msg:invalid file_id`。

**两种可靠的取法**（都走 `tencent-docs` service）：

```bash
# A. 按标题搜
tencentdocs.py tdoc_call tencent-docs manage.search_file '{"search_key":"量化策略"}'
#   → list[].file_id 是干净 ID；list[].ext=tencentsheet 说明是表格

# B. 按最近访问列表
tencentdocs.py tdoc_call tencent-docs manage.recent_online_file '{"num":1,"count":20,"order_by":1}'
#   注意：num 页码从 1 开始且【必填】；count 必须显式传 1~20。
#   不传或传 0 会被 MCP 层设成 100，然后被下游拒绝（count exceeds maximum value of 20）。
#   返回字段是 files[].file_id / file_name / file_url
```

> 顺手用 `ext` 判品类：`tencentsheet`→表格，`tencentdoc`→Word，`smartsheet`→智能表格。
> `file_url` 形如 `https://docs.qq.com/sheet/DY0xEUXhjWVRVeWpi` 可交叉验证。

## 2. 列出子表（sheet_id）

```bash
tencentdocs.py tdoc_call tencent-docs sheet.get_sheet_info '{"file_id":"<FID>"}'
# → sheets[].sheet_id / sheet_name / row_count / col_count
```
后续所有读写都要带 `sheet_id`。

## 3. 读内容 —— **必须显式传范围**

```bash
tencentdocs.py tdoc_call tencent-docs sheet.get_cell_data \
  '{"file_id":"<FID>","sheet_id":"<SID>",
    "start_row":0,"start_col":0,"end_row":200,"end_col":25,
    "return_csv":true}'
```

**坑**：不传 `start_row/.../end_col` 时，服务端依赖 `used_range`；当它为 `null`
（表格被清过、或数据不连续）**只会返回 A1 一个单元格**，看起来像"表格是空的"。
本机实测：一张有 60 行数据的表，不传范围只回 `RSRS` 一个词。

- `return_csv:true` → 拿 `csv_data` 字符串，适合整体扫一遍找落点
- `return_csv:false` → 拿 `cells[]` 结构化数据，**判断某列的真实存储类型时用这个**

读回来先写临时文件再用 Read 看，Python 里显式 `encoding='utf-8'`。
需要精确判断格式时，用 `repr(line)` 观察逗号/引号，别靠肉眼看截断输出。

## 4. 写入 —— 批量 + 对齐相邻块的格式

```bash
tencentdocs.py tdoc_call tencent-docs sheet.set_range_value \
  '{"file_id":"<FID>","sheet_id":"<SID>","values":[
     {"row":20,"col":1,"value_type":"STRING","string_value":"时间段"},
     {"row":21,"col":2,"value_type":"NUMBER","number_value":0.3187}
   ]}'
```
`values[]` 每项：`row`/`col`（0-based）、`value_type` ∈ NUMBER|STRING|BOOL|FORMULA，
配 `number_value` / `string_value` / `bool_value` / `formula`。
连续写 3 次以上必须用这个批量接口，别单条循环。

### ⚠️ 百分比列存的是**原始小数**
表格里显示 `41.00%`，存储层是 `number_value: 0.41`；显示 `173.20%` 存 `1.732`。
**写入必须传小数**（`0.4154` 而不是 `"41.54%"`），否则与同表其他数据块格式不一致，
后续排序/公式会错。**动手前先用 `return_csv:false` 读一行已有数据确认列的真实类型**
——这是对齐格式最稳的办法。

## 4.5 上色 / 设数字格式 —— **顺序不能反**

```bash
tencentdocs.py tdoc_call tencent-docs sheet.set_cell_style \
  '{"file_id":"<FID>","sheet_id":"<SID>",
    "start_row":21,"end_row":21,"start_col":1,"end_col":4,
    "font_color":"FFFF2323"}'
```
参数：`font_color` / `bg_color`（ARGB hex，如 `FFFF2323`）、`bold`、`italic`、
`font_size`、`number_format_pattern`（如 `0.00%`）、对齐等。
**支持范围**：同色/同格式的连续区域合并成一次调用，别逐格写。

### 🚨 头号坑：`set_cell_style` 是**整格覆盖式**写入
`font_color`、`bg_color`、`bold`、`number_format_pattern`、`horizontal_align` 全部落在
**同一个 cell style** 上。任何一次只传部分字段的调用，都会把**没传的字段重置成默认**（尤其是
`number_format_pattern` 和 `font_color` 互相抹掉）。

✅ **唯一稳妥做法：凡是要同时设颜色+数字格式+对齐的格子，把所有这些字段放进【同一次】
`set_cell_style` 调用里。** 不要分两次（先格式后颜色）调用——分两次时后一次会把前一次的字段冲掉，
现象就是「颜色上了又没」「百分比又变回裸小数」。本项目就因此返工过一次。

```jsonc
// 正确：一次调用同时带齐
{"file_id":"...","sheet_id":"...","start_row":21,"end_row":21,"start_col":2,"end_col":2,
 "number_format_pattern":"0.00%","font_color":"FFFF2323","horizontal_align":"center"}
```

> 分组技巧：同一列数字格式固定，按「同列内连续同色段」分组，每组一次调用带齐
> `number_format_pattern`(取该列格式) + `font_color`(该段颜色)。13 列×4 行约 26 次调用即可。
> **没有读样式的工具** —— `sheet.get_cell_style` 实测返回
> `-32601 工具没有注册`，确实不存在，无法回读校验，只能靠返回 `error:""` 判定成功。

### 实测有效的分组方法（13 列 × 4 行 = **15 次**调用）
不要逐列逐段盲切，先找**格式相同且颜色一致**的相邻列做矩形合并：

| 区域 | 内容 | 颜色 | 格式 | 次数 |
|---|---|---|---|---|
| `C4:C5` | 单位净值 + 下方差 | 恒定红 | `0.0000` | 1 |
| `C6:C9` | 信息比率~索提诺 | 恒定黑 | `0.00%` | 1 |
| `C12` | 跟踪误差 | 恒定红 | `0.0000` | 1 |
| `C13:C14` | 最大回撤 + 胜率 | 恒定黑 | `0.00%` | 1 |
| `C2 C3 C10 C11` | 符号驱动的 4 列 | 按**列内连续同色段**切 | 见格式表 | 11 |

### 观察：写入 NUMBER 后格式**通常已被继承**
本表实测：`set_range_value` 写完，回读 `csv` 已渲染成 `7.47%` / `1.0967`
（不是 `0.0747`），说明该区域继承了列或上方区块的格式。
**但 `set_cell_style` 仍必须带齐 `number_format_pattern`** —— 它是整格覆盖写，
不带就会把这层继承来的格式冲掉。

> 判断方法：写完先回读一次 `csv`。若已是 `41.00%` 这类渲染值 → 有格式在；
> 若看到 `0.41` → 该区域格式为空，后面 `set_cell_style` 千万别漏 `number_format_pattern`。

### ⚠️ 截图里的数字**显示口径可能和表里不一致**，别被带偏
实测同一张表的两个区块，截图来自不同来源：一个渲染成 `7.47%`（百分比格式），
另一个渲染成 `0.2190`（4 位小数裸数）。**两者的底层语义相同**（都是 21.90%），
**写入一律按「目标表的存储口径」= `NUMBER` + 小数**，不要照抄截图的显示形式。

判据：找一个**已知锚点列**（本表是「基准年化收益」——各周期固定值
`24.22% / -6.83% / -22.44% / -12.69%`）核对量级，锚点对上就说明小数/百分比口径没搞错。

### 从截图取色：用 PIL 逐像素，别靠肉眼猜
```python
# 装到隔离 venv，用该 venv 的 python.exe 跑（managed 主 python 无 PIL）
# <managed python> -m venv <...>/envs/default
# <...>/envs/default/Scripts/pip.exe install pillow
from PIL import Image
from collections import Counter
im = Image.open(path).convert('RGB')
cnt = Counter()
for y in range(h):
    for x in range(w):
        r,g,b = im.getpixel((x,y))
        if max(r,g,b) - min(r,g,b) > 40:   # 饱和 → 彩色字，滤掉黑白/灰
            cnt[(r,g,b)] += 1
print(cnt.most_common(8))   # 主色即红/绿值
```
再按列统计主导色分组（相邻同色列合并），**放大 3 倍目视复核**一遍。
A 股惯例：红=涨/正、绿=跌/负。常见取色值：红 `FFFF2323`、绿 `FF00B211`。

> ⚠️ 对齐前提：**先想清楚截图裁掉了哪一列**。本项目截图左侧「时间段」列被裁掉，
> 所以彩色列数（13）= 指标列数（13），不是表头总数（14）。数柱子前先做这个减法。

## 5. 标准作业顺序

1. `tdoc_init` → READY
2. 取真实 file_id（`search_file` 或 `recent_online_file`）
3. `get_sheet_info` → 定位 sheet_id
4. `get_cell_data` **带范围** 读全表，找到落点行，同时看清邻近块的列结构/类型
5. **用户确认行标签映射**——多个截图/多组数据对应哪些时间段，是最容易错的地方，
   拿不准就用 AskUserQuestion 问清楚，别猜
6. `get_cell_data` `return_csv:false` 读一行参照数据，确认存储类型
7. `set_range_value` 一次批量写入
8. **回读同一区域验证**，确认 `error:""` 且数值正确
9. 若要上色+设格式：**把 `number_format_pattern` 与 `font_color`（+对齐）放进同一次 `set_cell_style` 调用**（见 §4.5，绝不能分两次）
10. 清理临时文件

## 常见报错

| 报错 | 原因 | 处理 |
|---|---|---|
| `400001 invalid file_id` | 用了带假前缀的 ID | 走 `search_file` / `recent_online_file` 取真 ID |
| `count exceeds maximum value of 20` | `recent_online_file` 的 `count` 没传或传 0 | 显式传 `count` 1~20 |
| `400016` 类型不匹配 | 用 doc 工具改 sheet（或反之） | 先看 `ext` 再用对应品类工具 |
| 读到"空表"但用户说有数据 | 没传 `start/end_row/col` | 显式传范围 |
| 颜色上完又变回去了 / 百分比变裸小数 | 分两次调 `set_cell_style`，后一次把前一次字段冲掉 | 颜色+格式+对齐**合并进同一次调用**重设（见 §4.5） |
| `ERROR:no_token` | 连接器未启用 / 会话未重载 | 启用连接器后重开会话 |
