# R544 Molmo Integration Boundary Repair Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` for one bounded implementation pass, with expected RED tests before code. Existing user/parent authorization covers execution; no additional architecture approval or agent dispatch is required. No second independent review is required for this pass; verify the exact acceptance below.

**Goal:** Close five confirmed review defects without changing selected models, calibrated geometry or execution policy.

**Architecture:** Pin request/task identity through the existing adapter, strictly decode skill JSON, and make the diagnostic persist honest lifecycle evidence and outcome. Reuse current transport and secret/profile services; preserve legacy planner behavior.

**Tech Stack:** Existing Python 3.12, Pydantic, pytest, Ruff; CPU fixtures only for repair verification.

**Spec:** `docs/superpowers/specs/2026-11-10-molmo-opencv-grounded-planner-design.md`; R542 plan remains authoritative. Actual planner: `gpt-6-astra`.

## Global constraints

- Input inventory: all eight review-request entries matched. Recheck before edits; hashes are copied to plan.json. Do not modify original failure evidence. R545 runtime-only launcher may proceed separately without altering these source inputs.
- Edit only `src/cloud_edge_robot_arm/vision/grounded_planner.py`, `src/cloud_edge_robot_arm/vision/molmo_pointing.py`, `scripts/probe_molmo_grounded_planner.py` and their three corresponding test files. `planner.py` and `tests/test_rgbd_planning.py` remain verification inputs; no change needed. Add R544 step/implementation reports and logs under this round. Author's existing R542 guide/report work continues independently.
- No dependency/model/SDK/calibration/source-asset changes, no new default planner, no cloud downgrade, no secret/header logging, no profile activation, no hardware dispatch. Preserve Sol identity and transport security. No paid calls by default.
- R542 cumulative native budget remains <=1 model-load start and <=8 generation starts, including failures; R544 does not reset it or authorize another load. This repair uses zero actual model/cloud/hardware calls. Real smoke still requires R542 admission plus separate R545 runtime evidence.
- Preserve all historical raw/failure bytes. Raw input/output stays local under an ignored boundary; only derived nonsecret reports/source/tests are deliverable. A manifest is not a full remote reproduction bundle.

## Review focus

1. Request observation/instruction/task context replacement during either local query or cloud response must produce no actionable draft.
2. Duplicate `skills` or `reason` keys, including escaped-equivalent keys, must fail closed before schema validation.
3. Native paid timeout, invalid decision, empty decision or pipeline rejection must return nonzero; no-paid native geometry readiness retains its separate limited meaning.
4. Normal/fresh/replay inputs, cloud request/response bodies, identity provenance and failure manifests must survive independently of successful parsing.
5. Successful generation followed by decode failure must retain token IDs and a completed-generation count; failed generation starts still consume budget.

## Failure evidence and causes

See review.md I1–I5 for exact source lines, verbatim CPU reproduction scripts and outputs. Original Ruff seven-E402 output remains `original-ruff.stdout` / `.stderr`. `plan.json` records SHA256 for eight sources/tests, original Ruff evidence, spec/plans, reproduction evidence and this durable review. Findings: mutable request identity checked only at entry; last-key-wins JSON; geometry-only native success predicate; incomplete capture/finalization; post-decode token persistence/accounting. These are confirmed defects, not hypotheses about model quality.

## Task 1 — Bind the whole in-flight planning context and reject ambiguous skills

**Files:** `grounded_planner.py`, `tests/test_molmo_grounded_planner.py`.
**Interfaces:** `MolmoGroundedPlannerAdapter.plan(request) -> PlannerDraft` and `SkillDecision` stay public-compatible. Add private strict JSON decoding and context-check helpers as needed; no changes to shared transport or legacy VisualDecision decoding.

