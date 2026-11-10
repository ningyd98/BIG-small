# Molmo2-ER + OpenCV Grounded Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user has already authorized the selected architecture and continued development; no new architecture or execution-method approval is required. A fresh independent reviewer checks the complete change after implementation.

**Goal:** Add an opt-in native Molmo2-ER pointing provider and calibrated OpenCV/RGB-D grounding feeding the existing selected cloud planner's skill intent into the existing planning pipeline.

**Architecture:** Two bounded queries use exactly one immutable RGBDObservation. Reuse the deterministic geometry and contract-building portions of `RGBDPlannerAdapter._ground_response`, then use `OpenCVTargetTracker` for conservative initial acquisition checks. The selected cloud adapter receives grounded scene facts and returns only skill intent; existing validation, trusted-field completion, SafetyShield and execution boundaries remain in force.

**Tech Stack:** Python >=3.12, Pydantic, existing Pillow/NumPy/OpenCV research dependencies, existing PyTorch 2.6.0+cu124 / Transformers 4.57.1 Molmo BF16 runtime; pytest.

**Spec:** `docs/superpowers/specs/2026-11-10-molmo-opencv-grounded-planner-design.md`.

## Global Constraints

- Actual planner model: `gpt-6-astra`; round `round542-molmo-opencv-grounded-planner-20261110`; baseline commit `025c538935199ea7d3aa8cf15b6e93ac9826cf3a`.
- “User decision (2026-11-10): use Molmo2-ER for identification and localization, OpenCV with aligned raw depth for geometry, and retain existing cloud planning and program validation.”
- “Accept one unambiguous point per query or explicit ABSENT; reject malformed, contradictory, multiple or out-of-range output.”
- “Raw optical-z float32 metres, calibration, source and timestamps remain bound to the observation.”
- “The configured cloud model remains unchanged (current selected Sol profile stays Sol).”
- “Preserve visible pose markers, top camera and controller.” No edge-model selection, UI, new controller, training, hardware dispatch or default-planner switch.
- No fabricated confidence, probability, raw model response or task phrases from evaluation labels. No automatic download, dependency mutation, paid cloud call or hardware use. Legacy frozen data, weights and SDK bytes remain unchanged.
- This round permits at most **1 model-load start and 8 native generation starts**, including failed attempts. No retries that silently reset counters. Real cloud is a separate explicitly admitted run, not part of this round's default smoke.
- Files in the input inventory must be rechecked immediately before implementation. Subsequent changes explicitly prescribed here become tracked outputs, not grounds to silently rewrite the original inventory. A new root cause, scope increase or unexpected failure pauses affected repair and requires a new actual Astra plan.

## Review Focus

1. A prompt containing two point tags, duplicate attributes, an absent claim plus a point, nonfinite/overflow coordinates or another image ID must fail closed (Task 1 parser matrix).
2. A delayed provider/cloud reply or a replayed point from a different observation must never produce an actionable draft (Task 3 binding and elapsed-time tests).
3. A legitimate single point can still hit background, invalid depth or an unsupported camera/object family; preserve calibrated geometry and OpenCV rejection (Tasks 2–3 geometry tests).
4. A cloud reply can attempt to override coordinates, targets, confidence, safety or trusted timestamps; strict skill-only output must reject it (Task 3 malicious reply tests).
5. An opt-in runner can appear real while using replay replies, unchanged archived timestamps or wrong model identity; its evidence and counters must keep these modes distinct (Task 4 CLI/accounting tests).

---

## Problem, evidence and hypotheses

The existing full visual interface supplies a system role and paired RGB/depth display images, asks one model for coordinates plus skill sequence, and requires `reported_confidence`. Frozen R507 records both JSON_RGB and JSON_DUAL as `UNSUPPORTED_SYSTEM_ROLE` with **zero generations in those modes**. R505's final summary records Molmo native DEV16 joint target/destination 12/12 and absent 4/4, while full VisualDecision acceptance remains NONE. These are prior component-development signals, not heldout or integration evidence.

The inspected original raw native sample is `<points coords="1 1 458 557">yellow block.</points><|im_end|>`; its exact local path/hash is recorded below and in plan.json. R507's parser selected the first point from a possibly plural list. Do not reuse that permissiveness in production. The incompatibility is at the interface boundary, not proof that Molmo cannot point or that it performs calibrated depth reasoning.

