# 仓库结构

本页说明各目录的职责，以及源码、文档、生成数据和证据之间的边界。治理仓库时不要只按目录名判断完成度，要看对应代码、脚本、测试和证据。

| 路径 | 职责 |
| --- | --- |
| `.github/` | GitHub Actions 工作流。CI 必须保持软件安全，不能在没有证据时声明运行时或真实硬件验证。 |
| `artifacts/` | 已接受的验证证据和运行日志。这里不是源码目录，除非验证脚本明确再生成，不要随意格式化或重写历史证据。 |
| `assets/` | 机器人和仿真资产，例如 MJCF 模型。 |
| `configs/` | 可复现配置。`configs/real_robot` 只能放示例，不能提交真实 IP、序列号或 token。 |
| `contracts/` | 任务契约的 JSON 示例和 schema 相关材料。 |
| `data/` | 本地运行数据，例如 SQLite 文件。它不是权威源码。 |
| `docs/` | 架构、安全、阶段报告、审计和项目文档。 |
| `edge/` | 顶层说明目录。真实边缘运行时代码在 `src/cloud_edge_robot_arm/edge`。 |
| `environments/` | 环境准备和支持材料。 |
| `experiments/` | 实验基线和本地结果区。大体量生成结果默认不进源码，除非明确作为已接受证据。 |
| `ros2_ws/` | ROS 2 工作区源码及生成的 build/install/log。生成目录已忽略。 |
| `scripts/` | 验证脚本、demo、运行证据采集和编排入口。详见 `scripts/README.md`。 |
| `shared/` | 历史顶层说明目录。 |
| `simulation/` | 顶层说明目录。真实仿真代码在 `src/cloud_edge_robot_arm/simulation`。 |
| `src/` | 权威 Python 包源码。`src/cloud_edge_robot_arm` 是运行时实现。 |
| `tests/` | 单元、集成、契约、源码守卫和 artifact 测试。测试按行为和历史阶段组织。 |

## 空目录、重复目录和历史目录

顶层 `edge`、`shared`、`simulation` 保留用于兼容和说明，不应被当成权威运行时包。

`docs/phase*` 和 `docs/reviews` 里的历史文档用于追溯，不要在仓库治理时随手删除。

`artifacts` 存放证据。新的治理工作不应改写历史运行证据，除非某个验证命令明确要求重新生成。
