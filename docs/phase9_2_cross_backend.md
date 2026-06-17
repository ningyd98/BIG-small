# Phase 9.2 跨后端验证

Phase 9.2 用成对的 scenario/seed 运行对比 MuJoCo 和 Isaac。第一组验证场景包括：

- `S01_NORMAL_STATIC`
- `S16_PAYLOAD_MASS_VARIATION`
- `S17_CONTACT_FRICTION_VARIATION`
- `S19_CAMERA_NOISE_AND_OCCLUSION`
- `S22_COLLISION_NEAR_MISS`
- `S14_EMERGENCY_STOP`

两个后端使用相同 seeds `0..4`、相同语义机器人模型、相同初始状态、相同任务目标、相同障碍物语义、相同载荷/摩擦定义、相同安全策略和相同结果 schema。

验证已有 artifact：

```bash
python scripts/run_phase9_2_cross_backend.py --output artifacts/phase9_2/cross_backend
```

在兼容 Isaac 的主机上运行成对实验：

```bash
python scripts/run_phase9_2_cross_backend.py \
  --run-experiments \
  --output artifacts/phase9_2/cross_backend
```

生成的 artifact：

- `mujoco_runs.jsonl`
- `isaac_runs.jsonl`
- `paired_runs.jsonl`
- `metric_deltas.json`
- `statistical_summary.json`
- `cross_backend_report.md`
- `reproducibility_manifest.json`

验证器检查后端身份、run id 唯一性、commit SHA、scenario/seed 配对、进程和环境溯源、配置 hash、结果 hash、验证标志和必需指标完整性。Isaac 失败时不能回退到 MuJoCo。

指标差异按语义一致性、趋势一致性、数值差异和后端特有影响解释，不要求数值完全相等。
