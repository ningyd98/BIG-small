# Scripts Index

Scripts are grouped by purpose and hardware risk. Existing verifier paths remain stable.

## Core checks

| Script | Purpose | CI-safe | Artifact | Hardware |
| --- | --- | --- | --- | --- |
| `run_checks.sh` | Full local software check wrapper | Yes | Some verifiers write artifacts | No |
| `check_docs.py` | Documentation consistency checks | Yes | No | No |
| `verify_project.py` | Profile-based verifier orchestration | Depends on profile | Summary JSON | No hardware profiles by default |
| `validate_contract_examples.py` | Validate contract examples | Yes | No | No |

## Edge runtime demos

| Script | Purpose | CI-safe | Artifact | Hardware |
| --- | --- | --- | --- | --- |
| `run_fixed_pick_place.py` | Mock fixed pick-and-place flow | Yes | Optional logs | No |
| `run_fault_injection_suite.py` | Mock fault injection scenarios | Yes | No | No |
| `run_phase2_task.py` | Phase 2 task runtime example | Yes | Local DB optional | No |

## Safety verification

Phase 3 scripts exercise SafetyShield and integrated edge safety paths with Mock/FakeSystem only. They are CI-safe and do not contact hardware.

## Cloud planning

Phase 4 scripts exercise planning adapters, malformed output repair, idempotency, and edge dispatch through software-only paths.

## PCSC / ETEAC / AUTO

Phase 5-8 verifier scripts validate supervision, event-triggered autonomy, Skill Cache, RiskEvaluator, AUTO, and experiment evidence. These are software-only.

## Experiment runners

`run_phase8_experiments.py` and Phase 9 benchmark scripts may generate artifacts. They remain non-hardware unless a documented runtime profile explicitly requires Isaac or ROS 2 / MoveIt.

## MuJoCo

Phase 9 MuJoCo scripts run local simulation and do not connect to real hardware.

## ROS 2 / MoveIt

| Script | Purpose | CI-safe | Hardware |
| --- | --- | --- | --- |
| `phase9/activate_ros2_moveit_env.sh` | Activate ROS 2 / MoveIt environment | No | No |
| `verify_phase9_1.py` | ROS 2 / MoveIt acceptance aggregate | Environment-specific | No |
| `verify_phase10_moveit_dry_run.py` | MoveIt Runtime Dry-Run planning-only evidence | Environment-specific | No |

MoveIt dry-run must not call execute or connect to a real controller.

## Isaac

Phase 9.2 Isaac scripts require an Isaac Sim 6.0 compatible host. They produce runtime artifacts but no real hardware evidence.

## Cross-backend

`run_phase9_2_cross_backend.py` compares MuJoCo and Isaac artifacts by scenario/seed. It rejects Isaac fallback and static metrics.

## Phase 10 dry-run

| Script | Purpose | CI-safe | Hardware |
| --- | --- | --- | --- |
| `verify_phase10_0.py` | Config/gate/fault executable checks | Yes | No |
| `verify_phase10_1.py` | Synthetic framework dry-run | Yes | No |
| `verify_phase10_2a.py --skip-runtime` | CI-safe Phase 10.2A aggregate | Yes | No |
| `verify_phase10_2a.py` | Formal aggregate using MoveIt dry-run evidence when present | Environment-specific | No |

## Real hardware acceptance

`run_phase10_acceptance_level.py` is real-hardware-only when a site config and operator workflow exist. It must not be run automatically by CI or `all-available` profiles. It provides single-level acceptance only and does not run Level 1-6 in a batch.
