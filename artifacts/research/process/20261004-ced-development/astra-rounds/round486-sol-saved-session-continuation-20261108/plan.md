# R486 saved-session RGB-D continuation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to execute the bounded tasks below. This is the actual gpt-6-astra plan required by AGENTS.md; no additional user confirmation is needed for this already-authorized continuation.

**Goal:** Test the configured session through one existing RGB-D API call, then repair the statically identified saved-profile calibration omission with CPU evidence, preserving the running secret-bearing service.

**Architecture:** Existing FastAPI service owns the write-only InMemorySecretStore. The client selects the known successful profile and requests one simulator planning-only dry-run. The narrowly scoped source repair is independently verified in a fresh CPU test process; it is not injected into the running server.

**Tech Stack:** Python 3.12, FastAPI, pytest, existing MuJoCo RGB-D adapter, Linux flock.

**Spec:** `intake/continuation-context.json`, AGENTS.md, frozen R469/R475 plans. Input SHA256 values are in `input-pins.json` and plan.json. Original source excerpts are in `static-issue-evidence.json`; these are static evidence, not invented runtime failures.

## Global constraints and original issues

- User request: 当前已配置好云端大模型，请继续测试开发. Preserve visible pose markers, overhead RGB-D camera, controller choice and deferred edge-model choice.
- No key extraction, DB reading, process memory/environment reading, runtime monkeypatch/import hooks, secret export endpoint, server restart/reload, external model fallback, physics step or dispatch. No R469 execution in this round.
- R469 was not run; parent intake reports 261 pins without drift. Its runner requires hidden TTY getpass, whereas the successful key exists only in the running API profile `profile-4f24f5330ad644ad`. Its timeout is 30 s, versus frozen R469 profile `profile-a6a0273a17da4934` timeout 180 s.
- Existing dry-run captures S01_NORMAL_STATIC, seed0, 320×240 through default `assets/robots/franka_panda/scene.xml`; reset performs mj_forward and capture, not mj_step. get_sensor_frame returns the cached frame. Default domain_randomization=true with NONE is not the frozen false setting: report the exact difference. Normal path has one capture with two render passes, no instance segmentation. Actual render count is uninstrumented, not a measured exact count.
- Saved-profile `visual_planner()` currently uses image_size=(640,640) and omits coordinate_system/grasp_profile. Defaults are pixel/unconfigured. After a valid normal-sized visual response, `_ground_response` returns REQUEST_MORE_OBSERVATION with reason `top grasp requires a trusted MuJoCo upright-box calibration profile`. This known issue belongs to this plan, not a new round.
- Paid gate is the server's existing BIGSMALL_VLM_ALLOW_PAID_CALL flag; metadata READY does not prove it is enabled. No endpoint exposes or changes it. Permit a single diagnostic dry-run whose production guard blocks transmission if disabled; do not bypass or set the running process flag.
- One API planning request, at most one paid model call, completion ceiling 4096 including reasoning, reasoning_effort=low. This is a deliberate tightening of the authorized <=4 ceiling; do not consume remaining three calls. No retry, warm repeat, /profiles/.../test, /plans, extra capture or fallback. Profile max_retries=2 is metadata not consumed by this visual path: `_request_visual` invokes `_post` once, `_post` has one opener call and Sol rejects redirects. Pipeline repairs are local, not additional model calls; dry-run hardcodes repair_attempts=0, so do not claim this proves absence of local repairs.

## Review focus

1. Paid flag disabled, authentication/network failures: preserve response; no retry and no invented zero-cost claim when transmission is uncertain.
2. Valid cloud decision reaches the known calibration rejection: record reproduction, stop runtime work, proceed to scoped CPU repair.
3. Real/Isaac camera source or unconfigured generic adapter: preserve calibration rejection; never silently bless arbitrary hardware frames.
4. Client timeout/disconnect: server work may survive; client termination is not cancellation or renderer closure.
5. Source edit does not reload the live module; tests and live evidence refer to different generations. R469 pins must not be rewritten to conceal that.

