# Nexus v0.2.0 — Optional Obsidian Reading Mirror / 可选 Obsidian 阅读镜像

这是第二个公开版本：在 v0.1.0 的人生记忆记录器基础上，增加可选的 Obsidian 单向阅读镜像。新增功能提高次版本号，核心数据库结构和工具接口兼容；v0.1.0 保留供下载。

## 新增内容

- 可选部署：先说明用途、隐私与限制，再选择启用或跳过，默认不部署。
- 日后重跑 setup 即可启用；disable 可暂停且保留记忆与镜像。
- 中文阅读笔记、时间线、正式档案文件夹及完整阅读页、未分类入口和证据追溯。
- Nexus → 本地暂存/校验 → 本地 Nexus → 可选 iCloud Nexus；无反向同步，基础同步0 Token。
- 健康/受限内容、未完成写入及 iCloud 需要明确选择，保护用户文件与 .obsidian。
- 可选 macOS 每日04:00调度、双语部署说明及全新虚构演示。

运行 `python3 -B scripts/obsidian.py setup`。Nexus 可以独立使用；AI可辅助部署，但不属于扩展核心。参见 [部署说明](https://github.com/yyyx5/nexus/blob/v0.2.0/docs/obsidian.md)。

## 验证与边界

扩展发布时，既有20项测试及新增6项虚构回归、虚构Demo、临时launchd语法检查通过。本次仅修改版本元数据和说明，核对版本/来源哈希并审计源码、暂存和完整历史，不重复无变更的功能测试。发布不包含真实记忆或生产配置。

扩展仍为实验性参考实现：macOS/Linux、中文模板；Windows和长期跨设备使用未验收。镜像未加密，自动笔记编辑会被覆盖；macOS后台iCloud访问可能需要权限，本机写入不等于手机已下载。

## English

This second release adds an optional one-way Obsidian reading mirror to the v0.1.0 life recorder. The minor version adds capability without changing the core schema or tool interfaces. The earlier release remains available.

Setup explains purpose, privacy and limits before asking; skip is the default. Rerun setup to enable later, or disable to pause. Chinese reading notes, existing dossier folders and continuous reading pages, timelines, an unclassified inbox and evidence are included. Local generation precedes optional iCloud copying. Sensitive content and iCloud require explicit choices. No reverse writes or model calls.

Run `python3 -B scripts/obsidian.py setup --language en`; see [deployment instructions](https://github.com/yyyx5/nexus/blob/v0.2.0/docs/obsidian_EN.md). Nexus works independently; AI-assisted deployment is optional and outside the extension core.

At extension publication, 20 existing tests and 6 new fictional regressions passed, together with the fictional demo and temporary launchd syntax check. This release only updates metadata and documentation; version/hash consistency and privacy are checked without repeating unchanged functional tests. No personal data or production configuration is included. The mirror remains experimental on macOS/Linux with Chinese templates. Windows and long-term cross-device use are not accepted. Mirrors are plaintext; generated-note edits are overwritten. Background iCloud access may require macOS permission, and container writes do not prove mobile delivery.
