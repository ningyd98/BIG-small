# Phase 12 Acceptance

## Smoke

```bash
# 命令说明：运行 Phase 12 smoke，只验证最终实验管线，不连接真实机械臂。
python scripts/run_phase12_experiments.py --profile smoke
python scripts/analyze_phase12_results.py --profile smoke
python scripts/export_phase12_thesis_assets.py --profile smoke
python scripts/verify_phase12.py --smoke
```

通过后只能声明：

`PHASE12_EXPERIMENT_SUITE_READY`

`PHASE12_THESIS_ASSET_PIPELINE_READY`

Smoke 数据必须标记为 `SYNTHETIC_PIPELINE_SAMPLE`、`actual_runner_invoked=false`、`authoritative_for_thesis=false`。Baseline `7b4c9af` 的 90 条 smoke 记录不进入论文统计、不计算论文 effect size、不声明最终论文 evidence accepted。

## Validation

Validation profile 至少 3 seeds 和 2 repetitions，并必须调用 actual software runners。Isaac、Ollama、MoveIt 环境可 `BLOCKED_BY_ENV`，但 Mock、Phase 8、MuJoCo、Synthetic Dry-Run 和 Rule-Based 不得用公式替代。通过后可声明：

`PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED`

`PHASE12_VALIDATION_ANALYSIS_PACKAGE_ACCEPTED`

Validation 仍不得声明 full final evaluation 或最终论文证据 accepted。

## Full

Full profile 必须满足样本量、统计、图表、表格、论文素材、demo bundle、无 secret、无硬件误声明和 worktree clean。通过后才可声明：

`PHASE12_FINAL_EVALUATION_ACCEPTED`

论文素材和答辩包完成后可声明：

`PHASE12_THESIS_EVIDENCE_PACKAGE_ACCEPTED`

最终软件与仿真项目封板：

`BIGSMALL_SOFTWARE_AND_SIMULATION_PROJECT_ACCEPTED`

禁止声明：

`BIGSMALL_REAL_ROBOT_PROJECT_ACCEPTED`
