# Unified Infinity

**面向 Minecraft 1.21.1 的实验性模组兼容运行时与统一模组列表。**

[English](README.md) · [贡献指南](CONTRIBUTING.md) · [构建说明](docs/fusion-v6/REBUILD.md) · [许可证范围](LICENSING.md)

项目目标是在同一套源码集成运行时中逐步兼容 Fabric、Forge、NeoForge 和 Quilt
生态的模组。项目基于 NeoForge/FML、Sinytra Connector、Adapter、Forgified Fabric API
及 Quilt API 等上游工作，保留其来源、修改记录和许可证。

## 目前做到哪里

`main` 的已验收源码基线是 **v6 foundation**，对应
[`e527f35`](https://github.com/Nexa-MC/unified-infinity/commit/e527f35b852ba1cb66b0fa11aff3df55ec60ad34)。
后续文档整理不会扩大这份运行验收的范围。

- 目标环境：Minecraft 1.21.1、Java 21、NeoForge 21.1.219、FML 4.0.42
- 已验证：一组固定的五个用户模组在 Linux 客户端进入真实主菜单，展示统一模组列表、
  正确页脚及排除原因，重新打开复制的测试世界、保存并正常退出
- 该次列表统计：五个用户模组、56 个加载条目、46 个内置 API 条目；API 汇总单独展示
- 尚未证明：任意整合包兼容、四个加载器完整 API、Windows/macOS 支持、生产可用性，
  以及 v6 专用服务器的重新验收

[验收记录与限制](docs/fusion-v6/README.md)和[固定输入及产物哈希](docs/fusion-v6/artifact-and-input-pins.json)
是判断能力的依据。编译通过、接口存在、诊断 CI 成功或源码哈希匹配，都不等于真实模组已在游戏内通过。
`diagnostic/*` 分支中的工作不自动成为主分支已验收能力。

## 先检查源码

```sh
git clone https://github.com/Nexa-MC/unified-infinity.git
cd unified-infinity
python3 source-workspace/verify-fusion-source.py
```

这条检查不下载依赖、不启动游戏。它核对 655 项核心/FML/BOOT 源码、39 项产品记录、
12 项预加载界面连续性记录及七个启动辅助文件，并不代替构建和运行验收。

## 构建与安装

需要 Python 3、Java 21 开发工具包和 Gradle 8.11.1。历史构建使用 Java `21.0.12.1+1`。
先按[依赖恢复说明](docs/fusion-v6/DEPENDENCY-RESTORATION.md)恢复精确依赖及生成的
Minecraft/NeoForge 编译输入，再按照[完整构建指南](docs/fusion-v6/REBUILD.md)操作。

仓库不包含工具链、Gradle wrapper 可执行 JAR、运行时/模组二进制、Minecraft 游戏文件、
游戏资源或世界存档。尚未验证从完全干净网络环境重建；直接运行 `./gradlew build` 不是完整流程。

恢复前置条件后，核心构建与检查入口为：

```sh
python3 source-workspace/gradle-build.py --four-loader --heap-mib 512 fullJar
python3 source-workspace/gradle-build.py --four-loader --heap-mib 512 check
```

当前没有面向普通玩家的一键安装包。v6 需要单独重建依赖并准备经过检查的本地安装策略，
旧版 `runtimeDistribution` 的双 JAR 布局不适用于 v6。请勿混装修改版与原版加载器组件，
也不要用重要存档直接测试。元数据准入检查不构成操作系统沙箱，模组会以游戏进程的权限运行。

Minecraft 与依赖应从官方来源获取，并遵守 [Minecraft EULA](https://www.minecraft.net/en-us/eula)。
本项目不隶属于 Mojang、Microsoft 或上游加载器团队，也不代表获得其背书。

## 源码结构与方向

- `source-workspace/connector-four-loader/`：Connector、Adapter、FART 及兼容实现
- `source-workspace/fml-unified/`、`source-workspace/admission-bootstrap/`：FML 与共享 BOOT 准入
- `runtime-bundle/`：统一模组列表、排除原因、页脚等产品层
- `preload-ui/`：预加载界面和测试
- `docs/fusion-v6/`：当前已验收基线、哈希与构建说明
- `infinity-api/`：尚未接入游戏的独立事件 API 实验
- `four-loader/`、`docs/four-loader/`、`docs/full-source-build/`：探针及历史验收材料

完整四加载器 API 与行为兼容仍在推进，不能宣称“100% 兼容”。未来面向 Minecraft 1.21.1
的 Paper/Bukkit 插件层属于独立计划，当前基线不支持运行 Paper 插件。

## 参与贡献

请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。问题报告应包含确切提交、Java/Minecraft/
加载器版本、最小模组集合、复现步骤及脱敏日志。安全问题请参考 [SECURITY.md](SECURITY.md)，
不要在公开 issue 中粘贴凭据或敏感数据。

## 许可证

项目原创代码和文档在 [LICENSING.md](LICENSING.md) 界定的范围内采用 [LGPL-2.1-or-later](LICENSE)。
上游原始及修改后的组件继续遵守各自的 MIT、Apache-2.0、LGPL-2.1 或 LGPL-3.0 等许可证；
整个组合仓库不能笼统标成单一许可证。品牌图稿和第三方素材不包含在这次 LGPL 授权中。

再分发前请查看 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)、文件头及保留的完整许可证。
源码公开不等于组合二进制、游戏文件或上游素材可以不受限制地再分发。
