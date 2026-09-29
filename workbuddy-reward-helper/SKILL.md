---
name: workbuddy-reward-helper
version: "1.0.1"
author: 大顺AI实测
display_name: WorkBuddy积分助手
display_name_en: WorkBuddy Reward Helper
description: "WorkBuddy 积分助手：管理 Buddy加油站每日签到（100积分/天，连续第7天1000积分）与 Buddy旅行（派猫猫）派遣领取的日常积分任务。自动读取本地登录态，全程本机运行、无后端，token 不落盘不上传第三方。支持 checkin / travel / all / status 子命令，可配合定时任务执行。兼容提示：WorkBuddy 5.6.0+调整了本地登录凭据格式，当前签到与Buddy旅行能力可能受影响。本Skill会自动检测当前环境；若无法安全读取凭据，将明确提示兼容问题，不会尝试绕过或破解登录凭据。触发词：WorkBuddy 积分、积分助手、签到、checkin、Buddy旅行、派猫猫、travel、领积分。"
description_zh: "WorkBuddy积分助手可以帮助你管理日常积分任务。支持Buddy加油站签到和Buddy旅行任务，让重复操作交给AI自动完成。"
description_en: "WorkBuddy Reward Helper manages your daily credit tasks — Buddy gas-station check-in and Buddy travel dispatch/claim. Note: WorkBuddy 5.6.0+ changed the local credential format; check-in and travel may be affected. The skill detects this and reports clearly instead of bypassing or cracking the encrypted credentials."
license: MIT
---

# WorkBuddy 积分助手（workbuddy-reward-helper）

帮你打理 WorkBuddy 每日积分的两件事：

1. **Buddy加油站签到**——每日领 100 积分（连续第 7 天 1000 积分），已签到自动跳过。
2. **Buddy旅行（派猫猫）**——自动完成「派遣 → 到达 → 领奖励」状态机：猫闲着就派去咖啡馆、到了就领积分（实测每日约 5–10 积分），旅行中/达上限自动跳过。

## ⚠️ 5.6.0 兼容状态（v1.0.1，请先读）

WorkBuddy 5.6.0+ 调整了本地登录凭据格式（`workbuddy-desktop.info` 的 `accessToken` 变为 `$wbEncrypted` 加密格式），**当前签到与Buddy旅行能力可能受影响**。本 Skill 的处理方式：

- **自动检测当前环境**：明文登录态照常使用；检测到加密格式时明确提示兼容问题，**不会尝试绕过或破解登录凭据**
- **临时自救通道（非正式解决方案）**：设 `WB_REWARD_ALLOW_BACKUP=1`，仅当本机存在「同账号、同域名、未过期」的历史明文备份时才可用；备份不会永久刷新、不同用户未必存在可用备份，该通道随备份到期自然失效
- 不承诺 5.6.0+ 恢复正常；长期方案待官方支持，请关注 Skill 更新
- **真实验证记录**：WorkBuddy 5.6.2 实测仍维持 `$wbEncrypted` 格式，因此当前将其视为 5.6.0+ 的持续兼容变化，而不是 5.6.0 单版本临时故障

版本兼容一览：

| 桌面端版本 | 登录态格式 | 状态 |
|---|---|---|
| 5.3.8 ～ 5.5.x | 明文 | ✅ 已验证，原能力可用 |
| 5.6.0+ | `$wbEncrypted` 加密 | ⚠️ 存在兼容限制：无合规备份时报「暂无法读取登录态」并停止 |

全流程在本机完成：读取本地登录态 → 调用 WorkBuddy 服务端接口（`copilot.tencent.com` 与 `www.workbuddy.cn`）。**无后端服务，token 不落盘、不打印、不上传任何第三方。**

两个功能均迁移自已真实验证的自动化项目（workbuddy-checkin 连续运行 3 周+、workbuddy-travel-auto 完成 depart→claim 同单闭环验收）。

## 首次回复

