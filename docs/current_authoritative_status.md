# Current Authoritative Status

本文件是当前项目状态的唯一权威入口。任何论文、答辩或 README 状态描述都应与本表一致。

| Capability | Status | Verifier | Evidence | Hardware Claim |
|---|---|---|---|---|
| PCSC / ETEAC / AUTO | ACCEPTED | `scripts/verify_phase8_2.py` | Phase 8 artifacts | 不涉及真实硬件 |
| MuJoCo simulation | ACCEPTED | `scripts/verify_phase9.py` | `artifacts/phase9` | 不涉及真实硬件 |
| Isaac / cross-backend | `PHASE9_2_ACCEPTED` | `scripts/verify_phase9_2.py` | `artifacts/phase9_2` | 不涉及真实硬件 |
| MoveIt Runtime Dry-Run | `PHASE10_MOVEIT_DRY_RUN_ACCEPTED` | `scripts/verify_phase10_2a.py` | `artifacts/phase10` | `sent_to_hardware=false` |
| Dashboard Console | `PHASE10_2B_CONSOLE_ACCEPTED` | `scripts/verify_phase10_2b.py` | `artifacts/phase10/phase10_2b` | 不涉及真实硬件 |
| Level 0 framework | `PHASE10_LEVEL0_FRAMEWORK_ACCEPTED` | `scripts/verify_phase10_2c_level0.py --fake` | `artifacts/phase10/level0` | fake/framework；真实 Level 0 未开始 |
| Simulation Workbench | `PHASE11_SIMULATION_WORKBENCH_ACCEPTED` | `scripts/verify_phase11_simulation_workbench.py` | `artifacts/phase11/verification` | 不涉及真实硬件 |
| Simulation Runtime | `PHASE11_1_SIMULATION_RUNTIME_ACCEPTED` | `scripts/verify_phase11_1_simulation_runtime.py` | `artifacts/phase11_1/verification` | 不涉及真实硬件 |
| Model Control Center | `PHASE11_2_MODEL_CONTROL_CENTER_ACCEPTED` | `scripts/verify_phase11_2_model_control.py --ci` | `artifacts/phase11_2/verification` | 不涉及真实硬件 |
| Simulation AI Console | `PHASE11_2_SIMULATION_AI_CONSOLE_ACCEPTED` | `scripts/verify_phase11_2_model_control.py --ci` | `artifacts/phase11_2/verification` | `dispatch=false` 的 planner dry-run |
| Local model runtime | NOT_ACCEPTED | `scripts/verify_phase11_2_model_control.py --ollama` | 无真实本地模型 accepted evidence | installed_model_count=0 |
| Ollama runtime | NOT_ACCEPTED | `scripts/verify_phase11_2_model_control.py --ollama` | `ollama_runtime_status=SKIPPED` | 不涉及真实硬件 |
| Phase 12 smoke suite | `PHASE12_EXPERIMENT_SUITE_READY` + `PHASE12_THESIS_ASSET_PIPELINE_READY` | `scripts/verify_phase12.py --smoke` | `artifacts/phase12` smoke artifacts plus `artifacts/phase12/verification_phase12_1/phase12_smoke_status_correction.json` | 90 rows at `7b4c9af` are `SYNTHETIC_PIPELINE_SAMPLE`; original smoke summary retained and superseded；不涉及真实硬件 |
| Phase 12 validation suite | `PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED` + `PHASE12_VALIDATION_ANALYSIS_PACKAGE_ACCEPTED` | `scripts/verify_phase12.py --validation --artifact-root artifacts/phase12_2_clean/validation` | `artifacts/phase12_2_clean/validation` | clean provenance；540 rows，466 runtime-completed rows，74 rows blocked before runtime；不涉及真实硬件 |
| Phase 12 full final evaluation | NOT_ACCEPTED | `scripts/verify_phase12.py --full` | 无 full accepted artifact | full profile required before final thesis conclusions |
| Real robot validation | NOT_STARTED | 无 | 无 | `highest_real_hardware_acceptance_level=NONE` |

硬件边界：

- `real_controller_contacted=false`
- `hardware_motion_observed=false`
- `hardware_write_operations=[]`
- `real_robot_validation=NOT_STARTED`
- `highest_real_hardware_acceptance_level=NONE`

禁止声明：

- `BIGSMALL_REAL_ROBOT_PROJECT_ACCEPTED`
- 真实机械臂运动实验完成
- Level 1-6 验收完成