`planner.py` already supplies optical-z deprojection, support relief, calibrated top grasp, fixed contract templates and a strict skill order. Its parse/confidence gate is currently coupled to those operations. Extract the reusable deterministic portions; do not construct a fake `VisualDecision` with confidence 1 or synthesize a fake HTTP response. `observations.evidence()` currently reports model_image_count=2 for the legacy visual path; override that explicitly for this new path (Molmo=1 RGB, cloud=0 image inputs), without changing legacy evidence semantics.

`OpenCVTargetTracker` supports unique colored supports in the existing registered top-camera upright-box research family, rejects changed calibration/frame binding and stale acquisitions, and cannot certify continuous-motion or final placement success. Use its initial geometry conservatively; do not claim generic arbitrary-object segmentation, orientation certification or physical acceptance.

**Hypotheses to verify:** (H1) exact native output can be strictly parsed and bound without a confidence surrogate; (H2) shared geometry and existing OpenCV checks admit valid calibrated fixtures and reject unsupported cases; (H3) selected-cloud skill intent can drive the existing contract schema without gaining authority over geometry or safety; (H4) a bounded native smoke can run in the already validated runtime without changing assets. H4 being unavailable does not invalidate software tests, but cannot be marked real-runtime PASS.

**Infrastructure evidence:** parent reports host-authorized targeted baseline `119 passed, 1 existing anyio DeprecationWarning in 3.76s`; exact log hashes are in plan.json. Restricted sandbox loopback produces socket PermissionError and pytest cache is read-only in the worktree. GPU/NVML is also sandbox-restricted; host check reported RTX4070Ti SUPER, 14839 MiB free, no compute apps. These are environment admission facts, not requests to change source or permissions globally. Parent also reports preexisting full-suite failures during the baseline run (still in progress at plan completion); preserve its final log/classification and do not repair unrelated failures in this round. Planner discovery also found no `python` alias and no worktree-local `.venv`; use explicit existing Python paths. No tests or GPU loads were run by this planner. The managed worktree does not contain ignored runtimes, cache or service databases; reference their existing original-root absolute paths without copying model/SDK bytes. Native runtime: `/home/ningyd/文档/ChatGPT/BIGsmall/datasets/model-cache/ordered-small-vlm-20261109/runtimes/molmoer-r505/bin/python`; model: `/home/ningyd/文档/ChatGPT/BIGsmall/datasets/model-cache/ordered-small-vlm-20261109/models/Molmo2-ER`. Use the actual existing original-root service store supplied by the user/environment; do not invent a new profile.

## Bounded files and interfaces

Modify only:
- `src/cloud_edge_robot_arm/vision/planner.py`: extract shared deterministic grounding/contract helpers; retain existing `_ground_response` interface and legacy behavior.
- `tests/test_rgbd_planning.py`: helper/legacy regression tests only.

Create only:
- `src/cloud_edge_robot_arm/vision/molmo_pointing.py`: typed strict native parser, observation-bound point result/protocol, lazy imports and explicit local model lifecycle.
- `src/cloud_edge_robot_arm/vision/grounded_planner.py`: explicit task descriptor, conservative grounded adapter, strict cloud skill decision, selected-role factory.
- `scripts/probe_molmo_grounded_planner.py`: opt-in diagnostic runner; dry-run, replay and native modes; no dispatch.
- `tests/test_molmo_pointing.py`, `tests/test_molmo_grounded_planner.py`, `tests/test_molmo_grounded_cli.py`.
- `docs/research/molmo-opencv-grounded-planner.md`: operation/configuration guide and limits.
- This round's `implementation-report.md`, `phase-summary.md`, verification logs/manifests and nonsecret example config/derived smoke summaries. Complete raw sensor/model/token output stays in a new local-only raw directory under the established data boundary.

No changes to observations, top_grasp, tracking, model_resolver, role_models, runtime_binding, pipeline, contracts, model-control service, dependency specifications or existing frozen research bundles are planned. If one becomes necessary beyond the small shared-helper extraction, seek a new Astra round rather than expanding silently.

Interfaces to implement:

