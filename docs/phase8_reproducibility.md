# Phase 8 可复现性

运行 smoke 套件：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python scripts/run_phase8_experiments.py --suite smoke --output experiments/results/smoke
```

运行完整套件：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python scripts/run_phase8_experiments.py --suite full --seeds 0:9 --output experiments/results/full
```

归一化 config hash 会忽略 artifact 目录路径，但包含 mode、scenario、seed、network、cache policy、risk policy、timeout 和 ablation。

seed 传播覆盖网络 jitter/loss/duplication/reordering、场景故障顺序、模拟重试和确定性结果 hash。wall-clock 时间戳不参与可复现性比较。

每次运行写入 `run_manifest.json`、`raw_runs.jsonl`、`events.jsonl`、`summary.csv`、`summary.json` 和 `report.md`。
