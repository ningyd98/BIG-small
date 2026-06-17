# Phase 9 实验设计

套件划分：

- `phase9_smoke`：18 次 MuJoCo 运行。
- `phase9_validation_mujoco`：2250 次 MuJoCo 运行。
- `phase9_full_mujoco`：11250 次 MuJoCo 运行。
- Isaac 套件：除非达到 `ISAAC_READY`，否则生成 `BLOCKED_BY_ENV`。

artifact 写入 `experiments/baselines/phase9/`，内容包括 manifest、environment、config、randomization、events、raw runs、summary CSV/JSON、result hash 和 report。