```python
# molmo_pointing.py: immutable results; no confidence member.
@dataclass(frozen=True)
class NativePointResult:
    status: Literal["POINT", "ABSENT", "INVALID"]
    normalized_1000: tuple[int, int] | None
    object_index: int | None
    raw_text: str
    error: str | None

@dataclass(frozen=True)
class BoundPointResult:
    result: NativePointResult
    observation_checksum: str
    rgb_sha256: str
    query_sha256: str
    evidence: Mapping[str, object]

class PointProvider(Protocol):
    def point(self, observation: RGBDObservation, phrase: str) -> BoundPointResult: ...

def parse_native_point(raw: str) -> NativePointResult: ...
class MolmoPointProvider:
    # Explicit construction loads once after admission; point() never reloads.
    def __init__(self, *, model_directory: Path, asset_manifest: Path,
                 raw_directory: Path, generation_limit: int = 8) -> None: ...
    def point(self, observation: RGBDObservation, phrase: str) -> BoundPointResult: ...

# planner.py: GroundedScene dataclass owns scene and evidence copied per request.
@dataclass(frozen=True)
class GroundedScene:
    scene: SceneSummary
    evidence: dict[str, Any]

def ground_observation(request: InitialPlanningRequest, observation: RGBDObservation,
                       *, target_pixel: tuple[int, int], destination_pixel: tuple[int, int],
                       target_label: str, grasp_profile: str,
                       evidence: dict[str, Any]) -> GroundedScene: ...
# Pixels here are ALWAYS original observation pixels. Raises ValueError on unsafe geometry.
def build_grounded_contract(request: InitialPlanningRequest, grounded: GroundedScene,
                            skills: list[SkillIntent], *, raw_text: str) -> PlannerDraft: ...
# Raises ValueError on invalid skill order; never fills trusted pipeline fields.

# grounded_planner.py
class GroundingTaskDescriptor(BaseModel):
    # extra='forbid', frozen=True; nonblank strings; instruction <=2000 chars,
    # phrases <=160 chars, target_label <=100 chars; no control chars or markup.
    instruction: str
    target_phrase: str
    destination_phrase: str
    target_label: str

class SkillDecision(BaseModel):
    # extra='forbid'; only skills (0..20 SkillIntent) and reason (<=500 chars).
    skills: list[SkillIntent]
    reason: str = ""

class MolmoGroundedPlannerAdapter:
    requires_rgbd = True
    planner_name = "molmo_opencv_grounded"
    def __init__(self, *, point_provider: PointProvider, cloud: RGBDPlannerAdapter,
                 task: GroundingTaskDescriptor) -> None: ...
    def plan(self, request: InitialPlanningRequest) -> PlannerDraft: ...

def build_molmo_grounded_planner(*, service: ModelControlService, profile_id: str,
                                point_provider: PointProvider,
                                task: GroundingTaskDescriptor,
                                grasp_profile: str,
                                allow_paid: bool = False) -> MolmoGroundedPlannerAdapter: ...
```

The wrapper's `model_name` is the underlying cloud model; separate evidence names `allenai/Molmo2-ER` as the local perception provider. The factory uses `resolve_cloud_role` and the supplied existing service/secret store; it does not activate/select another profile, read credentials from a new config field, or downgrade an unavailable provider. Attach current source hashes covering the wrapper, native provider and reused geometry/transport modules to the new role snapshot. Keep that cloud snapshot distinct from local perception provenance; do not copy old whole-system runtime bindings or claim an accepted new role bundle. Existing execution paths require their usual fresh role/binding gates.

## Task 1: Strict native pointing and bounded local provider

**Files:** create `molmo_pointing.py` and `tests/test_molmo_pointing.py`.
**Consumes:** immutable RGBDObservation and explicitly configured task phrase.
**Produces:** NativePointResult / BoundPointResult / PointProvider / MolmoPointProvider above.