- [ ] Write `test_inflight_request_context_drift_is_closed`, parametrized over observation replacement, user_instruction, control_mode/safety context, and task descriptor replacement; trigger after local query 1, query 2 and cloud response. Capture the request baseline before calling. Assert sentinel/no actionable contract, no subsequent cloud call for local-stage drift, and no old-evidence/new-request contract. Add coverage for invalid copied checksum and second-endpoint bound-point mismatch if not already explicit. Existing timeout/config-drift tests remain.
- [ ] Write `test_skill_json_duplicate_keys_are_rejected`: raw strings with `skills:[]` then valid sequence, reverse order, repeated equal values, duplicate reason and escaped-equivalent key. Assert parse_error and parsed_json=None. Preserve valid JSON strict types, extra-field/order/empty-skill behavior.
- [ ] Run new cases RED with the existing app test interpreter; expected failures are current PLANNED/accepted outcomes. Record commands/output before fixing.
- [ ] At plan entry capture immutable original request context and descriptor identity (canonical JSON hash of the validated request and task is acceptable). Use original semantics for the entire plan and verify current request/task against those snapshots at every existing freshness boundary, including immediately before building/returning a draft. Check observation binding against the original complete checksum; do not update it on drift. Keep cloud request-settings fingerprint check. Context mismatch maps to REQUEST_MORE_OBSERVATION. Avoid exporting whole request hashes containing secrets; these request models carry scene/task context, not transport credentials.
- [ ] Decode model content with `json.loads(..., object_pairs_hook=reject_duplicates, parse_constant=reject_nonfinite)` then `SkillDecision.model_validate(value, strict=True)`. Reject duplicate keys at every object depth; do not normalize a refusal into valid skills. Catch JSON/value/schema errors with existing invalid-decision result. No permissive repair/fallback.
- [ ] Record immutable cloud model snapshot/hash and, when supplied by factory, role snapshot/digest (including selected profile/source hashes) in observation evidence; keep local perception provenance separate. Fixtures without a role snapshot stay explicitly without accepted-role claims. Assert no secret in JSON and evidence matches the actual frozen request configuration.
- [ ] Run all grounded tests GREEN, including valid pipeline and Sol route/default-payment tests.

## Task 2 — Make diagnostic status and raw evidence complete

**Files:** CLI and `tests/test_molmo_grounded_cli.py`.
**Interfaces:** `main(argv) -> int`, existing CLI flags retained. Add only private helpers for exclusive raw writes, manifests and final report accounting.

- [ ] Add RED tests for paid timeout, malformed/empty skill reply and pipeline rejection: each must have exit2/diagnostic_passed=false even with local geometry READY. Paid successful fixture requires PLANNED, complete expected attempts, and observed paid-request start; status may say accepted integration but must not imply physical/formal success. No-paid native geometry-only success remains allowed with real_cloud_status=NOT_PERFORMED; replay remains REPLAY and requires PLANNED. No vacuous all([]) pass.
- [ ] Add RED evidence tests: normal-input and fresh-capture runs retain exact original request/descriptor bytes plus fresh post-load acquired request/RGB/depth when applicable; replay retains exact supplied fixtures. Hash and manifest every raw file. Paid transport observer must save exclusive numbered request/response body files (no headers/secrets), preserve actual cloud content including invalid/refusal text, and retain bounded metadata for responses/envelopes/errors. Successful and failed runs finalize report plus manifest; failed-load path keeps count1 from load-started and manifests its failure bytes. Inject an HTTP/decoder error after response and verify raw bytes remain. Verify preexisting output remains untouched and source input bytes stay unchanged.
- [ ] Add paired template tests authorized by parent: `--mode native --capture-fresh` accepts a valid InitialPlanningRequest with observation=None, loads first, captures genuine new observation, validates/binds it and then plans. Missing observation without that exact mode/flag remains rejected before load. This avoids manufacturing a dummy/retimed historical sensor record. Do not refresh archived timestamps; retain template and acquired inputs separately.
- [ ] Implement mode-aware success calculation: dry-run validates configuration only; replay requires nonempty complete PLANNED attempts; native no-paid requires nonempty complete geometry-ready attempts; native paid additionally requires successful planned pipeline outcomes and real transport-attempt accounting. Keep individual local/cloud/pipeline states and actual calls separate. Failed real call stays ATTEMPTED/FAILED as appropriate, never NOT_PERFORMED or accepted.
- [ ] Read and preserve the exact input bytes used for parsing (one read, not reread after use); use duplicate-rejecting/nonfinite-rejecting JSON for config/replay reads too. Persist raw inputs only after exclusive output creation; dry-run can retain inputs while still having zero model calls. Attach per-attempt evidence/raw manifest references and cloud snapshots from Task1. Preserve local raw responses independently of parsing and save draft.raw_text locally rather than dropping it. Derived report may contain hashes/relative paths, not full raw bytes or credentials.
- [ ] Factor finalization so exceptions after output creation still emit counters, all existing raw-file hashes and failure report; do not mask the original error if finalization itself fails. Use current provider counters or persisted load-started record if construction failed. Correct `real_cloud_status` on exception whenever paid starts exist. Do not claim atomic completion after process kill; preserve durable start records for recovery. Keep exclusive-create semantics.
- [ ] For the seven E402 findings only, add narrow documented `# noqa: E402` on the bootstrap-dependent import statements (or equivalent minimal per-file annotation). Do not move bootstrap after imports or disable unrelated lint rules. Verify direct `--help` still works outside installed-package context.
- [ ] Run CLI tests GREEN, with monkeypatched native/resource/cloud boundaries and no real network/GPU.