## Task A — one existing-session integration observation

**Files:** Create only R486 `execution/` receipts, one `execution/run_once.py` client if needed, and excluded local raw under `cache/research/r486-sol-saved-session-20261108/`. Do not alter frozen R469/R475 files. The client must be a small one-shot API caller, not a new supervision framework. Do not import product modules, instantiate simulators, or obtain secrets in that client.

**Interface:** Base URL `http://127.0.0.1:8000`; GET `/api/v1/model-control/profiles`, GET `/api/v1/model-control/runtime`, POST `/api/v1/model-control/profiles/profile-4f24f5330ad644ad/activate`, POST `/api/v1/model-control/planner/dry-run` only.

- [ ] A1. Rehash all R486 inputs and the parent-reported 261 R469 inputs; record current HEAD and scoped dirty paths. Any unexpected code/config/asset drift stops dependent work. Confirm no R486 execution-start or raw attempt exists. Record profile metadata via the two GETs (5 s each, no retry); selected profile must match intake, be enabled and secret_present, max_tokens4096, timeout30, exact official Sol route. Snapshot original active ID for provenance. Do not read SQLite or secrets. Live profile changes/another operator mutation stop the run.
- [ ] A2. Acquire `cache/research/.r468-r469-gpu.lock` using flock LOCK_EX|LOCK_NB and hold across admission, activation, request and response persistence. A busy lock means WAITING_RESOURCE; no call, no automatic retry, no killing owner. This only coordinates cooperating R468/R469/R486 jobs; require no other known GPU workload or concurrent dashboard model action. Run each of the following exactly once with 8 s timeout and capture original stdout/stderr/rc:

```text
/usr/bin/nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader,nounits
/usr/bin/nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits
/usr/bin/systemctl --user show qwen38-flash-strata.service --no-pager --property=Id,LoadState,ActiveState,SubState,MainPID,ControlPID,ControlGroup,NRestarts
```

Require all rc0, GPU0 free>=2048MiB, compute-app output empty, qwen service loaded/inactive/dead, MainPID=ControlPID=0, disk free>=2GiB. No service actions. Admission failure closes without capture/model call. These checks are admission, not sustained RSS/VRAM measurements.

- [ ] A3. Under the lock, activate the known successful profile with a bodyless POST (5 s timeout, no retry), then GET runtime and profiles once each and verify the ID/config/route/budget. Activation is explicitly authorized by the continuation; leave this selected profile active and record it. No automatic restore that could overwrite another operator's choice. Unknown activation outcome stops before dry-run.
- [ ] A4. Exclusive-create `execution/execution-start.json` containing plan/pin digests, active metadata, UTC, max_calls=1 and exact request JSON below; flush it before transmission. Send exactly one POST, retaining response bytes/status/timestamps/hash in the local raw directory; no credentials in request payload or records:

```json
{"user_instruction":"pick the red cube and place it in the green target region","sample_scene":"S01_NORMAL_STATIC","control_mode":"PCSC","input_mode":"RGBD"}
```