- [ ] **Step 1 — Write parser and provider-contract RED tests.** `test_native_point_exact_grammar` checks the observed tag returns `(458,557)`, object index 1; bare exact ABSENT yields ABSENT and no point. Parametrize `test_native_point_rejects_ambiguity`: two tags, duplicate coords, two triples/groups, extra attributes, nested tags, image ID 0/2, signed/decimal/exponent/NaN/Inf/overflow and out-of-range values, malformed closing tag, unbounded digits, free prose outside the tag, ABSENT/not visible/no points contradiction inside or outside. Allow only whitespace outside the one tag and one optional terminal `<|im_end|>` or `<|endoftext|>`; reject repeated/mixed terminals. Inner label is bounded plain text retained only as raw evidence, never used as task semantics. Coordinates are ASCII integers in [0,1000]; object ID is a bounded positive integer. `test_native_single_rgb_binding` uses injected fake processor/model objects and verifies user-only conversation, one RGB PIL image, no depth/system/oracle metadata, exact checksum/query bindings, special-token-preserving decode. `test_native_budget_counts_failed_starts` verifies generation attempts are incremented before generate, never exceed 8, and no automatic reload occurs.
- [ ] **Step 2 — Run RED.** Explicit existing test interpreter, `-m pytest tests/test_molmo_pointing.py -q -p no:cacheprovider`; expected missing new module/functions only. Preserve output. Any unrelated failure is not this expected RED.
- [ ] **Step 3 — Implement minimal parser/provider.** Bound raw parser input (16 KiB), use full grammar matching rather than searching for first point. Provider prompt: `Point to the {phrase}. If the requested item is not visible, return exactly ABSENT and no points.` Resolve only original RGB bytes. Use existing R507 `apply_chat_template` sequence, BF16 full model, SDPA, CUDA:0, local_files_only, verified trust_remote_code, no changed model/SDK source; seed 0, max_new_tokens=512, do_sample=False, num_beams=1, use_cache=True. Validate exact local asset-manifest hashes before loading, validate runtime versions/devices/dtypes, import torch/transformers only inside native lifecycle. A missing local file or wrong runtime fails before load. Preserve requested/rendered prompt, processor tensor hashes, token IDs, start/result/failure records, native raw response, output cap flag and counters locally with exclusive-create files. Reached output cap is INVALID, not a trusted truncated point. No broad try/fallback to fabricated output.
- [ ] **Step 4 — Run GREEN.** Same command passes with no torch/GPU requirement for CPU tests; assert imports alone load no model and call no network. Test runtime lifecycle using mocks, labelled `CPU_CONTRACT_FIXTURE`.
- [ ] **Step 5 — Commit verified explicit files** with `feat: add strict native Molmo point provider`; record commit and tests in step report. Do not stage local raw/assets.

## Task 2: Reuse deterministic geometry without fake model confidence

**Files:** modify `planner.py`, `tests/test_rgbd_planning.py`; create geometry tests in `tests/test_molmo_grounded_planner.py`.
**Consumes:** original pixel coordinates and existing geometry functions.
**Produces:** GroundedScene, ground_observation, build_grounded_contract.

- [ ] **Step 1 — Write RED tests.** `test_grounding_helper_has_no_model_confidence` passes calibrated visible pixels and verifies original pixels, optical-z poses, support/top-grasp evidence and no inserted confidence field; compare legacy draft contract/evidence on existing fixtures. `test_grounding_rejects_invalid_depth_and_profile` covers zeros at both endpoints, wrong source, unregistered grasp profile, support under 0.01 m, unsupported top patch/height. `test_contract_builder_preserves_whitelist_and_trusted_fields` checks exact required core `[MOVE_ABOVE,APPROACH,GRASP,LIFT,MOVE_TO_REGION,PLACE,RELEASE,RETREAT]` with optional leading/trailing HOME; all other orders fail; trusted IDs/times retain old placeholders for the pipeline. Preserve existing small-frame legacy fixture behavior only in the helper; Task 3 forbids this bypass for the new adapter.
- [ ] **Step 2 — Run RED.** `-m pytest tests/test_rgbd_planning.py tests/test_molmo_grounded_planner.py -q -p no:cacheprovider`; expected absent shared helpers only.
- [ ] **Step 3 — Extract shared helpers.** Move only geometry, scene and contract construction portions out of `_ground_response`; keep its parsing, confidence gate, evidence creation and coordinate conversion. Legacy wrapper converts once then invokes the helpers and maps ValueError back to its prior sentinel/parse behavior. Do not change calibrated thresholds, source restrictions, physical semantics or existing error behavior. Shared scene `pose_confidence=0.0`, `scene_confidence=0.5` remain compatibility placeholders, explicitly documented as uncalibrated schema bookkeeping rather than model confidence. New evidence must never say MODEL_SELF_REPORT when none exists.
- [ ] **Step 4 — Run GREEN/regression.** Run `tests/test_rgbd_planning.py tests/test_rgbd_top_grasp.py tests/test_rgbd_role_models.py tests/test_molmo_grounded_planner.py`; all pass with legacy assertions unchanged.
- [ ] **Step 5 — Commit verified explicit files** with `refactor: share deterministic RGBD grounding and contract construction` and record evidence.

