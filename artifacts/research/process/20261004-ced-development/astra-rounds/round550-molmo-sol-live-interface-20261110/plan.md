# R550 Real Sol Planning and Interface Verification Execution Plan

> **For agentic workers:** Use superpowers:executing-plans for this bounded execution. Existing explicit user instruction “开展真实云端规划与接口校验” authorizes the paid attempt below. No new approval, feature development, independent review or sub-agents are required.

**Goal:** Obtain and inspect one real selected-Sol skill-planning exchange from a fresh Molmo/OpenCV observation, retaining the actual existing pipeline outcome.

**Architecture:** Unmodified R545 runtime overlay and existing diagnostic CLI, one post-load S01 capture and task pair, existing encrypted profile service/transport. Round-local observation/classification may persist missing result/timing evidence without changing business logic.

**Tech Stack:** Existing Molmo BF16 runtime, OpenCV, official Sol Chat Completions transport, current JSON mode and application validation.

**Spec:** R550 request.json. Actual planner_model `gpt-6-astra`; baseline HEAD `4c21a91746b412ddc01dc56f60c8c71b086f46e9`.

## Global Constraints

- All20 request input bytes/SHA256 matched during actual Astra planning; recheck before execution. Preserve native-01 failure, native-02 evidence and historical bytes.
- Current profile `profile-4f24f5330ad644ad`, config_version2, existing store `/home/ningyd/文档/ChatGPT/BIGsmall/data/model_control.db`, ENCRYPTED_FILE secret present. Do not print/copy key, headers, database or encrypted secret files; do not activate or change profile.
- Preserve `gpt-6.1-sol`, official route `https://api.openai.com/v1/chat/completions`, reasoning_effort=`low`, max_completion_tokens=4096, timeout30s, response_format=json_object. Effective settings hash `eb31dd5eb394646e1a09a0116c7d8d58c954a8c200f2443d12b5ce3ef972362d`. No model substitution, prompt/JSON-mode edits, downgrade, new endpoint or retries.
- R550 allocation: at most1 additional native load start,2 generation starts and1 paid HTTP attempt. Prior native starts2/4; combined native caps3loads/6generations. Failed/timeout starts consume allowance. No automatic or manual rerun under this round. Zero hardware dispatch and formal experiment calls.
- No production/test/runtime/SDK/asset changes. Only round-local execution/classification source, nonsecret metadata/derived reports and new ignored raw output. No raw/secret/DB/weights/SDK upload.

## Review Focus

- A real response can arrive after the immutable5s observation TTL; preserve refusal rather than recapture/retime or relax gates.
- A prepared request or timeout does not prove provider acceptance or billing; report evidence granularity honestly.
- JSON object mode does not establish strict skills/schema/order validity; use existing duplicate-rejecting application parser and pipeline semantics.
- Actual returned model, usage and finish_reason may be absent/unexpected; retain originals and mark unknown/mismatch, never invent successful identity.
- PLANNED is validated software-contract evidence only, not hardware task success or complete physical geometry certification.

---

## Evidence gap and hypotheses

Prior real native work established local geometry readiness, but real cloud was deliberately not invoked. There is no observed live-cloud failure to repair yet. The selected-profile preflight resolved the existing factory/secret store with zero paid requests and current role source hashes. It proves configuration availability, not endpoint success.

Known hypothesis: roughly2s native queries plus real cloud roundtrip may exceed the existing max5s/future50ms gate. Expected expiry is a legitimate measured outcome. Current transport has no retry and rejects Sol redirects; pipeline invokes the planner once and any existing contract repair is local. One input pair therefore bounds real inference to one outbound model attempt, absent a new defect. Source inspection also finds that CLI report saves outcome/draft evidence/raw bodies, but not the full returned InitialPlanningResponse/contract or precise call timing; avoid reconstructing a contract and calling it the actual returned result.

Official model/JSON-mode pages were already checked in the parent session and listed in request.json; this execution retains those choices unchanged. This planner verified local implementation/configuration and did not make a network, model or cloud call.

## Task 1 — Freeze one execution and preflight without spending budget

