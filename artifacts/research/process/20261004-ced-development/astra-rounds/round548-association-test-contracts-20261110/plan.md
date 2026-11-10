# R548 Association Test Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for one bounded task. Existing authorization permits implementation; no extra review or sub-agents. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Correct an incomplete RGBD test fixture and assert native coordinate evidence at the actual pre-geometry rejection boundary.

**Architecture:** Test-only correction; production association, safety checks, evidence and budgets stay frozen.

**Tech Stack:** Existing Python3.12 app environment, pytest and Ruff.

**Spec:** R548 request.json; R547 association plan remains authoritative. Actual planner_model `gpt-6-astra`.

## Global Constraints

- All five request inputs matched bytes/SHA256 during planning. Recheck before changes.
- Edit only `tests/test_molmo_point_association.py`, `tests/test_molmo_grounded_planner.py`, and the single UncalledCloud constructor in R547 round-local `implementation/replay_association.py`. Keep both production source hashes exactly unchanged, as well as legacy geometry/calibration/thresholds/native outputs.
- Preserve both R547 original test-red.log and test-green.log byte-for-byte. Reports may be added under R548 and referenced by R547 summary; never rewrite original test history.
- No actual model/cloud/hardware calls. Cumulative actual state remains1load/2generations. R547's remaining optional1load/2generations allocation is unchanged and not exercised by this test repair.

## Review Focus

- A valid fixture must reach the function under test rather than fail model construction.
- Coordinate mapping evidence is native_original_pixel_target; original_pixel_target is later geometry input, unavailable on early rejection.
- New assertions must preserve REQUEST_MORE_OBSERVATION/no-cloud behavior, not merely remove a failing assertion.
- Existing negative tests must actually execute association after fixture correction; they must not all pass from a common setup failure.
- Historical blocked RED results must not be relabelled as meaningful missing-helper failures.

---

## Failure evidence and diagnosis

Current R547 test-green.log reports **28 failed,83 passed**:25 association cases fail constructing RGBDObservation because required `sim_time_s` is omitted in association_scene(); they have not reached association logic. Three test_pixel_mapping_once cases fail KeyError for `original_pixel_target`. Source inspection confirms unchanged normalized mapping is recorded as `native_original_pixel_target` before the helper, and these boundary/background points are rejected by association before ground_observation creates geometry evidence. This is consistent with the intended R547 boundary, not justification to populate fabricated geometry fields.

Initial test-red.log reports **33 failed,78 passed**. Its25 fixture-blocked cases are **not** valid missing-module or behavior RED evidence. Preserve that distinction in R547/R548 reports; the other eight integration failures remain as originally logged. Parent reports the new near-point pipeline positive and seven old tracker safety negatives now pass, and four-file Ruff passes; these do not establish the25 blocked tests' behavior.

Supplementary same-root diagnostic fixture error: offline static association/geometry/tracker assertions passed, but UncalledCloud omitted explicit provider, so RGBDPlannerAdapter defaulted to ollama while its snapshot declared openai_compatible. The production wrapper correctly rejected that mismatch before the stale check. `offline-replay.stderr` preserves this original failure; it is not a geometry or TTL defect. Both supplemental input hashes matched.

## Task 1 — Repair only test setup and boundary assertions

**Files:** `tests/test_molmo_point_association.py::association_scene`; `tests/test_molmo_grounded_planner.py::test_pixel_mapping_once`.

**Interfaces:** RGBDObservation requires `sim_time_s`; no production signature changes. Native coordinate evidence remains exactly the converted original-image pixel, before optional association.

