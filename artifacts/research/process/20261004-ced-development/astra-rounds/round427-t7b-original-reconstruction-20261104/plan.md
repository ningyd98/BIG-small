# R427 original observed-endpoint reconstruction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Parent implements inline with the existing ledger; no renewed user approval. Steps use checkboxes.

**Goal:** Reconstruct original-file-backed MOVE_ABOVE/APPROACH observed-return G/U/L/M/C diagnostics while completion qualification remains UNKNOWN.

**Architecture:** Reuse the strict pinned registration as a file manifest, RawV3 graph, actual RGBD decoder and owner binding replay. Compute R425 arithmetic at actual return without equating it to registered full H. Retain every group/action/acquisition allocation.

**Tech Stack:** Python frozen dataclasses, existing RawV3/Pydantic readers, NumPy/OpenCV CPU, pytest.

**Spec:** R91 design.md §§2–5; exact paths and SHA256 in adjacent plan.json.input_pins.

## Global constraints

Actual planner gpt-6-astra; baseline HEAD439bd9260ae83c6ad1ced8c9dde591be8d68e71b on research/20261004-continuation. All1315 existing baseline source/test/config files remain frozen. Do not edit old raw or dirty workspace-baseline/workspace-h3 gitlinks. No renderer/model/hardware/paid service, UTC/lease/performance detour, live authority or old e/v filling. All outputs SOFTWARE_ONLY/UNAVAILABLE/UNKNOWN, qualified_completion_metric=None. Default dt1/240 remains unchanged; observed step count is not full horizon.

## Problem, raw evidence and hypothesis

R427 intake/observation.json records the gap: R425/R426 accept public point arrays and scores; old native_geometry_calibration._group uses a different UTC/terminal recipe. RawV3 has original files, exact executed payloads/groundings and full object physics, but no TCP orientation, no new same-session OC1/full-H/hold provenance, and a nonintegral-ns default dt. A genuine observed-return reconstruction can advance the reader without inventing those claims. This is a read-only gap, not an implementation crash. Expected RED is missing-adapter only. Planner first write command used absent `python`, exited127 before writing; the plan uses explicit .venv/bin/python.

Before edits verify all plan.json.input_pins byte counts/SHA and HEAD. Do not rebaseline drift. Only consulted files are pinned. Unexpected failure,new cause or scope expansion requires another actual Astra plan before affected repair/retry.

## Review focus

- Real RGBD positive, never decoder/truth/binding monkeypatch; independent numeric oracle.
- Rehashed owner grasp coordinates must match decoded rigid contact before receipt replay.
- Every missing frame/action retains allocation and unavailable contribution.
- Actual return and complete H remain distinct even for a short successful action.
- RELEASE and five other unimplemented skills retain UNKNOWN; failure is never upgraded.

### Task 1: Original-file observed completion adapter

**Create:** src/cloud_edge_robot_arm/research/native_completion_originals.py; tests/test_native_completion_originals_v2.py; R427 implementation/run_validation.py. No old source/test edits.

**Interface:** `reconstruct_observed_completion_v2(registration: NativeCalibrationRegistration) -> ObservedCompletionReconstructionV2`. Exact frozen fields/types/constants in plan.json.api. Existing registration is a pinned original-file manifest and geometry carrier only; no old UTC recipe migration. Groups and all envelope allocation orders are preserved. Missing values None,collections tuples; top schema native.completion.observed-originals.v2. Observed metric is CompletionMetricV2|None; qualified metric is fixed None,not constructor-settable.

- [ ] **Step1: Write the focused tests and NEW serialized SOFTWARE_ONLY fixture.** No missing module import at collection. Use the existing raw/owner/independent BITS7 helpers, but actual decoding/binding must execute. Pin actual source files throughout identity,original plan,policy and inputs; align object/region IDs with geometry. Keep full120-step settle+1 action graph and all file inventories.

