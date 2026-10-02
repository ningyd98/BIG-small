# Ubuntu authoritative deployment plan

Goal: preserve the research lineage and operate entirely through Sim2Real simulated devices. No real controller contact, hardware read/write, motion or S3/S4 promotion. Historical artifacts remain immutable; experiments use unique directories and clean provenance.

- [x] Fetch/audit branch SHA, graph, merge-base, unique Phase13 diff and range-diff.
- [x] Create codex/ubuntu-integrated-deploy from origin/codex/macos-local-dev; migrate four reviewed Phase13 commits.
- [x] Install isolated core Python, verified Node, locked Dashboard/Chromium and record host inventory.
- [x] Run full Python gates (769 tests); fix runtime/evidence bugs; run all Dashboard gates (24 unit / 37 E2E).
- [x] Validate MuJoCo assets, adapter/worker and actual deterministic DR model application.
- [x] Run core Phase0–9 software verifiers, preserving scope and logs.
- [x] Deploy isolated ROS Jazzy/MoveIt; build persistent ASCII workspace and actual planning/mock-controller evidence.
- [x] Deploy Isaac 6.0 / Lab; run actual GPU app/adapter and Lab configuration materialization.
- [x] Execute existing cross-backend and Phase12 full pipelines; preserve rejection and physical-comparison limits.
- [x] Fix repetition aggregation with failing-before/passing-after regressions; reanalyze immutable full inputs separately.
- [x] Validate Rerun offline traces/sensor fields/time overlay and Sim2Real API/UI/locked gates.
- [x] Check real-model availability; validate fake Phase13 pipeline with zero authoritative fake rows.
- [x] Run Phase12 smoke and full run/analyze/export/verify; record full REJECTED, no final closure claim.
- [x] Reproduce historical thesis pipeline and render/inspect all DOCX/PDF pages; separate new full statistics.
- [x] Add and verify Linux install/doctor/start/test wrappers, preserving macOS support.
- [x] Record subsystem reports, dependency/disk usage, source provenance and deployment handover.
- [ ] Accept all Isaac DR parameters actually applied to the scene and Lab EventManager (configuration only so far).
- [ ] Accept strictly matched MuJoCo/Isaac trials and requested physical gap metrics (NOT_ACCEPTED).
- [ ] Connect already deployed MoveIt runtime to Phase12 adapter (currently hard-coded blocked).
- [ ] Run real LLM baseline when a real model service is available (BLOCKED).
- [ ] Accept final full evaluation and updated final thesis conclusions/layout (NOT_ACCEPTED).

Completed deployment work and outstanding research acceptance are detailed in [ubuntu_deployment_report.md](ubuntu_deployment_report.md). Checked items mean the documented operation was completed, not that every subsystem received unconditional acceptance.
