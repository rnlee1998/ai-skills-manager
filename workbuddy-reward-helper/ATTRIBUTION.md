# 第三方迁移来源与署名（ATTRIBUTION）

本 Skill（`workbuddy-reward-helper`）中用于读取 WorkBuddy 5.6.0+ 本地登录凭据
（`$wbEncrypted` 加密信封，`sym-v1 / suite 1`）的运行时解密实现，位于
`scripts/wb_runtime.py`，**最小必要迁移**自以下开源项目：

- 项目：88lin/workbuddy-auto-signin
- 仓库：https://github.com/88lin/workbuddy-auto-signin
- 提交：cceadda3fc98172a8d2fb3c26aee116c67f26ea2
- 协议：MIT
- 版权：Copyright (c) 2026 88lin

## 许可说明

依据 MIT 许可证，本 Skill 在保留上述版权声明与许可声明的前提下，对该实现进行
了复用、修改与再分发。本文件（ATTRIBUTION.md）即为此署名与许可声明的载体，
随 Skill 一同分发，不得移除。

## 迁移范围与边界

- 仅迁移「通过 WorkBuddy 桌面端本地运行时（Electron 原生
  `electron_browser_workbuddy_storage` 接口）在内存中解密 `$wbEncrypted` 信封」
  的最小必要实现；
- 未改动原开源项目，也未纳入其签到 / 成长中心等业务逻辑；
- 解密所得明文 token 仅在本进程内存中使用，不硬编码密钥、不打印、不落盘、不上传第三方。

## 平台验证状态（诚实标注）

- ✅ macOS：已实测通过（WorkBuddy 5.6.2 / Electron 37.10.3）。
- ⚠️ Windows：沿用来源逻辑但**未在本环境实测**，对外一律标注为 **NOT_VERIFIED**，
  不得声称已验证。