NEW tmp_path SOFTWARE_ONLY originals only; reuse raw_fixture/owner_values/owner_originals and independent BITS7 observation helper without decoder/truth/binder monkeypatch. Real current capture/source pins throughout identity/original/policy/inputs; align contract object/region IDs to object/target_region. Full120-step settle+1 action graph. Keep asset geometry(.035 half extents,marker_to_object(.1,0,.03505),object_to_tcp(0,0,.01)). Actual160px PNG with48px glyph,depth1,fx=fy=47/.045,cx=cy79.5,camera rotation diag(1,-1,-1),translation(.303,.1,1.07505) yields estimated center(.203,.1,.04). Independent truth(.2,.1,.04),identity rotation,TCP(.2,.1,.16),policy clearance.1/minheight.16,owner grasp(.203,.1,.05). Positive new synthetic success permitted; negative preserves original failed result. Update every dependent camera qpos,state hash,identity,interval,command,frame,join and file inventory consistently,serialize and reread. Never derive truth oracle from decoder. Original asset/camera validation remains strict.

- [ ] **Step2: Preserve one expected RED.** Run `.venv/bin/python <R427>/implementation/run_validation.py red`; select only test_original_adapter_api_is_present. Expected exit1 and assertion `missing production original completion adapter`,no other failure. Preserve raw evidence. Any other failure follows the Astra rule.

- [ ] **Step3: Implement the exact bounded reader.** Use the following pipeline,without modifying existing readers:

1. Exact NativeCalibrationRegistration only. Call revalidate for complete actual original/current-source inventories. Existing registry is a pinned file manifest/geometry description only: no UTC recipe migration. Strict RawV3 decode/validate and hash every envelope original_file_hashes entry under group directory. File/hash/schema failures ValueError. Preserve all group/action/frame allocations; graph INVALID/INCOMPLETE gives unavailable metrics.

2. Apply original_source_reasons; any source/asset mismatch poisons metrics. Preserve raw reasons and utc_mapping; do not alter old _group or pretend UTC/operational chronology is valid. Every result qualification remains UNKNOWN.

3. Every allocated frame must have original observation, exact joined state, registered camera descriptor/sim time/full dimensions. Actual detect_pose_marker then marker_to_object rigid reconstruction and full_rigid_geometry_errors; truth never enters decoder. G=max full-rigid errors over all allocated frames, None if any unknown/missing. Retain original_rgbd_fingerprint plus episode/scene fingerprints.

4. For each successful RETURNED MOVE_ABOVE/APPROACH require owner original,grounding,unique BEFORE_SUBMIT/AFTER_RETURN joins at interval start/end steps,and capture==dispatch. Actual end is observed return only. Build original OnlineEvidenceSnapshot/TCP/checkpoint; independently recompute decoded grasp contact via object_to_tcp and compare owner grasp_tcp at abs1e-9; destination/support match registered geometry; verify frame/object/region identities. Rebuild owner binding at recorded created_at; match digest,original plan,exact executed payload.

5. p comes only from rebound target_pose; rc/rt from reconstruct_truth_endpoint(scope,original policy,skill,capture/return original state); x from return TCP. Pass corresponding singleton points and complete G to completion_metric_v2. Store observed_endpoint_metric only. Failure,partial,unsupported,ambiguous or missing evidence retains row/reasons with None metric.

6. Preserve physics_dt_s verbatim and observed_steps=end-start. Do not call horizon kernel,round dt to ns,declare full H or feed these diagnostics into joint calibration.

- [ ] **Step4: Run one bounded GREEN.** `.venv/bin/python <R427>/implementation/run_validation.py green` runs the new test file plus the20 R425/R426 kernel cases and four legacy negatives listed in plan.json.verification.green_argv. All must pass,source-before/after drift empty,startup prerequisite pass,no timeout or owned-process leak. No fullsuite or unplanned retry.

- [ ] **Step5: Record and deliver.** Write step report and phase summary separating software validation from actual run/formal acceptance (both NOT_STARTED). Explicit-path commit/push verified delivery on research branch; compare local/upstream/remote SHA. Preserve historical failures/raw/frozen files.

## Exact focused test contracts