- [ ] Recheck20 inputs, HEAD, selected profile/config hash/current active identity/secret presence through existing factory only. Inspect no secret values. Confirm prior cumulative2loads/4generations and no intervening starts. Create a durable R550 allocation/start ledger before launching, exclusive per-run directory, no resumable retry loop.
- [ ] Use the already prepared exact templates in `datasets/model-cache/molmo-sol-r550-20261110/inputs/request.json` and `inputs/task.json`, verified in input-template-manifest.json; do not create another request. Request is941 bytes/SHA256 `20f75dac7cabd3d2ba8b459272be8afbb23519663ee04cbbed02c19b7f54eed4`, observation=None, request_id r550-live-s01-01; task is166 bytes/SHA256 `e7b77613fc8942bc626ba6869c847458203c9f8122d48cbe7ee1d52d33d4be1e`, explicit red block to green region. Both hashes additionally matched during plan finalization. Bind instruction exactly and use --capture-fresh; no scene oracle. Use the existing model directory/asset manifest and original runtime paths, no asset copying or download. A new capture must happen only once after load through existing capture code.
- [ ] Run R545 launcher `--preflight` using validated r505 Python: exact Torch2.6.0+cu124/Transformers4.57.1 paths and CPU ABI PASS, no CUDA model initialized. Reverify all model asset hashes. Existing admission must hold shared GPU lock, find no foreign compute process, >=12000MiB free GPU, >=8GiB RAM, >=60GiB disk, and host GPU/direct HTTPS permissions. Do not send an extra model ping, chat probe or preliminary paid request; prior preflight is configuration-only.
- [ ] **Approved observation-only runner to complete evidence:** create a small round-local script that imports unchanged R545 launcher by file and calls configure_overlay once, then invokes the existing CLI main with the exact argument vector below. Wrap only `PlanningPipeline.process` and selected RGBDPlannerAdapter `_post` in memory, each calling its original exactly once and returning its exact original result/exception. Persist original pipeline return `model_dump(mode="json")` locally, plus UTC/monotonic start/end times and input observation captured_at/checksum. For `_post`, capture timing/status only, never headers/key; existing CLI observer already saves exact request/response bodies. Run in the main thread. Enforce the model-endpoint paid-start counter cap1 before delegating `_post`, increment and durably record the first start before the original call; any failure still consumes that slot. A second invocation is blocked before delegation and reported, never retried. Keep original strict route/no-redirect/no-retry transport intact. Save probe evidence in separate exclusive files and its own manifest; never rewrite CLI raw files/report/manifest. Do not alter request/body/timeout/prompt/result, parse/repair logic, TTL, success calculation or source files. Observation file writes must not overwrite existing evidence or mask an original exception. Label wrapper timing as inclusive call duration, not exact provider compute time.

  Verify runner delegation/count/return/exception preservation on CPU stubs and Ruff before the live command. No new model/profile/task configuration schema or service client. The parent approved this observation-only wrapper. Capture the complete actual original pipeline response/contract, return the very same object without changing any field, and never synthesize/rebuild PLANNED. Wrapper evidence supplements the CLI files; if evidence capture fails, disclose the gap and do not issue another paid call.

## Task 2 — One existing-entry real run, no retry

- [ ] Start one process under validated r505 interpreter with `-B`, using R545 overlay (direct launcher or the observation-only wrapper above). Pass existing CLI arguments: `--request <frozen-template> --task-descriptor <frozen-task> --output <new-ignored-r550-live-01> --mode native --capture-fresh --generation-limit 2 --model-directory <existing-Molmo2-ER> --asset-manifest <verified-existing-manifest> --profile-id profile-4f24f5330ad644ad --model-store /home/ningyd/文档/ChatGPT/BIGsmall/data/model_control.db --allow-paid`. Exactly one pair; no replay flags or synthetic cloud content. Preserve existing shared GPU lock and load/native request timeouts; Sol timeout remains30s.
- [ ] Keep raw stdout/stderr, exit, load/generation start/completion counts and durable call-start ledger. If geometry/freshness fails before cloud, cloud is NOT_PERFORMED and no second pair is permitted. If paid invocation starts and times out/fails, retain consumed attempt with unknown provider completion/charge as appropriate. If stale after response, preserve actual cloud body/content and original observation timestamp, return the existing REQUEST_MORE_OBSERVATION outcome. Never patch clock/TTL or recapture to upgrade the result.
- [ ] Do not treat CLI exit0 alone as complete interface acceptance. Review its report and captured original pipeline result after process exits. Any new fault requiring source/runtime/profile changes requires the next actual Astra plan; this plan only classifies observed results.

