# R495 Persisted Sol real RGB-D retest plan

**Planner:** actual gpt-6-astra. **Status:** planned, not executed. **Goal:** resume the authorized cloud testing after proving key persistence, using exactly one bounded production RGB-D dry-run. No new user confirmation or product change.

## Evidence and actual path

R486 was blocked by `BIGSMALL_VLM_ALLOW_PAID_CALL=false`. R488 fixed saved-profile calibration trust and normalized320×240 interpretation. R494 now proves active encrypted key recovery in freshbackend1506084/start9497458, configv2, unchangedthreeprofiles. The current launch gate is false. R469 frozen pins are stale; no R469 runner or formal qualification is authorized here.

Current service selects the active saved profile and calls `visual_planner(trusted_default_capture=True)` only for its internal default capture. It checks current-v2 sceneSHA `66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2` against repo-relative SimulatorConfig.model_path resolved under the same backendcwd. Capture is MuJoCo S01_NORMAL_STATIC seed0, camera rgbd,320×240, reset+forward and RGB/depthrender, no physicsstep. `sample_scene` is not forwarded in this RGBD branch; the defaults establish the actual scene. Preserve topview/visiblemarkers/controller choices and unconfigured rejection for arbitrary supplied frames.

The active official route must remain https://api.openai.com + /v1/chat/completions, gpt-6.1-sol, max_tokens4096, timeout30. The adapter sends one chat-completions request with reasoninglow/max_completion_tokens4096; no inference retry/fallback and no redirects for Sol. Saved metadata max_retries2 is unused by this adapter. Pipeline may perform at most2 **local deterministic** repairs, without another model request; the API hardcodes repair_attempts0, so that response field is not evidence of zero internal repairs.

Installed MuJoCo defaults to GLFW, while durable backendlaunch has no DISPLAY. Set MUJOCO_GL=egl as an explicit headlesscapture prerequisite before module import. Leave PYOPENGL_PLATFORM absent; installed EGL module sets it. Do not perform a previewcapture to probe renderer readiness; import/files/library metadata and resource admission only, with actual capture validated in the one request.

## Bounded steps

- [ ] **A. Static and resource admission before restart.** Verify source/input pins, same repo cwd and current-v2 scene SHA, installed MuJoCo/EGL modules and graphics libraries present using metadata only (no import/render probe); record HEAD and allow artifact-only progression with identical source pins. Acquire cache/research/.r468-r469-gpu.lock using exclusive nonblocking flock with a durable owner. Admit only GPU0 free>=2048MiB, no compute-app rows, qwen38-flash-strata.service loaded/inactive/dead MainPID=ControlPID=0, disk>=2GiB. Preserve R468/R469 mutual exclusion; no service stop or GPU eviction. Record WAITING_RESOURCE/BLOCKED with zero POST and leave existing service untouched if unavailable.

- [ ] **B. Freeze metadata and replace exact backend.** Bounded GET /health and model-control profiles/runtime/capabilities, filter through prior safe metadata allowlist. Require active4f24f5330ad644ad, modelgpt-6.1-sol officialhttps://api.openai.com /v1/chat/completions, max_tokens4096 timeout30 configv2, encrypted actualkeytrue, three profiles matching R494. Revalidate backend1506084/start9497458 uid1000 cwd/module/loopback8000, Vite159968/start8153269 unchanged. Reuse R494 exact DB/HOME/XDG/store launch contract with ONLY paid=true and MUJOCO_GL=egl additions/change; PYOPENGL_PLATFORM absent, MuJoCo EGL sets it internally. One pidfd SIGTERM to identified backend; observe<=90s in<=30s chunks, no repeat signal/KILL. Require exited and vacantport before exactly one detached launch. Never signal parent/group/Vite. If timeout or identity conflict, stop for new Astra with old/new state preserved.

- [ ] **C. New-generation readiness and one-shot reservation.** At most10 health probes timeout2s spacing<=1s overall30s, then one filtered metadata snapshot requiring same configuration/presence. Record newPID/starttime, source/asset/contract pins, explicit paid=true/EGL setting from launch manifest (do not read procenviron). Recheck resource admission and lock ownership. Exclusive attempted.json and execution-start.json must exist before one API POST; refuse duplicate run if either exists. Do not reactivate/edit profile or call provider test, capture endpoint, plans or any other planner. Keep other experiment/model requests quiescent; this one-shot bound is for agent-issued requests, not a claim of server-enforced global rate limit.

