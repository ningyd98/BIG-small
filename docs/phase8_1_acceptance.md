# Phase 8.1 验收

只有当实验 harness 真正驱动生产控制链，并且证据能通过正式 runtime record 闭环时，Phase 8.1 才算通过。

## 必需检查

- runtime harness 集成。
- 故障与执行步骤交错。
- 真实 `TaskExecutor` 路径。
- 真实 `SafetyShield` 路径。
- PCSC supervision。
- ETEAC event/replan 路径。
- S10 command ingress rejection。
- AUTO transition lifecycle。
- SQLite crash recovery。
- 基于事件源的指标重算。
- 可复现性。
- Phase 8 smoke suite。
- Phase 3-8 regression。
- Phase 8.1 pytest suite。

## 已运行命令

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python scripts/run_phase8_experiments.py --suite smoke --seeds 0 --networks NORMAL --output experiments/results/phase8_1_smoke
python scripts/run_phase8_experiments.py --suite full --seeds 0:4 --networks GOOD,DEGRADED,INTERMITTENT --output experiments/results/phase8_1_validation
python scripts/run_phase8_experiments.py --suite full --seeds 0:9 --networks GOOD,NORMAL,DEGRADED,POOR,SEVERE --output experiments/results/phase8_1_full
python scripts/verify_phase8.py
python scripts/verify_phase8_1.py
pytest -q
ruff format --check .
ruff check .
mypy .
pip check
```

## 观测结果

- Smoke：45 次运行，33 次成功。
- Validation：675 次运行，495 次成功。
- Full benchmark：2250 次运行，1650 次成功。

## 证据边界

- 原始 `events.jsonl` 和 `raw_runs.jsonl` 会生成，但不提交到仓库。
- `experiments/baselines/phase8_1/` 只保留小体积的可复现 artifact。
- Phase 8.1 仍使用 mock/simulated 组件，不证明真实机械臂安全，也不证明真实物理性能。
