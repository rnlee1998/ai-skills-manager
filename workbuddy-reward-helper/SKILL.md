---
name: workbuddy-reward-helper
version: "1.0.2"
author: 大顺AI实测公众号
display_name: WorkBuddy积分助手
display_name_en: WorkBuddy Reward Helper
description: "WorkBuddy 积分助手：管理 Buddy加油站每日签到（100积分/天，连续第7天1000积分）与 Buddy旅行（派猫猫）派遣领取的日常积分任务。自动读取本地登录态，全程本机运行、无后端，token 不落盘不上传第三方。支持 checkin / travel / all / status 子命令，可配合定时任务执行。凭据说明：WorkBuddy 5.6.0+ 本地登录态改为 `$wbEncrypted` 加密格式（sym-v1/suite 1）；v1.0.2 使用当前已登录 WorkBuddy 客户端自身的本地运行时处理其本地加密登录态（内存解密，macOS 5.6.2 实测通过；Windows NOT_VERIFIED），无需历史明文备份、不落盘、不上传第三方；运行时不可用时如实提示，不伪造或越权获取凭据。触发词：WorkBuddy 积分、积分助手、签到、checkin、Buddy旅行、派猫猫、travel、领积分。"
description_zh: "WorkBuddy积分助手可以帮助你管理日常积分任务。支持Buddy加油站签到和Buddy旅行任务，让重复操作交给AI自动完成。"
description_en: "WorkBuddy Reward Helper manages your daily credit tasks — Buddy gas-station check-in and Buddy travel dispatch/claim. Credential note: WorkBuddy 5.6.0+ stores the local login state as an encrypted `$wbEncrypted` envelope (sym-v1/suite 1). v1.0.2 processes this envelope in-memory via the currently signed-in WorkBuddy client's own local runtime (macOS 5.6.2 verified; Windows NOT_VERIFIED) — no plaintext backup, no disk writes, no third-party upload. When the runtime is unavailable it reports clearly; it never forges or escalates access to credentials."
license: MIT
---

# WorkBuddy 积分助手（workbuddy-reward-helper）

**作者：大顺AI实测公众号**

帮你打理 WorkBuddy 每日积分的两件事：

1. **Buddy加油站签到**——每日领 100 积分（连续第 7 天 1000 积分），已签到自动跳过。
2. **Buddy旅行（派猫猫）**——自动完成「派遣 → 到达 → 领奖励」状态机：猫闲着就派去咖啡馆、到了就领积分（实测每日约 5–10 积分），旅行中/达上限自动跳过。

## ⚠️ 5.6.0 兼容状态（v1.0.2，请先读）

WorkBuddy 5.6.0+ 将本地登录凭据的 `accessToken` 改为 `$wbEncrypted` 加密格式（`sym-v1 / suite 1`）。**v1.0.2 起已支持通过 WorkBuddy 桌面端本地运行时（Electron 原生存储接口）在内存中解密该信封**，无需任何历史明文备份、不落盘、不上传第三方。

本 Skill 的处理方式（v1.0.2）：

- **自动检测当前环境**：明文登录态照常使用；检测到 `$wbEncrypted` 时，调用 WorkBuddy 本地运行时在内存中解密（`atRestSecretKey` 来自客户端运行时、不硬编码、不打印、不落盘）
- **应急回退通道（仅兜底）**：仅当运行时解密失败 **且** 显式设置 `WB_REWARD_ALLOW_BACKUP=1` 时，才尝试「同账号、同域名、未过期」的历史明文备份；该开关**绝不意味着优先使用历史备份**，且随备份 token 到期自然失效
- **平台验证范围**：macOS 已实测通过（WorkBuddy 5.6.2 / Electron 37.10.3）；**Windows 暂未实测，标注为 NOT_VERIFIED**，请勿声称已验证
- **真实验证记录**：WorkBuddy 5.6.2 实测 `$wbEncrypted`（sym-v1/suite 1）可由客户端本地运行时解密，凭据读取链路已打通

版本兼容一览：

| 桌面端版本 | 登录态格式 | 状态 |
|---|---|---|
| 5.3.8 ～ 5.5.x | 明文 | ✅ 已验证，原能力可用 |
| 5.6.0+ | `$wbEncrypted` 加密 | ✅ v1.0.2 已支持（经 WorkBuddy 本地运行时内存解密，macOS 实测通过；Windows NOT_VERIFIED） |

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

