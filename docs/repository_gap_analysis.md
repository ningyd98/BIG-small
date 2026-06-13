# 仓库现状和差距分析

## 初始审查结论

本次开始开发前，仓库只有 `docs/plan.md` 和一个 Word 设计文档，没有 Python 包、测试、配置、脚本、CI 配置或可运行入口，也不是 Git 仓库。

## 已补齐内容

- 建立 Python `src/` 包结构和 `pyproject.toml`。
- 建立 `contracts`、`cloud`、`edge`、`simulation`、`experiments` 的顶层模块目录。
- 完成 Phase 0 数据模型、JSON Schema 导出、契约示例、配置、结构化错误和结构化 JSON 日志。
- 完成 Phase 1 RobotAdapter 抽象、MockRobotAdapter、MuJoCo 可选适配层、固定原子技能注册表、故障注入和固定抓取放置流程。
- 完成 Phase 1.1 安全收口：固定流程类型解耦、失败短路、停机、CLI 连接生命周期和 CI。
- 完成 Phase 2 边缘运行时：显式状态机、运行时上下文、技能参数模型、重试策略、InMemory/SQLite repository、防重放、崩溃恢复和审计事件。
- 增加 `.env.example`、可复现配置、检查脚本和 Phase 1 demo 脚本。
- 增加 Phase 0/1/1.1/2 单元测试，并先确认测试在缺少实现时失败，再实现通过。

## 与完整目标的差距

| 阶段 | 状态 | 差距 |
| --- | --- | --- |
| Phase 0 | 已完成 | 云端模型与真实机械臂按要求冻结，等待后续阶段 |
| Phase 1 | 已完成 | MuJoCo 为可选适配层；真实机械臂 SDK 和 ROS 2 适配待 Phase 9 |
| Phase 2 | 已完成 | 云端通信和安全盾仍按阶段边界留到 Phase 3+ |
| Phase 3 | 未开始 | 安全盾的工作空间、速度、障碍物、急停、超时和场景版本检查未实现 |
| Phase 4 | 未开始 | FastAPI 任务 API、初始规划、MockModelAdapter、prompt registry、contract repair 未实现 |
| Phase 5 | 未开始 | 周期云端监督、TTL ACK、乱序和网络降级集成测试未实现 |
| Phase 6 | 未开始 | 事件触发边缘自治、事件检测和云端请求流程未实现 |
| Phase 7 | 未开始 | 失败摘要、局部重规划、技能缓存和“已完成步骤不重复执行”约束未实现 |
| Phase 8 | 未开始 | 故障注入、批量实验、指标采集和对比图未实现 |
| Phase 9 | 未开始 | Docker Compose、部署脚本、验收脚本和真实机械臂接口未完成 |

## 主要风险

- 当前完整安全盾尚未实现，因此 Phase 1/2 的技能执行只适合 Mock 或可选 MuJoCo 环境验证，不应连接真实硬件。
- 当前没有 MQTT 和 FastAPI 服务入口，云边通信将在 Phase 4/5 开始落地。
- SQLite repository 已用于 Phase 2 本地持久化，但还没有迁移管理、生产部署配置或并发写入策略。
- Python 3.14 环境可用，但开发依赖需要通过 `.venv` 安装。