## Task 3 — Layered evidence and acceptance

Record each layer independently in R550 summary:

1. **Admission/native/geometry:** asset/runtime/source identity, actual1-or-fewer load and2-or-fewer generations, exact fresh capture checksum/time, native raw normalized points, original pixels, any associated pixel/mask provenance, unchanged top-grasp/tracker outcomes. Geometry remains a development estimate with its existing unknown extent/depth bounds.
2. **Outbound request:** count and exact body SHA256, selected model/profile/settings/role hashes, official route, low/4096/json_object, text-only grounded geometry and task; no coordinates/trusted fields delegated to model. Existing REQUEST observer is called before transmission; its record proves a prepared/invoked attempt, not alone successful socket delivery or billing. Count it conservatively against the one-attempt budget.
3. **Transport/provider envelope:** exact returned bytes and SHA256 (including HTTP error bodies when captured), provider response id/model, finish_reason, usage input/output/total and details when present; record absent fields as NOT_EXPOSED/unknown. Do not infer cost=0 from missing usage. A non-error returned model string different from requested must be flagged for identity assessment, not silently rewritten; no alias substitution. Preserve timeout/error cause type and available timing, without logging credential headers. Existing client may not retain numeric HTTP status: report NOT_CAPTURED rather than invent200 from body shape.
4. **Content/skills:** preserve actual message.content, strict JSON/duplicate/nonfinite/schema result, whitelist/sequence/empty-skills behavior and parse reason. If live TTL rejected before parser, optionally apply the same strict parser offline to the saved content, labelled OFFLINE_CONTENT_CHECK only; it does not change original pipeline refusal or prove an accepted live draft.
5. **Pipeline/contract:** original outcome/attempt validation/repair flags and errors, actual returned contract or null, task/scene binding, step sequence, trusted ids/sequence/issued_at/valid_until supplied by existing pipeline, safety/failure fields and unchanged measured target/destination. Report PLANNED only if the real returned pipeline outcome is PLANNED and original contract exists with validations passed. If result was not captured, mark detailed contract audit NOT_CAPTURED; do not rebuild a hypothetical contract and call it live.
6. **Freshness:** unchanged capture timestamp, measured call durations and capture age at available local boundaries; mark observed gate result and reason. `_post` wrapper boundaries bracket but are not the exact private `_fresh` check timestamp; state that precision. A valid cloud answer plus stale sentinel means REAL_CLOUD_RESPONSE_RECEIVED / LIVE_PLAN_REJECTED_STALE, not end-to-end success.
7. **Scope:** hardware_dispatch=false, PHYSICAL=NOT_PERFORMED, FORMAL_RESEARCH=NOT_PERFORMED. Validation of one cloud exchange is no throughput/reliability benchmark or full remote reproduction claim.

- [ ] Finalize a local manifest over all raw inputs/capture/token outputs/cloud wire bodies/content, wrapper result/timing evidence and failure logs: relative path, bytes, SHA256, creation/attempt associations. Verify every row. Record actual cumulative native totals against3/6, R550 paid starts<=1, all failures retained. Preserve native01/02 originals.
- [ ] Write concise execution report/phase summary with PASS/REJECTED/BLOCKED/NOT_PERFORMED/NOT_CAPTURED per layer, exact command/exit and unresolved next step. Any observer gaps remain disclosed; do not rerun to hide failure. Locally commit only explicit round-local source and derived nonsecret reports on the existing research branch; raw/DB/secrets remain ignored/local. Prior publication authorization is not permission to upload new private cloud raw. Follow established derived-report delivery boundary, performing all reviewable work before any genuinely necessary publication question.

## Preconditions, stop rule and plan acceptance

