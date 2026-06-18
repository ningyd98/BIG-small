# Simulation Frontend Tools

Phase 11 前端工具位于 `dashboard/src/simulation/`，用于把 React 页面里的实验逻辑拆成可测试、可复用的 domain、service、builder、adapter、store 和 worker。

## 目录职责

- `api/`：Simulation API、query 和 stream 封装。
- `domain/`：backend、scenario、draft、manifest、sweep、metric、timeline 和 comparison 类型。
- `services/`：capability、catalog、submission、monitor、metrics、comparison、reproduction、export 和 preset 逻辑。
- `builders/`：ExperimentConfig、Sweep、Batch、Comparison 和 Report 定义构建器。
- `adapters/`：后端响应到前端 domain 的适配。
- `workers/`：JSONL 解析和 metrics 聚合，避免大文件阻塞主线程。
- `pages/`：工作台、场景库、批量实验、实时运行和分析页面。

## 安全约束

前端不保存 token、控制器配置、真实 IP、credential 或机器人序列号。前端不接受任意 runner 名称，也不提交 shell、path、module、environment 或 executable 字段。

## 测试覆盖

`dashboard/src/simulation/toolkit.test.ts` 覆盖 15 个场景动态加载、config builder、sweep、batch、run monitor、timeline、metrics、comparison、reproduction、export 脱敏和非法参数拒绝。

