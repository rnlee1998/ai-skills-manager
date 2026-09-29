# WorkBuddy 积分助手 · 接口契约参考（references/endpoints.md）

> 本文记录本 Skill 依赖的全部网络接口，全部来自已真实验证的迁移源项目：
> - Buddy加油站签到：`workbuddy-checkin`（连续运行日志 2026-08-11 → 09-03 验证）
> - Buddy旅行（派猫猫）：`workbuddy-travel-auto`（2026-08-23 验收报告验证 depart→claim 同单闭环）
> 本 Skill 不调用以下以外的任何接口。

---

## 一、公共认证

| 项 | 值 |
|---|---|
| 认证头 | `Authorization: Bearer <access_token>` |
| token 来源 | 本地登录态（`credentials.py` 统一读取，见下） |
| 登录态文件（v5.3.8+，主路径） | `workbuddy-desktop.info`（明文 JSON） |
| 登录态文件（旧版，回退） | `state.vscdb`（Electron safeStorage 加密） |

登录态本地路径（按平台）：

| 平台 | 新版明文（主路径） | 旧版 state.vscdb（回退） |
|---|---|---|
| macOS | `~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info` | `~/Library/Application Support/{WorkBuddy,CodeBuddy}/User/globalStorage/state.vscdb` |
| Windows | `%APPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info` | `%APPDATA%\{WorkBuddy,CodeBuddy}\User\globalStorage\state.vscdb` |
| Linux | `~/.config/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info` | `~/.config/{WorkBuddy,CodeBuddy}/User/globalStorage/state.vscdb` |

统一返回结构（credentials.load_credentials()）：
```
{ "access_token": "...", "uid": "...", "source": "workbuddy-desktop.info|state.vscdb" }
```

---

## 二、Buddy加油站签到（host：`https://copilot.tencent.com`）

### 1. 查询签到状态
- `POST /billing/meter/checkin-status`
- body：`{}`
- 认证：`Authorization: Bearer <token>`
- 响应（节选）：`{ "code": 0, "data": { "today_checked_in": bool, "streak_days": int } }`
- ⚠️ 已知坑（v5.3.8 实测）：`today_checked_in` **不可靠**（签到成功后仍可能为 false），
  仅作快速短路参考；幂等必须依赖 daily-checkin 的 `code=10001`。

### 2. 执行签到
- `POST /billing/meter/daily-checkin`
- body：`{}`
- 认证：`Authorization: Bearer <token>`
- 响应（节选）：
  - 成功：`{ "code": 0, "data": { "credit": 100, "streak_days": 5 } }`
  - 已签到：`{ "code": 10001, "msg": "..." }` → **视为 already_checked，不是失败**
- 每日 100 积分，连续第 7 天 1000 积分。

---

## 三、Buddy旅行（派猫猫）（host：`https://www.workbuddy.cn`）

⚠️ 旅行接口属 WorkBuddy 成长中心（Web）活动接口：**活动改版/下线时本组接口可能失效**，
届时 travel 模块返回 failed + 具体 code/msg，属预期行为。

### 0. 专用请求头（在 Bearer 之外额外必需）
- `X-User-Id: <uid>`（来自登录态 `account.uid`）
- `User-Agent: WorkBuddy/5.3.14`

### 1. 查询旅行状态
- `GET /activity/growth/buddy/travel/status`
- 响应（节选）：`{ "code": 0, "data": { "state": "idle|traveling|arrived", "daily_limit_reached": bool, "arrive_at": int, "server_now": int } }`

### 2. 派遣旅行
- `POST /activity/growth/buddy/travel/depart`
- body：`{ "location_id": 1 }`（1 = 咖啡馆，实测时长 1–4h 浮动）
- 响应（节选）：`{ "code": 0, "data": { "state": "traveling", "record_id": int, "location": {...}, "depart_at": int, "arrive_at": int } }`

### 3. 领取奖励
- `POST /activity/growth/buddy/travel/claim`
- body：`{}`
- 响应（节选）：`{ "code": 0, "data": { "reward_credit": 7, "record_id": int, "state": "idle", "letter": {...}, "use_deeplink": "..." } }`
- 实测 reward_credit 在 5–10 间浮动；每天仅可完成一轮派遣+领取（`daily_limit_reached`）。

### 状态机决策（与原 travel_auto.py 一致，不重复设计）
| state | 条件 | 动作 |
|---|---|---|
| arrived | — | claim（领取） |
| idle | daily_limit_reached=false | depart（派遣，固定咖啡馆） |
| idle | daily_limit_reached=true | 跳过（今日旅行次数已完成） |
| traveling | — | 跳过（不重复派遣） |

---

## 四、通用错误约定

| 信号 | 含义 | 模块行为 |
|---|---|---|
| HTTP 401 | token 过期 | failed + 提示打开桌面端刷新，不重试 |
| 传输层异常 | DNS/连接/超时 | failed，等下次执行 |
| code != 0 且非 10001 | 业务错误 | failed + 原样返回 code/msg |
| code = 10001（仅签到） | 今日已签到 | already_checked（成功，非失败） |

## 五、调度建议（非本 Skill 自动创建）

签到幂等可多次执行；旅行每天限一轮。推荐每日多时间点（如 09/12/15/18/21），
WorkBuddy 自动化示例见 SKILL.md「定时执行」一节——**由用户自行创建**。