Parent independently reports runtime/resource preflight PASS with14841MiB GPU free, no foreign compute, about49GB RAM and358GB disk, with zero new actual calls. Recheck volatile resource admission at execution. Host GPU/direct official HTTPS access, existing encrypted-store readability and current frozen inputs are required; no extra credential entry or new runtime is planned. Plan completion is a bounded truthful experiment and report, not a guarantee of PLANNED. Preflight mismatch, unexpected repair need or any exhausted cap stops affected execution for another actual Astra plan. TTL/JSON/empty-skills/HTTP failures are reportable outcomes here; none authorizes retries or threshold changes. All planning-stage actual calls=0; execution budget is the explicit new allocation above.

## Exact verified inputs

- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/AGENTS.md` — 1774 bytes — SHA256 `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/grounded_planner.py` — 16214 bytes — SHA256 `91ac346517b0fc037148b5d585896cbf8609382dd747b889614b3e5f9ebd3ec0`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/molmo_pointing.py` — 15828 bytes — SHA256 `ee03fa55259b44e6cdb697baa557464db5ed086cc342a7cb3e4f11c0c439056e`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/point_association.py` — 7450 bytes — SHA256 `72c19fe7202c55451e5ee39f1c8e980cf3621d6fbbc257f9162ef8a3ff81692b`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/planner.py` — 31544 bytes — SHA256 `45d4fa9a194db46e098550625b6b48a871c2aa0a200302c809c6b5e8522399f9`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/observations.py` — 11603 bytes — SHA256 `1114e6b2de4107ae516f12f8972fcb3b6f71eae7ae5a45bf93adfeb4aa673bb8`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/tracking.py` — 35038 bytes — SHA256 `1a34ac6aa012cd58ab9016387310ebea044169b05b59286f4c5a8c540d3c6afc`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/role_models.py` — 10182 bytes — SHA256 `cfc28c29856be9cedcb0b8ca626d6e51e83cec8eaf2c0f637a03b71f757b81bf`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/model_resolver.py` — 8205 bytes — SHA256 `e75a94929529a4537a980e33fa4645285baee85aaec0b5597b426c347cd41e04`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/model_control/service.py` — 26725 bytes — SHA256 `4dfcc62648f5ed3c4096907621429dcd1f7879662d9ad0fa14060d05c1f5550e`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/model_control/secret_store.py` — 3214 bytes — SHA256 `db0acaf78236766cfd091bf20f3df0a5dd348909071b74c1360b468414a172e3`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/model_control/sqlite_repository.py` — 10664 bytes — SHA256 `a29da1813f1c20905377f0d4b21ab2bd68ac129de676bd525665579ac00c8f6f`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/cloud/planning/pipeline.py` — 27701 bytes — SHA256 `425337b65e8b4493027a55ccb7d7b746f83c75952025458d9da4f7ffee12dba1`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/scripts/probe_molmo_grounded_planner.py` — 20965 bytes — SHA256 `3ed2056152940ede47b6e8970c7c0c1e13b397ae9bae761f43e96f4b794d51d7`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/tests/test_molmo_grounded_planner.py` — 23461 bytes — SHA256 `7b1f530b2d07c086b781bcdea1930155fcd3c9181315ca6019c061c30246af63`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/tests/test_molmo_grounded_cli.py` — 17145 bytes — SHA256 `dbe9600264d5213b93a424abbfbc9112695a51ce5b276b6c0a3d3fb76b62f3ce`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round545-molmo-opencv-runtime-overlay-20261110/implementation/launch_molmo_grounded.py` — 4816 bytes — SHA256 `7e9918bea93a641182e47c69a5741a7895a323064ad6276e252bfa7499995b59`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round545-molmo-opencv-runtime-overlay-20261110/planner-r545-import-preflight.stdout` — 4426 bytes — SHA256 `654de3974d33c6519bf7c211c6a76d1c0f1ec943d7435f595f6ee7dbb9d9bedc`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round547-molmo-point-component-association-20261110/native-cumulative-summary.json` — 7643 bytes — SHA256 `3a7a10bab8cfb7eb1d6d556c7590926fc1c14d837910365efbc62e265fc870cc`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round550-molmo-sol-live-interface-20261110/selected-profile-preflight.json` — 2654 bytes — SHA256 `70205b36140e56dae0ee823dc1a0ee9985ab0ec1991ac08ce0f0326a010939d8`

Self-review: current selected profile preserved, fresh one-pair command bounded, observer limitations disclosed, contract/TTL/content layers separated, no production edits or additional review required.
