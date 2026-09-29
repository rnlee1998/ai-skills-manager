# ai-skills 共享仓库

一套跨 AI 应用的本地 skill 共享仓库。本机把 **WorkBuddy / Trae / CodeBuddy / Claude / Cursor …** 的 `skills` 目录统一指向这个仓库（用 NTFS junction 软链），**一份源文件多处生效**，避免重复下载、版本分叉。

> 仓库根目录由脚本自动推导（看 `_scripts/askill.py` 所在位置），所以克隆到任意盘符、任意用户名都无需改代码。

---

## 前置条件

- **Windows**（junction 仅 Windows 原生支持；macOS/Linux 需自行改链接逻辑）
- **git** 已安装
- **Python 3.8+**（脚本只用了标准库，无需 pip 安装任何包）
- 建 junction **不需要管理员权限**（用的是 `mklink /J`，与需要提权的 symlink 不同）

---

## 开箱即用（第二台机器）

只需两步：

```powershell
# 1) 克隆（二选一）
git clone git@github.com:rnlee1998/ai-skills-manager.git ai-skills   # SSH
# 或
git clone https://github.com/rnlee1998/ai-skills-manager.git ai-skills  # HTTPS

# 2) 建立链接（自动给本机已安装的应用建 junction）
cd ai-skills
python _scripts/askill.py link
```

完成。`local-skill-manager` 及仓库内其余 28 个 skill 立即可用，且自动共享。

> 若用 SSH 克隆报 `Permission denied (publickey)`：说明这台机器还没把 SSH key 加到 GitHub。
> 生成一把 key：`ssh-keygen -t ed25519 -C "你的备注"`，把 `~/.ssh/id_ed25519.pub` 内容加到 GitHub → Settings → SSH keys 即可。
> 嫌麻烦就直接用上面的 HTTPS 方式克隆（推送时才需要 token）。

---

## 常用命令

所有命令都在仓库根目录执行，统一前缀 `python _scripts/askill.py`：

| 命令 | 作用 |
|------|------|
| `link` | 给**本机已安装**的应用建立/修复 junction 链接（默认行为） |
| `link --app workbuddy` | 只处理指定应用（即使该应用尚未安装也会创建链接） |
| `status` | 体检：各应用链接状态 + 仓库概况 |
| `list` | 列出仓库内所有 skill |
| `verify` | 校验链接读写有效（能读能写回仓库） |
| `doctor` | 深度诊断：查分叉、冗余副本、孤儿文件、空目录 |
| `unlink --app workbuddy` | 断开某应用链接，还原为空目录（仓库内容不动） |
| `sync <路径>` | 把某个 skill 目录**复制**归集进仓库（源保留） |
| `here <路径>` | 把某个 skill **移动**进仓库，并在原位置留链接 |

---

## 它是怎么工作的

```
~/.workbuddy/skills/   ──junction──▶  D:\...\ai-skills\   (唯一真相源)
~/.trae-cn/skills/     ──junction──▶  D:\...\ai-skills\
...
```

- 各应用侧只保留一个 junction 链接，**不存实体副本**。
- 在仓库里增删改 skill，所有应用立刻同步看到。
- 若某应用侧原本是实体目录且已有 skill，`link` 会先把它们**归集进仓库**再替换为链接（无损合并）。

---

## 自定义路径（可选）

默认已按当前用户主目录 `~` 推导各应用路径，绝大多数情况无需配置。
只有在非标准盘符/用户名、或只想共享部分应用时，才需要建配置文件。

在仓库根目录新建 `askill_config.json`：

```json
{
  "repo": "X:\\自定义\\ai-skills",
  "apps": {
    "workbuddy": "C:\\Users\\你的用户名\\.workbuddy\\skills",
    "trae-cn":   "C:\\Users\\你的用户名\\.trae-cn\\skills"
  }
}
```

- `repo`：覆盖仓库位置（不写则自动推导）。
- `apps`：与内置清单**合并**，同名覆盖、新增追加、未提及保留默认。
- 也可临时用环境变量：`set ASKILL_REPO=X:\自定义\ai-skills`（优先级高于配置文件）。

---

## 增删 skill / 多机同步

- **新增 skill**：把含 `SKILL.md` 的目录丢进仓库根，重启应用即可；或 `python _scripts/askill.py sync <目录>`。
- **多机同步**：在一台机器改完仓库后 `git add -A && git commit && git push`，
  另一台 `git pull` 后重跑 `python _scripts/askill.py link` 即可。
- 内部目录 `_scripts/`（脚本）、`_backup/`（备份）、`_app_meta/`（元数据）已在 `.gitignore` 中忽略，不会进版本库。

---

## 目录结构

```
ai-skills/
├── _scripts/
│   └── askill.py          # 管理脚本（本仓库唯一工具）
├── <skill-name>/          # 各 skill（含 SKILL.md）
├── README.md
├── .gitignore
└── askill_config.json     # 可选，自定义路径用
```