## Task 3: Grounded scene to selected-cloud skill intent

**Files:** create `grounded_planner.py`; extend `tests/test_molmo_grounded_planner.py`.
**Consumes:** Task 1 provider; Task 2 geometry/contract helpers; resolve_cloud_role, OpenCVTargetTracker, existing cloud transport and PlanningPipeline.
**Produces:** task descriptor, SkillDecision, grounded adapter and selected-profile factory.

- [ ] **Step 1 — Write RED tests.** `test_grounded_adapter_pipeline_success` runs a >=64x64 calibrated top-camera upright-box fixture with two fixture native point results and fixture cloud intent through PlanningPipeline; verify validated contract and exact geometry provenance. `test_query_descriptor_is_bound_to_instruction` rejects mismatched request instruction and whitespace-only/oversized/markup phrases before provider/cloud calls; prove metadata/oracle scene labels cannot affect prompt. `test_pixel_mapping_once` checks normalized 0,500,1000 on non-square frames using `model_to_observation_pixel(...coordinate_system='normalized_1000')`; 1000 maps to last pixel, not width. No clamp for values outside [0,1000]. `test_absent_invalid_or_mismatched_point_skips_cloud` checks both endpoints and mixed observations/query hashes. `test_native_grounding_opencv_fail_closed` covers wrong source/profile, <64 dimensions, invalid depth, missing calibration/episode, unsupported orientation, fragmented/multiple colored supports and point outside selected support. `test_expiry_during_local_or_cloud_call` advances patched clock beyond 5 s and more than 50 ms into future, expects no actionable draft. `test_cloud_skill_only_rejects_override` supplies extra pixel/geometry/target/safety/timestamp/confidence fields, null/wrong types/unknown/reordered skills. `test_selected_sol_transport_preserved` asserts exact selected Sol model, official endpoint/path, reasoning_effort/max_completion_tokens, no added temperature/max_tokens, credential policy, allow_paid=false refusal and no profile activation. `test_cloud_failure_has_no_fixture_fallback` checks error and raw accounting.
- [ ] **Step 2 — Run RED.** `-m pytest tests/test_molmo_grounded_planner.py -q -p no:cacheprovider`; absent wrapper/factory is expected.
- [ ] **Step 3 — Implement the wrapper and factory.** Require descriptor.instruction exact equality to request.user_instruction. Form target query `visible top center of {target_phrase}` and destination query `interior of {destination_phrase}`. Phrases are explicit caller-provided task semantics, not derived from SceneSummary objects, dataset phrase sidecars, success labels or raw evaluation cases. Record descriptor hash locally; provider sees only resulting phrase and RGB.

  Before local queries, after both replies, before cloud and after cloud, check immutable checksum/bindings and age using current UTC (max 5 s, future tolerance 50 ms); fail with REQUEST_MORE_OBSERVATION. Keep original acquisition time; never refresh archived timestamps. Require >=64x64, source=mujoco_camera, nonblank episode/calibration binding and a registered explicit grasp profile for this integration. Do not infer calibration from model confidence or image appearance. Convert normalized points once with the existing mapping; then call ground_observation. Construct OpenCVTargetTracker with the shared evidence; its constructor must succeed, including unique-support containment. Record its existing `_public(initial)` and `_public(destination)` outputs under `opencv_initial_geometry`, with algorithm/calibration hashes. Do not move selected Molmo pixels to a convenient component center or fabricate a depth error bound; unsupported full extent remains unknown.

  Build cloud text messages with user instruction and a bounded serialization of measured target/destination geometry, geometry assumptions and permitted skills. Omit images, acquisition IDs, hidden scene labels, credentials and raw output from Molmo. Request only SkillDecision. Reuse `cloud._request_visual(messages, SkillDecision.model_json_schema())` on the selected compatible cloud adapter, thereby preserving Sol transport protections and generation settings. Parse its actual response body strictly and preserve that content as PlannerDraft.raw_text; native responses stay in their own evidence/raw files. Empty skills means REQUEST_MORE_OBSERVATION with its reason. Invalid/extra fields or bad order fail parsing; they cannot be repaired into accepted geometry. Valid order goes to build_grounded_contract. The pipeline alone supplies trusted contract fields and validates schema/semantics.

  Evidence separates perception model/runtime/raw hashes, RGBD checksum, native normalized points, original pixels, OpenCV geometry and cloud selected profile/request/actual response hashes. Set `model_image_count=1`, `perception_model_image_count=1`, `cloud_model_image_count=0`, `perception_input_mode='NATIVE_RGB'`, and `depth_consumed_by='DETERMINISTIC_RGBD_OPENCV'`. No fabricated VisualDecision/reported_confidence. No raw response is synthesized when cloud was never called. Factory resolves the supplied selected service profile, requires compatible transport, reuses its secret store and accepts allow_paid only explicitly; default false.