用户首次触发本 Skill 时，用下面这段话开场：

> 你好，我是WorkBuddy积分助手。
> 我可以帮你：
> 1. 检查Buddy加油站签到状态
> 2. 检查Buddy旅行状态并执行任务
>
> 你可以直接说：
> “检查我的WorkBuddy积分任务”
> 或者：
> “帮我设置每日积分检查”

## 快速开始

前提：本机已安装并**登录** WorkBuddy 桌面端 + Python 3.10+（仅标准库，无需 pip 安装）。

> 版本要求见上方「5.6.0 兼容状态」：**5.3.8 ～ 5.5.x 已验证原明文登录态路线**；**5.6.0+ 本地凭据改为 `$wbEncrypted` 格式，存在兼容限制**。旧版账户（state.vscdb）见「排错」。

```bash
python3 scripts/main.py all      # 日常推荐：先签到、后旅行，输出汇总 JSON
python3 scripts/main.py checkin  # 只签到
python3 scripts/main.py travel   # 只处理旅行
python3 scripts/main.py status   # 只读查询签到+旅行状态（不做任何领取/派遣）
```

输出示例：

```json
{"checkin": {"task": "checkin", "status": "success", "credit": 100, "streak_days": 5},
 "travel": {"task": "travel", "status": "claimed", "reward_credit": 7, "record_id": 2237800}}
```

状态一览：

| status | 含义 |
|---|---|
| `success` / `already_checked` | 签到成功 / 今日已签到（幂等，重复运行无副作用） |
| `departed` / `claimed` / `traveling` / `daily_limit_reached` | 已派遣 / 已领奖励 / 旅行中（不重复派遣）/ 今日旅行已完成 |
| `failed` | 失败，`reason` 给出原因（401 需打开桌面端刷新登录态） |

结果摘要自动追加到 `logs/result.log`（仅任务/状态/积分数字，**绝不记录 token**）。

## 定时执行（可选，由你自行创建）

本 Skill **不会自动创建任何定时任务**。电脑非全天开机时建议多时间点幂等补跑：

- **WorkBuddy 自动化**（Agent 环境调用 `automation_update`，recurring）：
  - 签到：`FREQ=DAILY;BYHOUR=9,13,20;BYMINUTE=0`（已实测连续运行）
  - 旅行：派遣后需等待到达再领取，建议每日多次，如 08:15 / 12:30 / 16:45 / 21:00（四条单时刻自动化；WorkBuddy 单条 RRULE 无法给不同小时绑定不同分钟）
  - Prompt 示例：`运行 /绝对路径/scripts/main.py all（用 Python 绝对路径），读取 JSON 输出并简要汇报签到与旅行结果；脚本幂等，重复运行无副作用。`
- **系统级**：macOS launchd / crontab、Windows 任务计划程序，示例命令同上。

## 原理与目录结构

```
workbuddy-reward-helper/
├── SKILL.md
├── scripts/
│   ├── main.py            # 统一入口：checkin / travel / all / status
│   ├── credentials.py     # 统一登录态读取（明文优先 + 5.6.0 加密格式检测 + 旧版 vscdb 回退）
│   ├── http_client.py     # 统一带鉴权 JSON 请求封装
│   ├── checkin.py         # 签到模块（copilot.tencent.com）
│   └── travel.py          # 旅行状态机（www.workbuddy.cn）
├── references/
│   └── endpoints.md       # 接口契约与已知坑（today_checked_in 不可靠等）
├── tests/                 # 全 Mock 测试（不真实请求），5 个文件共 109 项断言
└── logs/                  # 运行后自动创建，仅结果摘要
```

登录态（`credentials.py` 统一读取，两个模块共用一份）：

- **5.3.8 ～ 5.5.x**：已验证使用明文 `workbuddy-desktop.info`，纯 Python 读取，开箱即用
- **5.6.0+**：本地 `accessToken` 已切换为 `$wbEncrypted` 加密格式，当前按顶部兼容说明处理（不解密、不绕过）
- **回退（旧版）**：`state.vscdb` + Electron `safeStorage` 解密（需 Electron，见排错）

