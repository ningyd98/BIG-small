# H0/H1 开发封装验证

H0 固定首场景并将六类契约映射到既有运行模块。H1 提供安装 CLI、包内示例、显式
源码和模型环境准入及原证据索引。共享 GPU 准入只搬移实现。原探针入口保留别名，
原单场景执行器改用包内导入。[交付说明](../../../../../docs/harness.md)

Astra 初始输入的相关 12 项与主仓计划前 138 行均核对匹配。缺失入口和资源模块的
预期 RED 为 3 失败。第一次实现核验 18 项因 argparse 默认 action 拒收
`version=` 而失败，包内 helper 的测试通过。另有 6 项 Ruff 格式问题。实际 Astra
补计划限定添加 `action="version"` 和这些格式调整。首次运行测试定位工具错误也
独立保留。[初始计划](../../20261004-ced-development/astra-rounds/round-real-model-harness-20261118/plan.md)
[补计划](../../20261004-ced-development/astra-rounds/round-harness-cli-version-20261118/plan.md)
[预期 RED](red.log) [首次 GREEN 失败](first-green-failed.log)
[首次 Ruff 失败](ruff-failed.log) [测试路径工具失败](test-path.log)

| 检查 | 实测 |
| --- | --- |
| 新 Harness CPU 测试 | 19 passed，3.72 秒 |
| 原单场景与探针 CLI CPU 测试 | 50 passed，1.73 秒 |
| 限定 Ruff | 通过 |
| wheel 构建、清洁 venv 安装、pip check | 通过 |
| 源码树外 help、version、validate、doctor | 均退出 0 |
| 显式 checkout 检查、prepare、evidence | 均退出 0，原 manifest 3 个文件的字节和哈希核对成功 |
| 耐重试核验 | 对同一目录重复 prepare 退出 2，原 manifest 哈希保持 |

wheel `big_small-0.1.0-py3-none-any.whl` 为 1,620,182 字节。SHA256
`4bb5cf2f42ce5359f464e2451c9e93977b003a7f257b773524f21b2e544777be`。
构建来自已说明基线上的共享开发工作树，wheel 保留本地。wheel 含 Python 包、CLI
和示例。检查环境没有 MuJoCo、OpenCV、Torch 或 Transformers，CLI 子进程仅继承
PATH、LANG 和空的 CUDA_VISIBLE_DEVICES。JSON 核验覆盖的同时记录了准确依赖。
[构建](wheel-build.log) [安装](clean-install.log) [清洁命令](clean-verification.log)
[依赖](clean-pip-freeze.txt) [测试](green.log) [原 CLI 回归](original-cli-regression.log)
[Ruff](ruff.log) [证据哈希](verification.json)

prepare 记录原场景资产、选定源码和 `NOT_EXECUTED`。全轮模型、GPU、API 与动作
均未启动，`physical_success=null`，正式研究 `NOT_ACCEPTED`，真机未启动。
`run-simulation` 明确引用既有执行入口，此处验收范围为无图形的软件安装、诊断和
使用原脚本的准备流程。[准备结果](clean-prepare.json) [原件核验](clean-evidence-index.json)