- [ ] **Step 4 — Run GREEN/integration.** Same test file plus legacy regression set. CPU fixtures must produce Pipeline success for a valid calibrated scene and closed outcomes for every rejection, with zero actual model/cloud calls.
- [ ] **Step 5 — Commit verified explicit files** with `feat: integrate Molmo OpenCV grounding with cloud skill planning`; record tests and source hashes.

## Task 4: Usable diagnostic, bounded native smoke and delivery evidence

**Files:** create `scripts/probe_molmo_grounded_planner.py`, `tests/test_molmo_grounded_cli.py`, guide and round reports.
**Consumes:** factory, point provider, InitialPlanningRequest JSON and explicit task descriptor JSON; existing service profile store via ModelControlService.
**Produces:** opt-in CLI with dry-run/replay/native accounting and documented factory usage.

- [ ] **Step 1 — Write RED CLI tests.** `test_cli_dry_run_has_zero_calls` checks defaults. `test_cli_replay_is_labelled_and_no_network` checks native/cloud file fixtures bound to exact observation/query hashes, never inferring real execution. `test_cli_native_no_paid_default` ensures native mode does not call cloud unless separately and explicitly admitted (this round smoke remains no-paid). `test_cli_invalid_config_precedes_load` rejects missing files, changed hashes, profile drift, bad descriptor, limits outside 1..8 and preexisting output directory. `test_cli_accounting_keeps_failed_attempt` checks immutable failure record, start count and exit nonzero; no retry/reload.
- [ ] **Step 2 — Run RED.** `-m pytest tests/test_molmo_grounded_cli.py -q -p no:cacheprovider`; missing runner is expected.
- [ ] **Step 3 — Implement runner/guide.** Arguments: `--request`, `--task-descriptor`, `--profile-id`, `--model-store` (existing ModelControlService store), `--model-directory`, `--asset-manifest`, `--output`, `--mode {dry-run,replay,native}`, optional explicit replay point/cloud files and `--allow-paid` (default false). This flag requires separately checked trusted authorization before any real cloud call; R542 default/native smoke never sets it. Default dry-run only validates and reports NOT_STARTED. Replay uses injected provider/cloud fixtures with checksums and is marked REPLAY, never real evidence. Native mode uses the admitted runtime and new raw directory, runs the two queries (up to four descriptor/request pairs, total <=8), and reports real local perception/geometry status. It skips cloud by default; any replay cloud intent used to exercise integration is separately labelled API_FIXTURE and must not become real cloud PASS. Do not add hardware/dispatch flags. Service profiles remain unmodified; do not print secrets or API headers. Store derived report and raw manifest separately. Guide includes factory example and exact CLI commands plus the current calibrated domain, freshness and no-real-cloud limitation.
- [ ] **Step 4 — Run software verification.** CLI tests, targeted regression and all new tests; ruff on changed Python files and `git diff --check`. Then run full suite once with existing environment under host permissions needed for loopback; preserve command, interpreter, all exits and raw logs. Do not silently skip failing tests or install/change dependencies to make it pass. Known environment-restricted suites receive explicit NOT_RUN/BLOCKED classifications; unexpected source failures require the next Astra round. Copy relevant baseline logs into the round evidence before `/tmp` can disappear, preserving bytes/SHA.
- [ ] **Step 5 — Admit and optionally run bounded real local smoke.** Before any model load, verify asset manifest's 26 files against current bytes, prior protocol/runtime versions and import paths, free resources and common GPU lock; no foreign compute apps, >=12000 MiB VRAM free, >=8 GiB available RAM, >=60 GiB disk free. Hold the existing `.r468-r469-gpu.lock` location or same established mutual-exclusion mechanism without killing other work. Use host-authorized GPU/runtime access. Set offline HF/Transformers mode; keep all generated cache/raw artifacts in approved new local locations, not model/SDK trees. Load timeout <=1800 s and per-generation timeout <=900 s; count starts and preserve timeout failures. Load before obtaining any fresh scene intended for actionable integration. If only frozen RGB frames are available, retain original timestamps and run component/replay evidence only; expected stale/no-action outcome is honest evidence. If no admissible fresh RGBD/calibration/runtime exists, record BLOCKED/NOT_RUN with reason and zero calls, not a fake successful pipeline. Native output outside strict accepted grammar is a recorded failed smoke; do not widen parser or repeat loading without new Astra planning. No cloud/hardware run in this step.
- [ ] **Step 6 — Independent review and report.** Review exact changed code and evidence with a fresh reviewer. Resolve newly found issues only under applicable Astra round. `implementation-report.md` records per-task RED/GREEN, all failed starts and delivered source hashes. `phase-summary.md` separates SOFTWARE, REPLAY, REAL_LOCAL, REAL_CLOUD, PHYSICAL, FORMAL_RESEARCH status and explicitly states which are NOT_PERFORMED. Report smoke counts, completed/invalid/absent/error denominators, latency per query (two required per task), load count, input/raw hashes, model identity, cloud paid calls=0 and hardware dispatch=false.
- [ ] **Step 7 — Commit and deliver explicit paths.** Commit verified code/tests/guide/derived reports only; push authorized development branch under existing delivery policy and verify local HEAD, upstream and remote SHA equality. Never include full raw, databases, credentials, weights, SDK or historical frozen bytes. If existing public-network/push restrictions block delivery, preserve local commit and record the exact block; do not equate a manifest with a full remote reproduction bundle.