接口契约细节、已知坑与错误约定见 `references/endpoints.md`。

## 安全说明

> ⚠️ **凭据即账号密码**：本 Skill 读取的 `accessToken` 等同你的 WorkBuddy 账号密码。

- token 仅在内存中使用，**不写入任何日志/文件、不回显终端、不提交仓库、不上传第三方**
- 网络访问仅限 WorkBuddy 服务端接口：`copilot.tencent.com`（签到）与 `www.workbuddy.cn`（旅行）
- 日志（`logs/result.log`）仅记录任务/状态/积分数字
- 只读登录态文件，不修改 WorkBuddy 客户端的任何文件
- 仅操作本机当前登录用户自己的账户；请勿用于他人账户、批量注册刷分或任何违反 WorkBuddy 用户协议的用途，使用者自行承担风险

## 依赖

| 依赖 | 用途 | 说明 |
|---|---|---|
| WorkBuddy 桌面端（已登录） | 本地登录态 | 5.3.8～5.5.x 已验证；5.6.0+ 有兼容限制（见顶部兼容状态）；必须登录过至少一次 |
| Python 3.10+ | 运行脚本 | 仅标准库（json/urllib/sqlite3），无需 pip |
| Electron（可选） | 仅旧版 `state.vscdb` 账户解密 | 明文版本用户不需要 |

## 排错

- **⚠️ WorkBuddy 5.6.0+（2026-09-19 发布）：本地登录态已启用新的加密格式（`$wbEncrypted`）**
  桌面端升级 5.6.0 后，`workbuddy-desktop.info` 中的 `auth.accessToken` 由明文字符串变为加密信封对象，本 Skill v1.0.0 及更早版本将无法读取登录态，签到与旅行会报「未找到可用登录态」。v1.0.1 起：
  - 会如实报「检测到 WorkBuddy 5.6.0+ 已启用新的本地凭据加密格式……请等待 Skill 更新」（不再误报未登录）
  - 临时自救：设置环境变量 `WB_REWARD_ALLOW_BACKUP=1`，将严格校验并使用**同账号、同域名、未过期**的本地历史明文备份（该通道随备份 token 到期自然失效，非长期方案）
  - 建议关注 Skill 更新；未升级 5.6.0 的用户不受影响
- **报「未找到可用登录态」**：先打开 WorkBuddy 桌面端登录一次；确认版本在 5.3.8～5.5.x 明文区间（5.6.0+ 见上一条）
- **旧版账户（state.vscdb）**：需 Electron 运行时，设 `WB_REWARD_ELECTRON=<electron路径>`；旧版应用名迁移设 `WB_REWARD_APP_NAME=CodeBuddy`
- **401 令牌过期**：打开 WorkBuddy 桌面端刷新登录态即可，下次运行自动恢复
- **旅行返回 failed（业务错误 code/msg）**：Buddy旅行属成长中心活动接口，**活动改版/下线时该功能会失效**，属预期行为；签到不受影响
- **签到提示 already_checked**：正常，今日已领过（幂等保护）

## 已知限制

- **WorkBuddy 5.6.0+ 本地凭据加密**：无「同账号、同域名、未过期」明文备份时，签到与旅行均无法执行（如实报错并停止）；备份通道为临时自救，随备份 token 到期自然失效
- 签到按自然日结算，整天未开机当日无法补签（连续天数会重置）
- 旅行每天限一轮派遣+领取（服务端 `daily_limit_reached` 控制）
- 旅行时长 1–4h 由服务端浮动，定时任务间隔需覆盖到达窗口（参考 08:15/12:30/16:45/21:00）
- 旧版 `state.vscdb` 解密分支已实现，但仅在 5.3.8～5.5.x 明文环境验证过主路径
