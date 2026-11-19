# Harness 正常 CLI 的大结果读回

## 原故障与候选修复

按 Astra 计划核对 10 份输入。冻结 4bdb64eb 的原运行中，development-11 的原生进程退出 0，旧包装退出 2，固定的包装及批次记录保留。使用该版本已经安装的正常 `bigsmall-harness evidence` 从源码外读原路径，再现退出 2 和 `evidence JSON exceeds 8 MiB`。

新候选仅为 manifest 绑定的根目录 `result.json` 设置 16 MiB 限额。读取使用原安全文件描述符，先核 manifest 声明与实际文件长度，再最多读取声明长度加一个字节，核对全字节 SHA256 后调用原严格 JSON 解码和原终态、准备与归属验证。manifest、scene assignment 和 source hashes 仍使用原 8 MiB。现有路径拒绝、发布与 CLI 输出结构沿用。两文件先在独立薄检出验证，后逐字合入共享交付工作树。

## 验证

| 验证 | 结果 |
| --- | --- |
| 实现前定向 RED | 9 个预期失败，3 个通用上限控制通过，36 个未选择 |
| 修后 embodied Harness 文件全量 | 48 通过，8.65 秒，Ruff 退出 0 |
| 合法大结果 | 8 MiB 加一个字节、恰好 16 MiB，正常 CLI 与运行后归属检查均通过 |
| 无效大结果 | 16 MiB 加一个字节、虚报小长度、实长/摘要不符、无效 JSON、重复键与非有限常量均拒绝 |
| 实际候选 wheel 的普通例 | 从源码外正常 prepare 退出 0，随后 evidence 退出 0 |
| 实际候选 wheel 的通用大文件控制 | manifest、assignment 和 source 各超过 8 MiB 一个字节，三个正常 CLI 命令均退出 2 |
| 原 development-11 的候选读回 | 直接源码入口和安装后的正常 CLI 均退出 0，两次 stdout 字节一致 |

新 wheel 版本 0.1.0，SHA256 为 `2d07e585fba280ce8994b2a08107cf17d74a61b8afc540d14e5dd1b0b33bf141`。安装依赖检查通过，实际加载的 evidence.py SHA 与交付源一致。旧、新 JUnit 和原件前后摘要均在详细回执。

新 CLI 在原目录完整验证 3,524 个文件。原 `result.json` 为 8,606,790 B，SHA256 为 `cbdcbf9e56787117a2a67e982b2518b60dcbc583483c1e0da032334608f5b745`，原 manifest SHA256 为 `145a8e0885449c0df9ee2bf2b06f6d27f71f5b6799e4ecdd72c6e2917225379b`。从同一份已验证的原结果读到 episode ID `1e73c77cac3f447986a569cc2ab9ab75`。正常 CLI 返回 `VERIFIED`，原终态 `COMPONENTS_COMPLETED`，组件和物理成功，8,096 个物理步、9 个动作。原批 wrapper 终态和研究资格保持原记录。此次读回没有启动新物理试次、模型或付费请求。

本地命令日志、JUnit、安装与只读回执保存在忽略目录 `experiments/results/phase9/harness-large-result-reader-20261119/`。 [公开小回执](result.json)
