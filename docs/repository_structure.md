# Repository Structure

This document explains the repository layout and the boundary between source, documentation, generated data, and artifacts.

| Path | Responsibility |
| --- | --- |
| `.github/` | GitHub Actions workflows. CI must remain software-safe and must not claim runtime validation without evidence. |
| `artifacts/` | Accepted verifier evidence and generated run logs. Artifacts are not source code and should not be reformatted casually. |
| `assets/` | Robot and simulator assets such as MJCF models. |
| `configs/` | Reproducible configuration. `configs/real_robot` must contain examples only, never real IPs, serials, or tokens. |
| `contracts/` | JSON examples and schema-facing material for task contracts. |
| `data/` | Local runtime data such as SQLite files. These are not authoritative source. |
| `docs/` | Architecture, safety docs, phase reports, audits, and project documentation. |
| `edge/` | Top-level explanatory directory. Runtime edge implementation is in `src/cloud_edge_robot_arm/edge`. |
| `environments/` | Environment support material. |
| `experiments/` | Experiment baselines and local result areas. Large generated results stay out of source unless intentionally accepted. |
| `ros2_ws/` | ROS 2 workspace source and generated build/install/log outputs. Generated subdirectories are ignored. |
| `scripts/` | Verifiers, demos, runtime evidence runners, and orchestration entrypoints. See `scripts/README.md`. |
| `shared/` | Historical/top-level route notes. |
| `simulation/` | Top-level explanatory directory. Runtime simulation code is in `src/cloud_edge_robot_arm/simulation`. |
| `src/` | Authoritative Python package source. `src/cloud_edge_robot_arm` is the runtime implementation. |
| `tests/` | Unit, integration, contract, source-guard, and artifact tests. Tests are organized by behavior and historical phase where useful. |

## Empty, Duplicate, and Historical Directories

Top-level `edge`, `shared`, and `simulation` are retained for compatibility and documentation. They should not be treated as authoritative runtime packages.

Historical documents under `docs/phase*` and `docs/reviews` are retained for traceability. Do not delete them during repository governance.

`artifacts` contains evidence. New governance work should not rewrite historical runtime evidence unless a verifier command intentionally regenerates it.
