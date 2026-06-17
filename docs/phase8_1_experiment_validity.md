# Phase 8.1 实验有效性

## Phase 8 已证明的内容

Phase 8 证明实验框架具备确定性和可复现性，但还不能保证 runner 已经端到端驱动生产 runtime chain。

## Phase 8.1 新增内容

- 故障与真实原子执行交错。
- step completion 来自 `TaskExecutor`、checkpoint 和 completion evidence。
- safety result 来自 `SafetyShield`，不再来自 runner 侧计数器。
- command rejection 来自真实 ACK record。
- cloud invocation count 来自真实 supervisor 和 replanning event。
- AUTO mode change 使用持久化的 prepare/commit/abort transition。
- restart check 会重建 repository 和 service，而不是复用旧对象。

## 不声明的内容

- 不声明 AUTO 一定优于 PCSC 或 ETEAC。
- 不把仿真零碰撞等同于真实硬件安全。
- 不声明 mock network 行为与生产网络完全一致。
- 不声明 Phase 8.1 可以替代 Phase 9 硬件验证。

## 复现实验

```bash
python scripts/run_phase8_experiments.py --suite smoke --seeds 0 --networks NORMAL --output experiments/results/phase8_1_smoke
python scripts/run_phase8_experiments.py --suite full --seeds 0:4 --networks GOOD,DEGRADED,INTERMITTENT --output experiments/results/phase8_1_validation
python scripts/run_phase8_experiments.py --suite full --seeds 0:9 --networks GOOD,NORMAL,DEGRADED,POOR,SEVERE --output experiments/results/phase8_1_full
python scripts/verify_phase8_1.py
```

## 证据规则

- 不得静默排除失败。
- 不得从固定计数器推断成功。
- 不得用 wall-clock time 比较结果。
- 用 config hash、git SHA、seed 和 event hash 做复现检查。