## Acceptance boundaries and replan rules

- **Software integration:** strict parsing, bound semantics, calibrated geometry, source/freshness rejection, selected-cloud transport preservation and real PlanningPipeline fixture behavior pass; defaults and frozen legacy tests stay compatible. This is the core deliverable.
- **Replay/API fixtures:** exercise deterministic code and schema only, labelled in every report; no real model or cloud claim.
- **Real local:** optional <=1 load / <=8 generation starts, exact assets/runtime/inputs and raw outputs accounted; only native perception and observed geometry behavior. Any missing fresh evidence limits result to component smoke.
- **Real cloud:** NOT_PERFORMED by default. Factory readiness and mocked Sol requests do not establish live cloud success or authorize cost.
- **Physical:** NOT_PERFORMED; no dispatch, no hardware acceptance and no claim that a visible point proves grasp success, object center, orientation, continuous stability or placement.
- **Formal research:** NOT_PERFORMED; no G1/G2, heldout, model reselection or benchmark conclusion. Prior DEV16 remains frozen with its original denominators.

Implementation may proceed under existing user authorization after input verification; no architecture menu or redundant approval gate. New input drift, unsupported runtime behavior, missing dependencies needing installation, helper refactor regressions, broadened calibration/geometry requirements or unplanned failures require a new Astra plan before repair. Independent unaffected tasks can continue. Expected RED import failures and planned fail-closed test cases are not new root causes.

## Exact input verification

All 24 request-manifest files were read and verified by this actual Astra planner; bytes and SHA256 matched. Manifest SHA256: `24d4b539461cdc9c4d1005c2a905e450b53c3113308a316470ade72e974d78a3`. Inventory below is copied exactly; original manifest remains unchanged. Additional inspected sources/raw sample and baseline logs have separate hashes in plan.json.

- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/AGENTS.md` — 1774 bytes — SHA256 `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/docs/superpowers/specs/2026-11-10-molmo-opencv-grounded-planner-design.md` — 2972 bytes — SHA256 `0d7d54bfe1df26a37fcf2daddde6e6956dd3298f0ea2fed3129206a10f48c575`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round542-molmo-opencv-grounded-planner-20261110/request.md` — 2071 bytes — SHA256 `77abeacd055f3fe7b8640beb07d97f469bc4e139c0b89dd3f27cabecac7d2057`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/pyproject.toml` — 2486 bytes — SHA256 `42fdefae6dff25d26e3ded9ab39c7910ee8116f4aed2e9d8f60eee23809e0933`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/planner.py` — 29433 bytes — SHA256 `cc632036242004480e85ae6977cfa4e662ac512b71cd3303c38a0510c7c0b1c5`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/observations.py` — 11603 bytes — SHA256 `1114e6b2de4107ae516f12f8972fcb3b6f71eae7ae5a45bf93adfeb4aa673bb8`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/messages.py` — 6324 bytes — SHA256 `f60868e4db77ac103d94d2b18b769612ae19b54bed60f79fbfe5a2846c5e30a3`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/top_grasp.py` — 8005 bytes — SHA256 `4726f87207d271dfad133852677a50abdc9b267b7a8688742cc87c6869dbc0ae`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/tracking.py` — 35038 bytes — SHA256 `1a34ac6aa012cd58ab9016387310ebea044169b05b59286f4c5a8c540d3c6afc`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/model_resolver.py` — 8205 bytes — SHA256 `e75a94929529a4537a980e33fa4645285baee85aaec0b5597b426c347cd41e04`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/role_models.py` — 10182 bytes — SHA256 `cfc28c29856be9cedcb0b8ca626d6e51e83cec8eaf2c0f637a03b71f757b81bf`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/runtime_binding.py` — 6092 bytes — SHA256 `d6e6c7a42cc57a2ef0aa2e205c6499fe84244be53c8ca91241137265d2fc69dc`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/cloud/planning/pipeline.py` — 27701 bytes — SHA256 `425337b65e8b4493027a55ccb7d7b746f83c75952025458d9da4f7ffee12dba1`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/cloud/planning/models.py` — 6585 bytes — SHA256 `54a83b33bf3f31c0a7efe4485f7f1f651578a342377787cd88ca18429173912d`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/cloud/planning/adapter.py` — 23845 bytes — SHA256 `512670835bcd1da4b7e4fca33cedf4acec3ca866835895a76e577564481d64c4`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/tests/test_rgbd_planning.py` — 20514 bytes — SHA256 `b1d514ebe57648d948c741296aa9bfb6a821098433a8f47e9e42cd8b9964c70f`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/tests/test_rgbd_top_grasp.py` — 7962 bytes — SHA256 `900eac15293ed8cd2ac411243f139ff35d894cf9fada8c22e367a355f56140c6`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/tests/test_rgbd_role_models.py` — 52099 bytes — SHA256 `07a3ca1d8f0d9340cf7828817d474e08e07fd1196ba5cf7a90be91fc83619a9c`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/phase-summary-final.md` — 6861 bytes — SHA256 `c2abd3a13d61c40ebb4c02beb862430484f03e56e50dcd3c7f03c46bad330c08`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/implementation/molmoer_adapter.py` — 3654 bytes — SHA256 `313f3f4225118e0e7e9ac73fba7f3e607c8cb65288ba70d370cd1684e404f612`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/implementation/run_candidate_molmoer.py` — 9284 bytes — SHA256 `78656a182d1dbda702f966d440b701957caed63c089acf530e508b86f51d189a`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/04-molmoer/protocol-r507.json` — 4223 bytes — SHA256 `316d4764b090ac78975db00ab976dce37022494f229ce544cf959447a91867c4`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/04-molmoer/asset-manifest.json` — 13198 bytes — SHA256 `ff0563c87a9bd42a90df49db81dc14ee00d88894ad662f2b43c1942475076464`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/diagnostic/model-inputs.json` — 6885 bytes — SHA256 `f413ce5693f7c68b8830e558fa50fb54282f2fd1b44bda13cc55d7c3cdc614de`

## Planner self-review

Spec coverage, task interfaces, coordinate semantics, missing-confidence handling, all five review-focus classes and acceptance levels checked. Four tasks share the existing pipeline and produce independently testable deliverables; no unresolved architecture decision remains. This plan changes no production code and performs no model/cloud/hardware operation.
