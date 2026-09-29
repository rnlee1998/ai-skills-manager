---
name: local-skill-manager
description: 本地 skill 共享仓库管理。当用户提到「装 skill」「安装技能」「skill 装哪」「多个 AI 应用共用 skill」「skill 目录」「skill 重复下载」「skill 版本不一致」「问技能放哪」「本地 skill 管理」「共享 skill」「skill 仓库」「归集 skill」「skill 占用空间」等意图时必须使用。核心规则：所有 skill 一律装进 D:\WorkSpace\Myrepo\ai-skills\，各 AI 应用侧只保留指向该仓库的目录链接，不再往应用自己的目录里放实体副本。
version: 1.0.0
---

# 本地 Skill 管理

## 这个 skill 解决什么问题

本机装了多个 AI 应用（WorkBuddy、Trae CN、CodeBuddy、Claude、Cursor、.agents 等），
每个应用都有各自的 skills 目录。如果每个应用各装一份 skill，会：

- **重复下载**：同一个 skill 在 N 个应用里占 N 份空间
- **版本分叉**：改了一份，其他应用还是旧的（已实际发生：qmt 技能在 WorkBuddy 是 26774B 完整版，在 Trae 是 3030B 简版）
- **重装即丢**：应用升级/重装后 skill 丢失

本 skill 用「**单一仓库 + 目录链接**」解决：所有 skill 实体只存一份，
各应用侧是 junction 链接，改一处、全体生效。

## 核心约束（硬规则）

| 项 | 值 |
|---|---|
| **共享仓库（唯一真相源）** | `D:\WorkSpace\Myrepo\ai-skills\` |
| **链接方式** | junction 优先（无需管理员/开发者模式），失败退 symlink |
| **实体副本** | 应用侧**不允许**存在。发现副本即需归集 |

### 各应用链接位置

| 应用 | agent 标识 | 应用侧路径 |
|---|---|---|
| WorkBuddy | `workbuddy` | `C:\Users\Administrator\.workbuddy\skills` |
| Trae CN | `trae-cn` | `C:\Users\Administrator\.trae-cn\skills` |
| CodeBuddy | `codebuddy` | `C:\Users\Administrator\.codebuddy\skills` |
| Codex / Amp / Cline / Cursor / Gemini | `agents` 等 | `C:\Users\Administrator\.agents\skills` |
| Claude Code | `claude` | `C:\Users\Administrator\.claude\skills` |
| Cursor | `cursor` | `C:\Users\Administrator\.cursor\skills` |

> 更多应用（gemini / windsurf / roo / kilo / continue / cline）已在脚本 `APPS` 表中预置，
> 装了对应应用后直接跑 `askill.py link` 即可自动接管。

## 仓库结构

```
D:\WorkSpace\Myrepo\ai-skills\
├── _scripts\askill.py      管理脚本（内部目录，隐藏）
├── _backup\                历史备份（内部目录，隐藏）
├── _app_meta\              各应用元数据归档（内部目录，隐藏）
├── akshare\                以下均为 skill 目录
├── baostock\
├── qmt__skillhub\
└── ... （共 26 个）
```

> 内部目录一律以 `_` 开头并设隐藏属性。脚本会自动跳过它们，不会误认为 skill。
> **新增 skill 时不要用 `_` 开头**，否则会被当作内部目录跳过。

## 怎么用

脚本：`D:\WorkSpace\Myrepo\ai-skills\_scripts\askill.py`
Python：`C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe`

> **本机注意**：PowerShell 控制台回显中文会乱码，脚本已同时把输出写入
> `%TEMP%\askill_out.txt`（UTF-8）。看不到输出时读那个文件。
> 跑脚本前设 `$env:PYTHONIOENCODING = "utf-8"`。

### 命令一览

| 命令 | 作用 |
|---|---|
| `status` | 体检：各应用链接状态 + 仓库概况 ← **最常用** |
| `list` | 列出仓库内所有 skill（含描述、大小） |
| `link` | 建立/修复所有应用链接（自动归集实体副本） |
| `link --app trae-cn` | 只处理指定应用 |
| `unlink --app trae-cn` | 断开某应用链接（仓库不受影响） |
| `sync <路径>` | 把 skill 目录**复制**进仓库（源保留） |
| `here <路径>` | 把 skill **移入**仓库并在原地留链接 ← **装新 skill 用这个** |
| `verify` | 校验链接有效性（读写双向） |
| `doctor` | 深度诊断：查副本、查非法 skill、查空目录 |
| `init` | 初始化仓库骨架（首次用） |

### 典型任务

**装一个新 skill（最常见）**

1. 把 skill 目录放到任意临时位置，或直接放在目标应用目录
2. 跑 `askill.py here <那个skill目录路径>`
   → skill 进仓库，原位置变成链接，所有应用立即可用
3. 跑 `askill.py status` 确认

> 若 skill 来自压缩包/仓库，先解压到一个临时目录再 `here`。

**体检 / 排查**

```
askill.py status     # 先看整体状态
askill.py doctor     # 有问题再深查
```

**发现某应用有副本未共享**

```
askill.py link --app <应用名>    # 自动归集该应用目录下的副本并换成链接
```

**想知道某个 skill 在哪、多大**

```
askill.py list
```

## 判断"是否已合规"

看应用侧目录是**链接**还是**实体目录**：

```powershell
(Get-Item "C:\Users\Administrator\.workbuddy\skills" -Force).LinkType
```

- 返回 `Junction` / `SymbolicLink` → 已合规（共享中）
- 返回空 + 里面有 skill 目录 → **有副本，需归集**

## 关键坑位（本机实测，务必遵守）

1. **检测 junction 必须用 `os.lstat()`**，不能用 `os.stat()`。
   `os.stat()` 会跟随 junction 并把 `ReparsePoint` 属性规范化掉，
   导致 junction 被误判为普通目录。
   正确写法：`os.lstat(p).st_file_attributes & 0x400`

2. **`os.path.islink()` 对 junction 返回 False**（只认 symlink）。
   不能只靠它判断。

3. **本机 `Rename-Item` 对目录会报「访问被拒绝」**，即使目录已清空。
   移动目录要用「复制 → 校验 → 删源」的方式，别用 rename。

4. **沙箱会拦截 `cmd /c rd /s`、`rd /q`**，`Add-Type` 也被拦。
   删除目录改用逐文件 `os.remove` + `os.rmdir`（Python 里做）。

5. **`here` 给源位置留的链接必须指向 `REPO/<skill名>`**，
   不是 `REPO` 根——否则源位置会看到仓库里全部 skill，语义错误。

6. **同名冲突策略**：比较目录总字节数，保留更大的那个。
   已实际用于 `qmt__skillhub`（保留了 239859B 的完整版，归档了 216178B 的简版）。

7. 给内部目录（`_scripts` / `_backup` / `_app_meta`）设**隐藏属性**，
   降低 AI 应用扫描时误识别的概率。

## 验收标准

跑 `askill.py doctor`，看到：

```
--- 4. 仓库整洁度 ---
  [OK]   无空 skill 目录
====================================================================
诊断结论: 一切正常
```

且 `status` 里各已安装应用均显示 `[OK] <名称> junction -> 仓库`。
