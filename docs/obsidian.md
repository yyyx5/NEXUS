# 可选的 Obsidian 人生记忆阅读镜像

[English](obsidian_EN.md) · 实验性参考实现 · 默认不启用

Nexus 可以独立作为人生记忆记录器。此扩展只是在你想直接阅读记忆时，生成一个可在 Obsidian 打开的 Markdown Vault；不部署它不影响 Nexus 的保存、查询、来源和修订。

## 选择与日后启用

在仓库根目录运行：

```sh
python3 -B scripts/obsidian.py setup
```

程序先解释用途、同步方向、隐私和限制，再询问是否启用。直接回车表示跳过，不创建配置、Vault 或定时任务。以后改变想法，再运行同一个命令即可；不需要重新部署 Nexus。

选择启用后，输入自己的 Nexus SQLite 路径和本地 `Nexus` 文件夹。健康/受限记录和未完成写入默认不导出；包含它们需要单独选择。iCloud 也默认不启用，启用意味着所选内容会进入 Apple 的云同步服务。

配置保存在仓库之外，默认位置由程序显示；也可使用 `--config` 指定外部配置。`config/obsidian.example.json` 只是禁用状态的模板，不能原样用来访问真实数据。已经启用后再次 setup 选择跳过会保留原状；暂停使用下方 disable。

## 手动运行、暂停和恢复

```sh
python3 -B scripts/obsidian.py sync
python3 -B scripts/obsidian.py status
python3 -B scripts/obsidian.py disable
# 后悔了或希望更改配置：再次选择启用
python3 -B scripts/obsidian.py setup
```

使用自定义配置时，每个命令都传相同的 `--config <配置路径>`。disable 保留 Nexus 数据、已生成笔记和既有调度；之后的同步会跳过。重新 setup 启用即可恢复。更改目标路径不会自动删除旧位置的副本。

熟悉这些选择后，可以显式无人值守启用；未给出的可选项保持关闭：

```sh
python3 -B scripts/obsidian.py setup --enable \
  --database '<自己的Nexus数据库绝对路径>' \
  --local-vault '<本地Nexus文件夹绝对路径>' \
  --timezone Asia/Shanghai
```

`--include-sensitive` 是明确的敏感内容授权；`--icloud-vault` 是明确的云副本选择。核心 Nexus 的部署不会调用此脚本或自动开启它。

## 你会看到什么

- 中文标题与已明确的日期；事件时间和录入时间分开，歧义时间不猜。
- 按正式档案关联集中到同一文件夹：档案首页、连续阅读的完整页、条目明细。
- 分类入口、时间线、`09-未分类/未分类索引.md` 与同步状态。
- 易读的金额/待办/日程信息，以及可展开的证据和记录编号。

关系不明确的内容不会仅凭标题相似被归入档案。未分类统计仅覆盖本次允许导出的记录；默认不展开尚未完成且未确定可见性的写入请求。模板目前主要为中文。

```text
Nexus → 本地暂存与校验 → 本地 Nexus → 可选 iCloud Nexus
```

Nexus 是唯一事实源，镜像没有任何反向写入。Obsidian 是阅读界面，不是第二套数据库。镜像内自动生成笔记的修改会被后续同步覆盖；纠错和归档应回到 Nexus。全档案页面是逐条汇集，不是 AI 撰写的游记，也不生成新的事实。旧摘要若是快照，会标明其性质。

## iCloud 与定时运行

仅本地运行用 `sync --local-only`。默认的 sync 先完成本地生成，再尝试云端复制；云端失败不会撤销本地成功。基础同步只使用 Python 标准库，0 Token，不调用云模型或云 API。

在 macOS 上，setup 只使用实际存在的 Obsidian iCloud 容器；没检测到时，需要你填写自己核实的路径。两个 Vault 都应命名 `Nexus`，必须分离且不相互嵌套。Obsidian 应用需自行安装；没有插件安装步骤。

可选生成 macOS 每日 04:00 的 launchd 配置：

```sh
python3 -B scripts/obsidian.py schedule
# 需要加载时才运行；也可自行审阅 plist 后加载
python3 -B scripts/obsidian.py schedule --load
```

04:00 采用 macOS 系统时区，配置里的 timezone 只管笔记时间显示。已有不同配置的同名任务不会被覆盖。安装、加载及后台访问权限必须在自己的机器验证：实际部署中已遇到 Python 被 macOS 隐私机制阻止读取 iCloud。只加载成功不等于自动同步成功；本机写入成功不证明手机/平板已经下载。

Linux 可使用本地镜像并自行选择调度器。当前不支持 Windows 的运行锁/部署；不承诺通用 iCloud 或手机端安装。

## 数据边界与验证

SQLite 使用只读连接和一致读取事务。镜像是未加密副本；本地源文件访问权限由系统管理，不复用 Agent 的对话授权检查。只给你自己的数据库使用，不能作为多用户服务。健康筛选依据现有字段，不能保证每段原文都不包含敏感表达；启用云副本前自行核对范围。

只有 manifest 登记且带生成标记的文件会被清理；`.obsidian/` 和其他文件保留，未管理的同名文件会拒绝覆盖。逐文件原子替换不是整个 Vault 的文件系统事务；不要同时手工修改生成笔记。配置、Vault、日志和运行状态必须放在源码仓库之外，不要上传私人阅读副本。

公开验证使用全新虚构数据，覆盖选择跳过/日后启用/暂停、档案归组、金额纠正、改名与删除、用户文件保护、云端失败后的本地成功、并发锁和敏感内容选择。尚无长期跨设备使用验收。

```sh
python3 -B scripts/obsidian_demo.py
# 若要在 Obsidian 中打开虚构演示，请指定一个仓库外尚不存在的目录
python3 -B scripts/obsidian_demo.py --output '<新建虚构演示目录>'
```

可以让自己选择的 AI 助手阅读此说明、协助确认路径与执行部署。不要把真实数据库、记忆正文或凭据上传给 GitHub；给云端 AI 的数据另行由你决定。AI 辅助不属于扩展核心代码。
