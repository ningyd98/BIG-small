# Simulation Reproducibility

Phase 11 每次运行都生成 provenance 和 reproducibility hash。复现实验从 artifact 生成新的 `ExperimentDraft`，并比较源提交、source tree hash、config hash、environment hash、backend、scenario、seed 和 control mode。

## Provenance

单个 run 写入：

- `run_manifest.json`
- `events.jsonl`
- `metrics.json`
- `logs.json`
- `result.json`
- `provenance.json`

## 复现规则

环境一致时可标记为 exact reproduction。环境不一致时只能显示 warning，不得声明完全可复现。

## 脱敏

导出和 artifact preview 必须脱敏本机绝对路径、用户名、token、credential 和 controller config。Phase 11 不保存真实控制器配置。