> 版本要求见上方「5.6.0 兼容状态」：**5.3.8 ～ 5.5.x 已验证原明文登录态路线**；**5.6.0+ 本地凭据改为 `$wbEncrypted` 格式，v1.0.2 已支持经 WorkBuddy 本地运行时内存解密（macOS 实测通过；Windows NOT_VERIFIED）**。旧版账户（state.vscdb）见「排错」。

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
- **5.6.0+**：本地 `accessToken` 已切换为 `$wbEncrypted` 加密格式，v1.0.2 使用当前已登录 WorkBuddy 客户端自身的本地运行时处理其本地加密登录态（内存解密，macOS 实测通过；Windows NOT_VERIFIED）
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
| WorkBuddy 桌面端（已登录） | 本地登录态 | 5.3.8～5.5.x 已验证；5.6.0+ v1.0.2 已支持经 WorkBuddy 本地运行时内存解密（macOS 实测通过；Windows NOT_VERIFIED）；必须登录过至少一次 |
| Python 3.10+ | 运行脚本 | 仅标准库（json/urllib/sqlite3），无需 pip |
| Electron（可选） | 仅旧版 `state.vscdb` 账户解密 | 明文版本用户不需要 |

## 排错

- **⚠️ WorkBuddy 5.6.0+（2026-09-19 发布）：本地登录态已启用新的加密格式（`$wbEncrypted`，sym-v1/suite 1）**
  桌面端升级 5.6.0 后，`workbuddy-desktop.info` 中的 `auth.accessToken` 由明文字符串变为加密信封对象。**v1.0.2 起已支持通过 WorkBuddy 桌面端本地运行时在内存中解密**（macOS 实测通过），无需历史明文备份：
  - 运行时解密为首选路径：`accessToken` 为 `$wbEncrypted` 时自动调用 WorkBuddy 客户端（Electron 原生 `electron_browser_workbuddy_storage` 接口）在内存中解密，密钥不硬编码、不落盘、不打印、不上传
  - 仅当运行时解密失败且显式设置 `WB_REWARD_ALLOW_BACKUP=1` 时，才回退到「同账号、同域名、未过期」的本地历史明文备份（该通道随备份 token 到期自然失效，非长期方案，**绝不优先使用**）
  - 若解密持续失败：请打开 WorkBuddy 桌面端刷新登录态后重试
- **报「未找到可用登录态」**：先打开 WorkBuddy 桌面端登录一次；确认版本在 5.3.8～5.5.x 明文区间（5.6.0+ 见上一条）
- **旧版账户（state.vscdb）**：需 Electron 运行时，设 `WB_REWARD_ELECTRON=<electron路径>`；旧版应用名迁移设 `WB_REWARD_APP_NAME=CodeBuddy`
- **401 令牌过期**：打开 WorkBuddy 桌面端刷新登录态即可，下次运行自动恢复
- **旅行返回 failed（业务错误 code/msg）**：Buddy旅行属成长中心活动接口，**活动改版/下线时该功能会失效**，属预期行为；签到不受影响
- **签到提示 already_checked**：正常，今日已领过（幂等保护）

## 已知限制

- **WorkBuddy 5.6.0+ 本地凭据加密**：v1.0.2 起默认经 WorkBuddy 本地运行时内存解密（macOS 实测通过）；仅当运行时解密不可用时，才在 `WB_REWARD_ALLOW_BACKUP=1` 下回退历史明文备份；**Windows 尚未实测（NOT_VERIFIED）**
- 签到按自然日结算，整天未开机当日无法补签（连续天数会重置）
- 旅行每天限一轮派遣+领取（服务端 `daily_limit_reached` 控制）
- 旅行时长 1–4h 由服务端浮动，定时任务间隔需覆盖到达窗口（参考 08:15/12:30/16:45/21:00）
- 旧版 `state.vscdb` 解密分支已实现，但仅在 5.3.8～5.5.x 明文环境验证过主路径

## 第三方迁移来源与署名（务必保留）

本 Skill 的 `$wbEncrypted` 运行时解密实现（脚本 `scripts/wb_runtime.py`）**最小必要迁移**自开源项目：

- 项目：`88lin/workbuddy-auto-signin`
- 仓库：`https://github.com/88lin/workbuddy-auto-signin`
- 提交：`cceadda3fc98172a8d2fb3c26aee116c67f26ea2`
- 协议：**MIT**（Copyright (c) 2026 88lin）

迁移原则：仅复用其「通过 WorkBuddy 客户端本地运行时内存解密 `$wbEncrypted` 信封」的最小实现，未改动原项目；原项目的签到/成长中心业务逻辑不纳入本 Skill。

> ⚠️ **Windows 验证状态**：`wb_runtime.py` 的 Windows 运行时发现与解密路径沿用来源逻辑，但本 Skill **未在 Windows 环境实测**，对外一律标注为 **NOT_VERIFIED**，不得声称已验证。macOS 已实测通过。
