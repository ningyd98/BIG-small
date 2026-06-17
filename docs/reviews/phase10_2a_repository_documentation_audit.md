# Phase 10.2A-R Repository Documentation Audit

## Baseline

- Repository: `ningyd98/BIG-small`
- HEAD: `5dce1b0b491e41ad821fc4c4ca5c798e56eff552`
- `origin/main`: `5dce1b0b491e41ad821fc4c4ca5c798e56eff552`
- Worktree at audit start: clean
- Current accepted status: `PHASE10_MOVEIT_DRY_RUN_ACCEPTED`
- Real robot validation: `NOT_STARTED`
- Highest real hardware acceptance level: `NONE`

## Current Repository Information Architecture

- Authoritative Python source lives under `src/cloud_edge_robot_arm`.
- Top-level `contracts`, `edge`, `shared`, and `simulation` are explanatory or schema-facing directories; runtime code is under `src`.
- `configs` contains safety, Phase 9, and real robot example configuration. `configs/real_robot` must not contain real site IPs, serials, or credentials.
- `scripts` contains many phase-specific runners and verifiers, plus `run_checks.sh`; there is no script index or unified project verifier.
- `docs` contains architecture, phase reports, acceptance notes, safety docs, and historical planning documents, but no single documentation portal.
- `artifacts` contains authoritative evidence and generated run logs. It is not source code and should not be reformatted during documentation governance.
- `data`, `experiments/results`, ROS build outputs, and tool caches are local/generated data.

## README Issues

- The first section is a long phase-history paragraph rather than a project entry point.
- Current status is accurate but overloaded with Phase 9.1 historical blockers before the current Phase 9.2/10.2A status.
- Quick-start commands include many phase-specific and environment-specific verifiers, making CI-safe, runtime-specific, and real-hardware-only commands hard to distinguish.
- The directory structure still describes tests as Phase 0/1 era and does not reflect the current Phase 10 package, Phase 9.2 evidence, or documentation layout.
- Safety boundaries are present but not isolated as a clear statement for new users.

## Docs Issues

- There is no `docs/README.md` index, so users need to know phase numbers to find information.
- There is no current `docs/project_status.md` separating Phase 9.1 historical status from Phase 9.2 current final status.
- There is no `docs/repository_structure.md` explaining source directories versus explanatory top-level directories and artifacts.
- There is no `docs/verification.md` separating CI-safe, environment-specific, and real-hardware-only commands.
- There is no glossary, roadmap, changelog, or contribution guide.
- `docs/architecture.md` is useful but still reads as a chronological architecture log; it should become the current authority with explicit layers and diagrams.
- Historical documents such as `docs/repository_gap_analysis.md` are intentionally historical and should not be rewritten to current status.

## Scripts Issues

- There is no `scripts/README.md` grouping scripts by purpose, environment needs, artifact output, or hardware risk.
- There is no unified `scripts/verify_project.py` for safe profile-based verifier orchestration.
- Original verifier paths are stable and should remain compatible.
- Phase-specific scripts are numerous; moving them now would create more risk than value.

## CI Issues

- `.github/workflows/ci.yml` runs compile, ruff, mypy, pytest, and Phase 3-9 CI-safe checks.
- CI does not run Phase 10 software-side verifier checks.
- CI does not check documentation links, README script references, Mermaid fences, or sensitive path/token leaks.
- CI must not claim Isaac runtime, MoveIt runtime, or real robot validation unless a dedicated runtime job actually produces evidence.

## Naming and Status Inconsistencies

- README repeats `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK` without clearly separating historical Phase 9.1 context from current Phase 9.2 final acceptance.
- Current terms should be standardized as:
  - cloud intelligent planning: `云端智能规划`
  - edge safety execution: `边缘安全执行`
  - `PCSC`
  - `ETEAC`
  - `AUTO 双模式选择器`
  - `Synthetic Dry-Run`
  - `MoveIt Runtime Dry-Run`
  - `Real Robot Read-Only`
  - `Real Robot Motion`
  - `evidence`, `artifact`, `provenance`

## Proposed Modification Scope

- Rewrite `README.md` as a concise project entry document.
- Add documentation portal, project status, repository structure, verification, glossary, roadmap, changelog, and contribution documents.
- Update architecture and Phase 10 docs to align with Phase 10.2A evidence and boundaries.
- Add `scripts/README.md`, `scripts/check_docs.py`, and `scripts/verify_project.py`.
- Update `scripts/run_checks.sh` and `.github/workflows/ci.yml` for document checks and Phase 10 software checks.
- Add tests for documentation checks and unified verifier profiles.

## Explicit Non-Scope

- Do not modify `SafetyShield` decision semantics.
- Do not relax `HardwareExecutionGate`.
- Do not modify `PCSC`, `ETEAC`, or `AUTO` core behavior.
- Do not modify Phase 8, 9, or 10 authoritative experiment results.
- Do not delete accepted artifacts.
- Do not connect or command real hardware.
- Do not move Python source packages or break existing import paths.
- Do not remove existing verifier script paths.
- Do not rewrite, squash, amend, rebase, or force-push pushed `main` history.