## Task 3 — Preserve generation completion before decode

**Files:** `molmo_pointing.py`, `tests/test_molmo_pointing.py`.
**Interface:** Native result/provider signatures and <=8 budget unchanged. Define generation_calls_completed as successful generate plus synchronization, independently of decoding/parsing success; failures after that point have a completed generation but failed result.

- [ ] Write `test_decode_failure_retains_generated_tokens`: fake generate returns IDs, decode raises. Expect starts1/completed1, exact output-token-ids.json and generation timing/completion record persisted, failure record retained, no returned BoundPointResult. Also assert failed generate has starts1/completed0 and no retry/reload; cap output remains INVALID with completed1. Capture expected RED.
- [ ] After successful generate and synchronization, increment completed count and preserve output IDs/timing before calling decode. Retain a separate completion-stage record/counter so failure to decode/write/result-parse cannot erase the generated tokens or misstate a model failure. Keep raw text exclusive-write as soon as it exists, then parse; keep failure-stage/error type and current counters. Do not fake raw text when decoding failed. Include per-attempt elapsed timing in failure metadata where available.
- [ ] Run all native provider CPU tests GREEN. Asset/version checks, CUDA/BF16 contract, prompts, special-token decode options, max_new_tokens512 and budgets unchanged.

## Final verification and delivery

- [ ] Recheck input applicability immediately before edits; preserve review/plan/original logs. Execute tasks sequentially in one fix pass; expected RED cases above do not trigger a new Astra round. Any different root cause, input drift, changed geometry threshold or need for a new source/dependency file pauses affected work for next actual Astra plan.
- [ ] With `/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python`, run `-m pytest tests/test_molmo_pointing.py tests/test_molmo_grounded_planner.py tests/test_molmo_grounded_cli.py tests/test_rgbd_planning.py tests/test_rgbd_top_grasp.py tests/test_rgbd_role_models.py -q -p no:cacheprovider`. Use authorized host loopback if required. Record actual count; prior relevant baseline is parent220, independent new-module100. Run existing Ruff executable with `--no-cache` on all eight input Python files, and `git diff --check`; all must pass. Do not broaden tests repeatedly without cause. Existing full-suite run/result is independent and must be recorded separately; do not silently repair unrelated full-suite failures here.
- [ ] Record RED/GREEN, old/new hashes, commands, exits, scope diff and remaining real-evidence limits in R544 implementation report; link from R542 phase summary. Commit only explicitly verified paths plus intended reports, then follow authorized branch push/local-upstream-remote SHA equality policy. Never stage local raw, databases, credentials, SDK/weights.

## Preconditions and acceptance

Managed worktree writes require scoped approved access; tests use existing app environment, not a dependency install. R545 exclusively owns any native-runtime overlay. Expected completion is software boundary repair and CPU evidence only. Real local, real cloud, hardware and formal research acceptance remain separately NOT_PERFORMED unless separately evidenced under their original gates. Preserve total R542 budgets even across processes/reports. Self-review: all five Important findings have explicit RED/GREEN acceptance and bounded files; original architecture remains unchanged; no unresolved design approval is required.
