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

## Validation

Validation profile 增加 seed 和 repetitions，通过后可声明：

`PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED`

## Full

Full profile 必须满足样本量、统计、图表、表格、论文素材、demo bundle、无 secret、无硬件误声明和 worktree clean。通过后才可声明：

`PHASE12_FINAL_EVALUATION_ACCEPTED`

论文素材和答辩包完成后可声明：

`PHASE12_THESIS_EVIDENCE_PACKAGE_ACCEPTED`

最终软件与仿真项目封板：

`BIGSMALL_SOFTWARE_AND_SIMULATION_PROJECT_ACCEPTED`

禁止声明：

`BIGSMALL_REAL_ROBOT_PROJECT_ACCEPTED`