- [ ] **D. Exactly one RGBD dry-run.** POST /api/v1/model-control/planner/dry-run with request below once, no redirects/retries/fallback. Absolute client deadline90s, response cap4194304bytes; preserve complete response bytes HTTPstatus/timing/hash in private local cache and sanitized derived report in canonical artifacts. Underlying provider timeout30s, one HTTP inference max, max_completion_tokens4096 reasoninglow. Do not add text/vision probe. Full body timeout/partial response is UNKNOWN and consumes the attempt; never replay. If completion unclear, retain durable lock owner and do at mostone bounded read-only health/completion-status check<=30s; require same-PID health plus terminal request evidence before release, otherwise stop related work for next Astra with lock holder receipt rather than assuming cancellation.

- [ ] **E. Classify all response predicates and preserve outcome.** Evaluate the checks below, not the historical R486 success heuristic. PLANNED alone is insufficient. Record provider-return evidence, visual-schema/normalized coordinates, safe envelope, observation scene/time/calibration, final TaskContract/semantic identifiers/time separately. Failures can be useful diagnostics but are not success. API cannot expose full raw image/depth/instances/transport/cost ledger; record gaps/null actual tokens/cost/callcount where not observable. Keep exact local bounded response, sanitize excerpts; no credential headers/env/DB/vault data. No product repair or additional attempt; new unexpected failure gets next Astra plan.

- [ ] **F. Finish bounded integration and preserve configured service.** After a complete response and known finished request, release resource lock and take optionalone filtered metadata/health snapshot to prove config/presence intact. If successful, leave new normalUI backend paid-enabled and EGL-configured, Vite unchanged. If rejected/error, stop further model work and report gate state truthfully (still enabled unless separately planned transition); do not silently claim disabled or launch a rollback loop. Report exactlyone attempt, result stage and evidence limitations; nominalR469 NOT_RUN. Preserve rawbytes and scoped commit/push derived artifacts/pins without staging privatecache or dependencyfiles.

## One request and retained evidence

```json
{
  "user_instruction": "pick the red cube and place it in the green target region",
  "sample_scene": "S01_NORMAL_STATIC",
  "control_mode": "PCSC",
  "input_mode": "RGBD"
}
```

Use the exact prior R494 absolute Python/app/bind/cwd/DB/HOME/private XDGdefault/ENCRYPTED_FILE/LOCAL_ONLY/writesfalse contract. Only paidgate true and EGL selection change. Preserve Vite159968/start8153269. Restartstop90s is observed in <=30s chunks with updates, no repeat signal or kill/relaunch loop. Prepare launcher, detached logs, requestmarker and durable lockholder before sending any signal. Keep read-only metadata GETs distinct from the single model POST budget.

Write exact bounded API response bytes under a unique ownerprivate ignored `cache/research/r495-persisted-sol-real-rgbd-retest-20261108/` directory (umask077); save HTTPstatus/UTC+monotonic timing/length/SHA and sanitized derived JSON/report in canonical R495. No authorization headers, keys, vault content or full environment anywhere. Full API response is not full providertransport and not raw RGB/depth; do not claim otherwise. Do not overwrite historical raw or modify R486 classifier.

## Classification predicates

**envelope.**

- HTTP200 completeJSON object
- input_mode==RGBD; dispatch is False; hardware_execution is False
- evaluation_scope==RGBD_PLANNING_ONLY; provider_kind==OPENAI_COMPATIBLE; model_name==gpt-6.1-sol
- validation_errors is list; no unexpected shape treated as success

**observation.**

