# 论文成果包仓库审计

## Git 状态

- 工作分支：`codex/thesis-report`
- 基线 HEAD：`5c43450eab1dd29b5a32786fb506f503b2729d4e`
- 主 checkout 状态：存在 Phase 9/11 artifact 未提交改动，本任务未修改、未删除、未提交这些改动。
- 隔离 worktree：仓库外独立 checkout，未在文档中记录本机绝对路径。

## 权威证据来源

本论文优先读取：

1. `artifacts/phase12_2_clean/validation/verification/phase12_summary.json`
2. `artifacts/phase12_2_clean/validation/runs/raw_runs.jsonl`
3. `artifacts/phase12_2_clean/validation/aggregates/phase12_aggregate.json`
4. `artifacts/phase12_2_clean/validation/statistics/phase12_statistics.json`
5. `artifacts/phase12_2_clean/validation/paired/paired_summary.json`
6. `docs/current_authoritative_status.md`

## 当前边界

- Phase 12 clean validation 已接受。
- full profile 未运行完成，不输出最终论文证据 accepted。
- LLM-only 当前只有 fake-provider pipeline evidence，不作为真实大模型性能证据。
- 真实机械臂验证未开始。
- `real_controller_contacted=false`
- `hardware_motion_observed=false`
- `hardware_write_operations=[]`
- `highest_real_hardware_acceptance_level=NONE`

## 处理原则

论文正文、表格、图索引和证据矩阵均从脚本读取 evidence 生成。缺失文献、真实模型、
Isaac/MoveIt 环境阻塞和 full profile 缺口以边界说明列出，不用占位数据替代。
