# MuJoCo Runtime Acceptance

MuJoCo readiness means the Python package and local simulation environment are detectable. Phase 11.1 runtime acceptance is stricter: MuJoCo jobs must be queued, leased, executed by the allowlisted MuJoCo worker, produce persisted events and metrics, and write runtime artifacts.

Required acceptance cases:

- M11-01 `S01_NORMAL_STATIC`, `PCSC`, seed 0.
- M11-02 `S07_NETWORK_DEGRADED`, `PCSC`, seed 0.
- M11-03 `S14_EMERGENCY_STOP`, `PCSC`, seed 0.
- M11-04 `S01_NORMAL_STATIC`, `ETEAC`, seed 0.
- M11-05 `S01_NORMAL_STATIC`, `AUTO`, seed 0.
- M11-06 three seed batch, seeds 0, 1, 2.
- M11-07 cancellation of a deliberately slowed MuJoCo job.
- M11-08 timeout of a constrained MuJoCo job.
- M11-09 recovery after queued/runtime state exists.
- M11-10 duplicate execution prevention.

Run:

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python scripts/verify_phase11_1_simulation_runtime.py --mujoco
```

Ordinary CI does not run MuJoCo runtime acceptance. It must not replace unavailable MuJoCo with Mock or claim Isaac success from Mock results.
