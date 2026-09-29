---
name: win-crash-triage
description: Windows 上应用（游戏、桌面软件）崩溃/闪退/无响应的三维定位流程——应用日志 + 系统事件日志 + minidump 二进制解析（纯 Python 零依赖）。当用户说「闪退了」「崩溃了」「查一下什么原因」「不知道怎么排查」「程序自己退出」时使用。产出：崩溃退出机制（主动 abort vs 非法访问）、出错模块、环境异常项。
agent_created: true
---

# Windows 崩溃/闪退三维定位

闪退排查最大的坑是**只看一个来源**。记住这条判据，它能直接决定排查方向：

| 系统事件日志 | 含义 | 排查重点 |
|---|---|---|
| 有 Event 1000 `Application Error`（`c0000005` 等异常码） | **非法访问崩溃**（真崩栈） | 看「错误模块名称」，大概率是某插件/DLL |
| **没有** Event 1000，但有 Event 1001 `RADAR_PRE_LEAK_64` | **主动 abort 退出**（代码里 assert / TerminateProcess） | 看应用日志末尾的 assert 原文，多是环境/资源问题，不是代码 bug |
| 两者都没有 | 进程被外部杀掉（杀软、OOM killer、脚本） | 查杀软日志、内存压力 |

`RADAR_PRE_LEAK_64` = Windows 资源耗尽检测（Resource Exhaustion Detection And Resolution），**进程内存异常增长时触发**，是内存压力/泄漏的强信号。

## 步骤

### 1. 找应用日志

按应用类型找，别猜：

- 游戏走 Steam：先定位 Steam 根目录，注册表最可靠
  `Get-ItemProperty "HKCU:\Software\Valve\Steam" | Select SteamPath`
- Unity 游戏用户数据：`%USERPROFILE%\AppData\LocalLow\<厂商>\<产品>\`
- 通用：`%LOCALAPPDATA%\<厂商>\`、`%APPDATA%\<厂商>\`

拿到目录后**必须看文件修改时间**，确认哪份日志对应本次闪退。用时间戳对齐，不要假设"最新的就是这次的"。

### 2. 系统事件日志（最关键的一步）

```powershell
Get-WinEvent -FilterHashtable @{
  LogName='Application'
  StartTime=(Get-Date "2026-09-22 00:00:00")
  EndTime=(Get-Date "2026-09-23 23:59:59")
} | Where-Object { $_.ProviderName -match 'Application Error|Windows Error Reporting' -or $_.Id -in 1000,1001 }
```

### 3. minidump 解析（见 `scripts/minidump_triage.py`）

**不需要 WinDbg / Visual Studio**。minidump 是公开格式，纯 Python 就能挖出：异常码、异常地址、加载的模块清单、崩溃线程寄存器与栈扫描。

```bash
python scripts/minidump_triage.py <path-to.dmp>
```

输出写入同目录 `<dump>.triage.txt`（UTF-8，避免 Windows 控制台乱码）。

**用途**：模块清单能立刻回答"某插件/模组的原生 DLL 到底有没有被加载"——如果没有，就可以排除它，这是极高效的排除法。

### 4. 环境层异常项（容易被忽略，但经常是真凶）

三个高价值检查点：

**a) 兼容性模式垫片**

```powershell
Get-ItemProperty "HKCU:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
```

**关键机制**：`__COMPAT_LAYER` 是**环境变量，会被子进程继承**。父进程设了兼容模式，所有子进程都会被注入 `AcLayers.dll` / `AcGenral.dll` / `SortWindows61.dll`。所以哪怕目标 exe 自己没设兼容模式，它也可能带着垫片跑。

**验证方法**：垫片里的"版本欺骗"会让程序把系统版本报错。去应用自己的启动日志里找 OS 版本行。例如 Steam 的 `logs/bootstrap_log.txt`：

```
[2026-09-22 15:49:50] Windows 6.2.9200.0, 0, 2, 256, 1, 48
```

`6.2.9200` = Windows 8。如果系统实际是 Win10/11（`10.0.19041` 等），就坐实了 WIN8RTM 垫片生效。

**b) 提交内存上限**（不是物理内存！）

```
commit limit = 物理内存 + 分页文件
```

```powershell
Get-CimInstance Win32_PageFileUsage
(Get-CimInstance Win32_ComputerSystem).AutomaticManagedPagefile
(Get-CimInstance Win32_OperatingSystem).TotalVirtualMemorySize
```

64GB 内存 + 系统自动管理的 9.7GB 分页文件 = 只有约 73GB 提交上限。大型应用（尤其 Unity 游戏挂几百个模组）很容易撞上限，表现为分配器大量 Failed Allocations + 最终 abort。

**c) 应用内部 IPC / 鉴权失败**

在应用日志里搜 `Denied` / `Unauthorized` / `pipe` / `failed to update`。这类失败本身可能不致命，但和进程间通信相关的 assert 一起出现时，往往是同一条因果链。

## 坑

1. **PowerShell 输出不回显**时，一律 `Set-Content` 到临时文件再读；读文件时注意 GBK 乱码，以文件本身为准。
2. **别只看应用日志的末尾**。很多"致命错误"是次生现象，真正的信号在别处（系统事件日志、资源监控）。
3. **主动 abort 的退出原因**往往写在应用日志倒数几行，是形如 `<源文件>(<行号>) : Fatal assert; application exiting` 的原文。**拿这个原文去搜索**，能直接找到同款案例的成因（尤其能识别出是哪个第三方 SDK 的代码，比如 `src\common\pipes.cpp` 就是 Steam 客户端的源码）。
4. 日志文件可能被缓冲，**文件时间戳与日志内部时间戳可能不一致**，以日志内部时间戳为准。
5. 递归列目录前先看规模。有些应用数据目录有几万个小文件，直接 `-Recurse` 会输出爆炸。先 `Group-Object` 或限 `-Depth`。