- `test_original_adapter_api_is_present`: Expected RED only: find_spec assertion missing production original completion adapter; no absent top-level import.
- `test_decoded_move_originals_match_independent_oracle`: Real decoder/binder/files: G=.003,p=(.203,.1,.16),rc=rt=x=(.2,.1,.16),U=.003,L=.003,M=0,C=.006,endpoint0,abs1e-8; capture=dispatch120,return121,observed_steps1; dt original1/240.
- `test_decoded_approach_uses_contact_without_clearance`: p=(.203,.1,.05),rc=rt=(.2,.1,.05),x=(.2,.1,.16); U=.003,L=sqrt(.003**2+.11**2),M0,C=.003+L,endpoint.11. No fabricated TCP rotation.
- `test_original_truth_drift_changes_metric_not_command`: Final object x=.204, capture .2, same decoded image,p.x=.203; consistently update new fixture camera qpos/state hashes. G=.003,U=.003,L=.003,M=.004,C=.010,endpoint.004. Truth never changes p.
- `test_changed_or_missing_actual_files_are_rejected`: Parametrize RGB,depth,records/truth,owner JSON,missing file,symlink,registry digest: pinned manifest unchanged, ValueError before numeric output.
- `test_rehashed_graph_and_owner_contradictions_are_unavailable`: Broken state join, duplicate BEFORE, executed payload mismatch, owner receipt mismatch, owner grasp_tcp+.02 even with internally regenerated receipt: no observed metric, preserve reasons/allocations.
- `test_unknown_or_missing_allocated_frame_poison_geometry`: Missing allocated frame record; actual blank/duplicate-marker pixels with consistent new hashes; wrong registered camera: all rows retained,G=None,all action metrics=None.
- `test_capture_and_return_joins_are_exact`: Nonzero capture age, missing AFTER_RETURN,duplicate AFTER_RETURN,wrong return step => None; never nearest-time/fallback state.
- `test_failed_partial_missing_and_unsupported_actions_are_retained`: Parametrize failed RETURNED,partial,missing span record,and GRASP/LIFT/MOVE_TO_REGION/PLACE/RELEASE/RETREAT. All original allocations stay, original disposition/success retained,metric None. RELEASE explicitly needs future PLACE/rigid evidence.
- `test_dt_and_non_authority_fields_are_immutable`: dt==original1/240; observed_steps separate; no full_horizon,legacy e/v,calibrated bound or publishing interface. Frozen SOFTWARE_ONLY/UNAVAILABLE/UNKNOWN and qualified_completion_metric=None init=False; no caller score accepted.
- `test_groups_and_returned_data_preserve_original_allocations`: Two assigned groups including unavailable one remain ordered with original ancestor/frame/action IDs. Detached serialization cannot mutate originals/results; changed original reread rejected; no group quantile.

## Validation budget, prerequisites and acceptance

The new lightweight wrapper reuses frozen R425 stage spec/environment,R426 runtime pins and unchanged R413 bounded_stage.py/events with R235 startup prerequisite. It only changes stage identity/paths/scope/nodes as needed. Use fresh red/green directories and basetemp,isolated cache/DB/resources,timeout600s each,no ports. Add new test/wrapper/plan pins and adapter only for GREEN; preserve all old pin values. Keep invocation,source-before/after,prerequisite,stdout/stderr,pytest events,junit,process/resource/cleanup/result evidence. Acceptance is genuine original-byte reconstruction and independent arithmetic plus24 existing checks,not a calibrated group or research completion.

Future real production prerequisites remain:

- Same-session producer OC1 preregistration/RESET/event chain tied to every original SHA and action/reference binding.
- Registered full S horizon including original/compiled/owner durations,rational default-dt support,builtin tails/waits without rounding or double counting.
- Unique controller/owner each-step and hold evidence,original deadline/hard-stop/failure preservation,no later-action contamination.
- All required frames/control points/hold conditions; RELEASE exact executed PLACE receipt and complete rigid grasp transform.
- Independent assigned groups/all-action joint calibration plus real online and physical outcomes before formal acceptance.