- source==mujoco_camera; scene_id==S01_NORMAL_STATIC; sim_time_s==0; width320 height240
- nonempty episode_id/frame_id/observation_id/calibration_version; observation_id==frame_id; checksum/rgb/depth hashes64hex
- captured_at within client sendUTC minus1s and responseUTC plus1s; record clockinterval; pipeline sourcechecks freshness<=5s before inference, do NOT demand age<=5s after30s provider
- depth_convention==optical_z_m; model_image_count==2; ground_truth_used_for_control is False
- intrinsics approximately[257.34083046114705,257.34083046114705,159.5,119.5] atol1e-6; camera_to_world approximately[1,0,0,0.35,0,-1,0,0,0,0,-1,1.4,0,0,0,1] atol1e-9; matches pinned topcamera; calibration_version expectedf33940579c533afe from unchanged camera metadata, discrepancy must be reviewed rather than silently accepted

**visual_schema.**

- Nonempty raw_planner_output parse via pinned VisualDecision.model_validate_json(strict=True) offline; both coordinate tuples have ints0..1000 for a positive plan
- reported_confidence>=0.5; complete ordered MOVE_ABOVE,APPROACH,GRASP,LIFT,MOVE_TO_REGION,PLACE,RELEASE,RETREAT allowing optional leading/trailingHOME
- target_label semantically redcube (record actual label; ambiguity is not automatic match). No extra provider request to judge label

**contract.**

- parse_result==PLANNED, validation_errors==[], final_contract nonnull valid pinned TaskContract offline
- control_mode==PERIODIC_CLOUD_SUPERVISION; user_instruction exact; task_target.object_id==visual_target and target_region_id==visual_destination; object_class==decision.target_label
- scene_version==expected_scene_version==1; plan_version==command_seq==1; task_id nonempty; contract step skills match accepted decision sequence
- issued_at within request/responseUTC interval ±1s; valid_until>issued_at; timestamp consistent with issued_at; do not require contract still unexpired when report is later read

**failure_classification.**

- BLOCKED_BY_ENV: prerequisite/exception only, no invented provider attempt evidence
- PLANNER_FAILED with exact paid-gate reason: gateblocked; HTTP/provider/auth/schema/contract reasons separately, no retry
- REQUEST_MORE_OBSERVATION: safe refusal/grounding not accepted; preserve reason/raw decision if available
- transport deadline/oversize/incompletebody: UNKNOWN or RESPONSE_LIMIT, never success/replay
- PLANNED plus any failedpredicate: INTEGRATION_EVIDENCE_MISMATCH, preserve result and next Astra before repairs

A positive result is **PLANNED_INTEGRATION** only after all positive predicates; otherwise record the exact failed stage. Treat incomplete/exceptionresponses honestly; fieldabsence is unknown, not success. The API does not return metricdepth pixels, instanceIDs, full grounding-evidence dict, providerusage or ledger. Do not fabricate cost/tokens/actualwirecount or independentlyverified physicalcorrectness. A valid modeldecision or safe groundingrefusal can establish partial integration evidence without a finalcontract.

## Acceptance and failure boundary

The one-shot budget is at most1 paid inference with4096 completiontokens total (including reasoning), timeout30; client absolute90s/4MiB. Source normal capture implies2 renderpasses, but exact measuredrendercount remains unknown. No modeltest endpoint, extra capture, fallback, repeated POST, hardware dispatch, physicssteps or controller execution. No source repair follows a newfailure without nextAstra. Keep resourceownership until known requestcompletion; client timeout is not cancellation.

Before stopping, admissionfailure leaves the old paidfalse service intact. After a newprocess startup failure, do not retry: preserve evidence, optionally clean up only that positivelyidentified newprocess with oneTERM and <=90s observation, and return to Astra. After a completed unsuccessful modelresult, no automatic gate-toggle restart; record paidgate remains true and stop further calls pending nextplan. On success leave the normal UI backend configured paidtrue as authorized, with persistedkey intact. The single-call cap covers this task's requests; do not claim global server rate enforcement.

Report R495 realintegration outcome separately from softwareverification and keypersistence. NominalR469 remains **NOT_RUN**. Root may commit/push only named derivedreports/pins/scripts, preserving local rawcache exclusion and unrelated worktrees; HEAD may progress by artifact-only commits with unchanged sourcepins. Input SHA256 pins and exact machine-readable bounds are in plan.json. Self-review covers calibration asset/cwd, paidgeneration, EGL readiness, source no-retrybound, timestamp/scenepredicates missing in historicalclassifier, and evidence limits. Planner did not call APIs, render, signal, launch, test or modify product.