`sample_scene` is accepted but RGBD path internally captures its fixed default; do not claim a configurable scenario. Profile timeout30 governs provider socket operations, not an absolute server deadline. Client uses 90 s observation deadline and 4MiB response ceiling. On complete HTTP response, capture lifecycle has returned through finally/shutdown under the pinned code; retain result and release lock after persistence. On timeout/disconnect/oversize/incomplete response, mark SERVER_REQUEST_COMPLETION_UNKNOWN, no replay, do not close the lock merely because the client deadline elapsed. Keep the one-shot owner's FD held in a quiet waiting state until existing evidence positively establishes request completion; no inferred closure from health/GPU free, no process kill, no new paid call. This endpoint has no completion/cancellation API, so unresolved work may need operator resolution. Do not wrap the lock owner in an outer timeout that releases its lock. No hard server resource/absolute-time guarantees are claimed.
- [ ] A5. Classify returned JSON. A disabled paid flag normally becomes PLANNER_FAILED with reason mentioning BIGSMALL_VLM_ALLOW_PAID_CALL (caught by Pipeline); capture/initialization exceptions become BLOCKED_BY_ENV. A valid decision with exact calibration reason, nonempty raw_planner_output, observation source=mujoco_camera, 320×240, S01 and sim_time0 is LIVE_SAFE_REJECTION_REPRODUCED. dispatch and hardware_execution must be false, scope RGBD_PLANNING_ONLY where supplied, final_contract null. Missing metadata stays missing. Record planned model-call bound <=1, actual sent count/tokens/cost UNKNOWN unless response proves it; no transport ledger is available. HTTP200 alone is not success. Any other failure stops further runtime work and preserves its original bytes; independent phase B may still proceed for the already-known static omission, but do not fix a new root cause under this plan.

## Task B — repair saved-profile snapshot, CPU only

**Modify:** `src/cloud_edge_robot_arm/model_control/service.py`, only `visual_planner()` snapshot construction, local imports, and a fail-closed check of the default calibration asset.
**Create:** `tests/test_model_control_rgbd_snapshot.py`.
**Interfaces:** Keep visual_planner() signature unchanged. Explicit project simulator settings: image_size=(320,240), coordinate_system="normalized_1000", grasp_profile=CURRENT_GRASP_PROFILE from vision.top_grasp (currently "mujoco_upright_box_v2"). This is the existing project default scene, whose SHA256 must equal `66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2`; Before selecting v2, read only the default SimulatorConfig model_path asset and require its SHA256 to equal calibration_asset_sha256(CURRENT_GRASP_PROFILE); missing/unregistered/mismatched asset raises RGBDModelUnavailable before planner creation/transport. This explicit trust check prevents marking a changed local scene as calibrated. Preserve provider/model/route/key lookup, max_completion_tokens4096/low, timeout30 and paid guard. Do not modify generic ModelConfigSnapshot defaults, frozen profiles, observation timestamps, capture code or calibration tables.

This phase is allowed after the exact live reproduction OR after static/CPU reproduction if A is resource/gate/environment blocked. It does not depend on spending a call. Paid failure of another kind is not permission to expand the repair.

- [ ] B1. Add isolated CPU regression tests with tmp_path repository and InMemorySecretStore containing a fixed fake test string, never live profile/DB. Forbid real sockets, simulator initialization, Renderer/MjModel/MjData/mj_step. Use production service.visual_planner and production RGBDPlannerAdapter.plan. Reuse the existing software-only 320×240 `_frame`, `_request`, `_wire` helpers from tests/test_sol_evidence_reader.py (explicitly install equivalent no-external-effects guards; importing helpers does not inherit their module autouse fixture). The fixture wire returns target=[250,500], destination=[750,500], current-v2 red top patch and green destination. Only frame.observation enters production, never instance IDs/labels. Assert exactly one fake transport request, grounded observed_scene, no sentinel, v2 calibration evidence and expected original target=(80,120), destination=(240,120), correct red-block/green-region task meaning. Validate the actual selected target surface and grounded destination against fixture observation.world_point and calibrated top-grasp result, not only snapshot fields. Inspect actual body for exact Sol route/model, low/max_completion_tokens4096 and two registered images decoded as 320×240. This must be RED before the fix due to existing calibration rejection, not network/import errors. The helper timestamps are fixed software data; planner.plan bypasses pipeline freshness; do not relabel that as live freshness.
- [ ] B2. In that file add focused tests: (a) paid flag absent raises RGBDModelUnavailable before mocked _post, calls0; (b) changing only the synthetic observation source to rgbd_camera/isaac_camera still returns the calibration sentinel with no observed_scene; missing default XML, changed asset digest or unregistered calibration rejects before transport; (c) non-square 320×240 synthetic observation with normalized center maps to (160,120) and two model image payloads decode as 320×240, not 640-square; (d) active-profile switch preserves the earlier snapshot identity/settings; (e) no-active-profile still delegates from_environment and legacy MOCK/RULE_BASED still rejected. Assert actual Sol route, model, timeout and generation values in the first behavioral test; no fake evidence of actual paid execution.
- [ ] B3. Run `.venv/bin/python -m pytest -q tests/test_model_control_rgbd_snapshot.py` once before the change; preserve full RED output/rc. Only the specifically expected snapshot/calibration assertions may fail. Then implement the explicit snapshot values and default-asset trust check described above. No feature flags, credential/session APIs, generic framework or alternate model.
- [ ] B4. Run the same focused command for GREEN, then adjacent CPU checks once:

```text
.venv/bin/python -m pytest -q tests/test_rgbd_grasp_scope.py tests/test_rgbd_normalized_protocol.py tests/test_rgbd_planning.py tests/test_rgbd_project_defaults.py tests/test_rgbd_gripper_calibration.py::test_repaired_gripper_planner_records_its_own_calibration tests/test_openai_sol_visual_migration.py
```

Do not run the whole gripper_calibration file: other tests create real MuJoCo capture sessions. Capture command/rc/stdout/stderr/duration and source diff/hash. Test network boundaries must remain mocked. Existing test fixture/schema mistakes within these specified cases may be corrected; an unexpected product failure/new root cause requires the next Astra plan before repair.

## Task C — generation boundary and delivery

- [ ] C1. Rehash unchanged inputs; expected changes are only service.py and new test file, plus R486 evidence/report. Preserve old pins and record before/after SHA. R469 source pins include service.py: after this edit the old R469 preflight is stale; mark FROZEN_INPUT_DRIFT_EXPECTED_AFTER_R486_FIX, not ready-to-execute. Do not rewrite R469 pins, preflight, source generation or original raw.
- [ ] C2. Record `software_fix_verified` only if RED→GREEN and adjacent tests pass. Record `live_fixed_generation_validated=false`: current server still owns old imported code and the session key. `/runtime/reload` merely reads metadata and cannot load the source fix. Do not call it to imply deployment. Smallest future live step is a separately planned normal server restart/code deployment plus user re-entry of the key through the existing write-only UI; never attempt to export/transfer the key automatically. Once current service can be intentionally replaced, revalidate the new live generation with an explicitly bounded call. Existing frozen R469 nominal additionally needs re-freezing for changed source and either its hidden TTY key or a separately planned server-owned evidence path; this API result is not that path.
- [ ] C3. Write R486 step-report with actual calls/outcome, static reproduction, test status, source-generation split, resource/closure uncertainties and future boundary. Summarize in the existing stage summary using exact scoped file edits only. Commit and push only named R486 plan/evidence/derived reports and the two scoped code/test files plus that summary; exclude full raw, DBs, secrets, weights and SDKs. Verify local/upstream/remote SHA, coordinating with unrelated Taichu changes; never stage their files.

## Acceptance boundaries and self-review

Development acceptance: meaningful CPU reproduction and passing narrow fix tests. Runtime acceptance: one truthful existing-session response or truthful blocking receipt; paid transport may be observed while the known grasp gate safely refuses a contract. Formal/nominal: R469 NOT_RUN, native UNKNOWN, formal NOT_ACCEPTED, physical/edge false, full-H unproved. No API raw response can substitute for full frozen request/response/cost/instance/render/process evidence or the R469 independent reader.

Self-review performed: all seven AGENTS evidence requirements covered; current API signatures and default values checked against pinned source; no fabricated runtime failure; original calibration issue included before execution; CPU and live generations separated; no additional delegation or confirmation gate; one-call ceiling and shared-lock uncertainty explicit; scope limited to one service function and one test file. Planning itself used static reads only and ran no test, render, API mutation or model call.