- [ ] **Step 1 — Preserve evidence and recheck frozen inputs.** Record hashes for both original logs and the two production modules. Current28 failures are the valid evidence for this test-contract repair; do not claim all are missing-helper RED. No production rollback is required to recreate history.
- [ ] **Step 2 — Apply the two exact test edits.** Supply `sim_time_s=0.0` in association_scene's RGBDObservation constructor; this is explicit synthetic fixture time, not a rewritten real acquisition. In test_pixel_mapping_once capture the existing third adapter_fixture return as `bodies`, assert `draft.observation_evidence["native_original_pixel_target"] == [pixel,26]`, assert `draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"`, and assert no cloud request bodies. In the round-local replay script add only `provider=snapshot.provider` to the UncalledCloud constructor, retaining existing endpoint/model/snapshot and no-call stubs. Keep all normalized cases0/500/1000, expected pixel0/40/79 and the native output construction unchanged. Do not relax any other expected rejection, remove negative cases, or add original_pixel_target to production.
- [ ] **Step 3 — Run previously blocked tests and mapping tests.** `/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest tests/test_molmo_point_association.py tests/test_molmo_grounded_planner.py::test_pixel_mapping_once -q -p no:cacheprovider`. Expected all25 helper cases plus3 mapping cases pass with actual helper execution, no fixture ValidationError. Inspect any failures individually; a newly exposed helper defect is a new root cause requiring the next actual Astra plan, not permission to adjust production or weaken tests here.
- [ ] **Step 4 — Verify full scoped regression.** Same interpreter, `-m pytest tests/test_molmo_point_association.py tests/test_molmo_grounded_planner.py tests/test_molmo_pointing.py tests/test_molmo_grounded_cli.py tests/test_rgbd_planning.py tests/test_rgbd_top_grasp.py tests/test_rgbd_role_models.py tests/test_opencv_target_evidence.py -q -p no:cacheprovider`. Use established host loopback permission if necessary; no installs. Run existing Ruff on the two changed tests and `git diff --check`. Record actual totals and confirm production module SHA256 values remain exactly those in this plan.
- [ ] **Step 5 — Re-run the corrected offline diagnostic.** Use `PYTHONPATH=/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src` and the existing app interpreter with R547 `implementation/replay_association.py`. Save new stdout/stderr under new R548 filenames, never overwrite original offline-replay.stderr. Expected static nomination(179,119) and unchanged geometry checks pass, then real adapter rejects unchanged archived input with capture_time_not_fresh and points.calls=cloud.calls=0; all26 native01 raw files verify. Add this round-local file to scoped Ruff/diff checks. No timestamp/camera rewrite, actual perception or model budget use.
- [ ] **Step 6 — Correct reporting and deliver explicit paths.** Write R548 report describing the original fixture blockage, corrected test execution and mapping semantics. Update the R547 phase summary to distinguish original setup failures from meaningful functional RED/GREEN; no claim of25 missing-module RED. Locally commit only the two tests, single round-local diagnostic fixture correction and intended derived reports under R547's no-upload/public-push boundary. Keep raw/failure logs unchanged.

A synthetic missing-helper reconstruction is **not required** for this narrow repair: it cannot retroactively make the original run valid TDD evidence. If a targeted sensitivity check is useful, run only in an isolated subprocess with an explicitly temporary import blocker/snapshot and label it `POST_IMPLEMENTATION_SYNTHETIC_MISSING_HELPER_CHECK`; preserve fixture success first and capture raw result. Never remove/rename production source, modify original logs, or call that the original RED. This optional check grants no additional production scope.

## Preconditions and acceptance

Existing app interpreter/dependencies and managed-worktree write permissions suffice. pytest already resolves managed/src; independent stdin diagnostics require explicit managed/src PYTHONPATH. All actual model/cloud/hardware boundaries remain unused. Acceptance is valid test execution, correct native-coordinate assertion and retained rejection semantics; real-local/cloud/physical/formal acceptance are NOT_PERFORMED by R548. New behavioral failure, changed input assumptions or requested production repair requires a new actual Astra plan. No extra review/sub-agent is needed.

## Verified inputs and preserved original RED

- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/tests/test_molmo_point_association.py` — 5305 bytes — SHA256 `a92dc4f92942045e8230d5e77ec87de229df6ce31f37dd7ae8f47d54dd4cb035`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/tests/test_molmo_grounded_planner.py` — 23353 bytes — SHA256 `686e59b0a6946e72a9ab2f0d4e357ec3bfe6347c3a109d70fba5cf63a94709eb`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/point_association.py` — 7450 bytes — SHA256 `72c19fe7202c55451e5ee39f1c8e980cf3621d6fbbc257f9162ef8a3ff81692b`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/grounded_planner.py` — 16214 bytes — SHA256 `91ac346517b0fc037148b5d585896cbf8609382dd747b889614b3e5f9ebd3ec0`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round547-molmo-point-component-association-20261110/test-green.log` — 95191 bytes — SHA256 `5437cbff079511efbc10138dd908d30445f69dee6e46d9197cda460142f7a896`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round547-molmo-point-component-association-20261110/test-red.log` — 32583 bytes — SHA256 `f2f06fefb0e7e9fc2a21a4817f9323973dda1694a4ea46e6e8faa3772207012c`

Self-review: both test edits and supplemental diagnostic fixture correction supported by source/raw evidence; no production change; prior RED limitations explicit; no unresolved decision.

Supplemental verified inputs:

- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round547-molmo-point-component-association-20261110/implementation/replay_association.py` — 5722 bytes — SHA256 `fa4656b72391e704349fb4357c294ae30bafdcbf7e3d7d3d505db3b59e81217a`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round547-molmo-point-component-association-20261110/offline-replay.stderr` — 1043 bytes — SHA256 `4decb4d703f14eba46c5a62505e7a05aa1d771b7aca69ac2e0e0787ea8ccbe05`
