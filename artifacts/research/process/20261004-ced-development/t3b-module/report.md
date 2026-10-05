# T3b role-module software handoff

Software implementation is ready for root integration. Real Max role acceptance, edge acceptance, physical acceptance, and complete T3b acceptance remain NOT_STARTED / unaccepted; no successful real cloud-role probe was produced.

## Scope

Owned files: `vision/role_models.py`, `tests/test_rgbd_role_models.py`, `configs/research/ced_roles.yaml`, and `scripts/probe_rgbd_roles.py`. Root expanded ownership to the nullable API identity validation in `vision/model_resolver.py`. Existing grasp-v2 differences in the working tree predated this assignment; this worker changed only the weight/quantization types and their validation there. No commits, dependencies, shared documentation, active profile changes, or fallback models were added.

## Contracts

- Frozen `RoleProviderSnapshot(role, provider_id, provider_location, model_id, revision, weight_digest, quantization, request_config_hash, source_hashes)` uses roles CLOUD/EDGE/DEVICE and factual locations LOCAL_HOST/REMOTE_SERVICE. CLOUD requires a model ID. All request/source hashes are nonempty full SHA-256 values. The source mapping is copied and read-only. `evidence()` preserves null unknowns; `digest()` binds all fields using canonical JSON.
- Frozen `RoleModelBundle(cloud_snapshot, edge_provider_id, edge_provider_hash, device_pipeline_hash)` rejects a non-CLOUD snapshot. `evidence()` and `digest()` expose/bind every role. `validate_bindings(*, cloud_snapshot_hash, edge_provider_hash, device_pipeline_hash)` rejects changed or swapped hashes.
- `configuration_hash(mapping)` canonicalizes JSON with nonfinite numbers rejected.
- `select_cloud_model_id(model_id, available_model_ids=())` preserves explicitly dated profiles; aliases select the newest valid advertised qwen3.8-max date ID if supplied, otherwise stay aliases. It neither invents revisions nor discovers availability itself.
- `resolve_cloud_role(service, profile_id, *, source_hashes, allow_paid=False, image_size=(320,240), coordinate_system='pixel', grasp_profile='unconfigured', available_model_ids=()) -> (RGBDPlannerAdapter, RoleProviderSnapshot)` reads the chosen existing model-control profile and its SecretStore, never activates a profile, rejects other provider/model families, reuses the existing adapter/endpoint boundary, honors profile token/temperature/timeout values, and attaches `planner.role_snapshot`. API revision, digest, and quantization remain null. The request hash includes endpoint hash, exact model, chat path, generation settings, image/coordinate/grasp protocol, profile config version, and paid-call setting. Credentials never enter it.
- `ModelConfigSnapshot` now allows digest/quantization None for compatible APIs. Local Ollama snapshots reject None while existing empty digest / UNKNOWN legacy profiles remain compatible.

## Probe

`python -m scripts.probe_rgbd_roles --output <fresh-directory>` records NOT_STARTED without consulting the supplied service or renderer. `--execute --allow-paid --profile-id <existing-id> --model-control-db <existing-db>` opts into the real remote nominal S01 probe. The CLI implements the existing SecretStore protocol read-only through a named environment variable (default BIGSMALL_VLM_API_KEY); programmatic `run_probe(..., service=existing_service)` uses its live SecretStore directly. Missing profile/database/key is BLOCKED before transport or renderer access. No global activation, download, local fallback, or actuation occurs.

A real execution records synchronized raw inputs and offline-only instance evidence, actual request/response artifacts without Authorization headers, paired-image byte/hash summaries, strict parse/grounding/refusal results, and actual raw received/sent byte counts through the existing CostLedger. Request-image summaries reuse the existing local probe helper after compatible image conversion. Failed attempted calls remain recorded, and planned/unexecuted counts preserve the denominator. Remote billing and pure inference duration are null. A snapshot can be written only after nominal real-HTTP/real-camera gate checks; this gate explicitly does not establish missing-target/distractor reliability, edge dispatch capability, or physical task success.

The edge entry is an explicitly unaccepted, non-dispatching rules/cost identity without a forced model. Device config includes tracking, semantics, execution, SafetyShield, RGB-D capture/geometry and calibration source hashes. These are bindings, not device acceptance evidence.

## Verification

- `red.log`: 19 expected missing-module failures before implementation.
- `red-nullable.log`: API null identity and local-null validation failures before resolver change.
- `red-probe-boundaries.log`: missing-key path failed to remain ahead of the transport marker; the guard was moved ahead of renderer import.
- `red-wire-bytes.log`: a deliberate missing-byte mutation failed the hand-checked 20-byte malformed-response case, then restored production ledger accounting. The fixture proves refusal/accounting, never model success.
- `red-cli-profile.log`: missing CLI profile/database originally emitted only argparse stderr; now emits machine-readable BLOCKED report with no calls.
- `green.log`: 26 passed, 0.77 seconds.
- `green-safe-regression.log`: 75 passed, 2 deselected, one upstream Starlette/AnyIO deprecation warning, 2.11 seconds. Command: `.venv/bin/python -m pytest -q tests/test_rgbd_role_models.py tests/test_rgbd_planning.py tests/test_rgbd_model_probe.py -k 'not dry_run'`.
- `green-profile-regression.log`: 4 safe CRUD/endpoint/CAS/API profile cases passed, 10 deselected; same upstream warning.
- `lint.log`: Ruff passed for the five owned source/test files.
- `types.log`: mypy passed for role_models.py and probe_rgbd_roles.py; existing unused-override note only.
- `cli.log` / `cli-dry-run-final/`: fresh default CLI NOT_STARTED, no role freeze.

The broader initial scoped regression was interrupted after 42 passes at `test_fake_ollama_models_download_activate_and_planner_dry_run`. That legacy test supplies fake management transport, but service RGB-D dry-run bypasses it and enters real capture/visual service code. The specific pytest process was stopped. The earlier missing-secret RED path also reached beyond its intended software boundary before its fix. Neither run produced successful real-role acceptance evidence; both deviations were reported to root. Further verification used isolated tests, and the full project suite was delegated back to root per explicit instruction to avoid duplicate runtime/model/GPU activity.

## Integration needs / self-review

Root should add a typed `role_snapshot` field to RGBDPlannerAdapter and bind its digest plus edge/device hashes in the new path. The assignment currently uses the typed-property compatibility suppression solely for that handoff. Root owns planner/execution/frozen-loader integration and the cancelled-reply/zero-dispatch test. New paths must not treat the legacy single model hash as a full bundle hash.

The date-model list must come from provider discovery evidence or an explicitly verified profile; this module does not claim registry discovery. Probe acceptance is nominal S01 only: root must schedule real missing-target/distractor probes and reject any unsupported date snapshot rather than silently substituting a model. Existing role hashes make source/request drift and role swapping observable. Software tests exercise production compatible serialization and _post with only the external HTTP boundary replaced by deliberate refusal/malformed replies; no fixture supplies success evidence to the real probe pipeline.

## Fix round 1 — independent review P1 and P2

The review's P1 and P2 were confirmed and both were fixed. Exact reviewed copies are preserved under `reviewed-baseline/`; `fix-round-1.diff` is the exact delta against those files. Root additionally authorized only the constructor / `_post` raw observation hook in `vision/planner.py` and deferred other planner edits for this worker. No runtime integration, unrelated planner behavior, dependency, or commit was added.

P1: `cloud_request_settings(adapter)` now derives canonical effective request settings from the adapter's actual endpoint, provider, model, chat path, timeout/payment settings and immutable image/generation/coordinate/grasp snapshot. The profile config version is retained separately. The nominal report persists the original canonical request settings, edge policy/snapshot, device source map, and per-run config path/hash. Every attempt records effective settings at the outbound byte observation boundary. Final adapter settings are recorded after attempts. `validate_role_probe_bindings(report)` reconstructs and compares the whole bundle digest, edge identity/digest/policy, current cloud/edge/device source hashes, current config file hash, original request hash and every actual/final request setting. `can_accept_role_probe` calls this validator and also requires exact raw-body artifacts with matching hashes/ledger byte counts and production request summaries. Expected request bodies are built from the original bound settings, not a mutable current adapter. Source, endpoint, chat-path, timeout and payment drift all reject the nominal freeze.

P2: `RGBDPlannerAdapter(..., raw_transport_observer=None)` accepts a callback `(phase: Literal['REQUEST','RESPONSE'], path: str, raw_body: bytes) -> None`. It exposes no headers or API key. The hook sees exact serialized outbound body bytes and exact bounded response bytes before decoding, including non-JSON and HTTP error responses. Request observation failure happens before any sent-cost row or HTTP operation. Response observation failure leaves the one actual failed attempt and exact received-byte count intact. There is no retry or fallback. Observer failures propagate a sanitized model-unavailable error and cannot enable a freeze. Observed requests exceeding two million bytes are rejected before transmission; responses preserve the existing 2,000,001-byte bounded read and error accounting.

The probe archives exact bodies as `request.raw` / `response.raw`; their SHA-256 fields now hash those exact bytes. `request.json` / `response.json` are separate parsed convenience artifacts with separately named parsed hashes. Non-JSON and HTTP error bodies still retain raw artifacts. If a body contains the configured credential (plain or its JSON-escaped representation), the raw and parsed body are withheld, its count/hash and an explicit suppression flag remain, and the attempt is BLOCKED. This is an explicit evidence limitation, never a redacted body mislabeled as raw. Previously the original handoff's “actual request/response artifacts” wording overstated the JSON artifacts; only these new `.raw` artifacts provide that reconstruction.

New RED coverage:

- `red-fix-round-1.log`: all 12 P1/P2 regression cases failed on the reviewed baseline (full role/transport drift and whitespace/non-JSON/HTTP-error byte archival).
- `red-fix-round-1-config.log`: per-run config hash drift failed before its check was added.
- `red-fix-round-1-secrets.log`: removing credential withholding failed the secret-echo test; restored code passes.
- `red-fix-round-1-unsent-cost.log`: the request-observer failure initially counted an unsent request; the failing case was recorded before moving request observation ahead of sent-cost creation.

Final verification:

- `green-fix-round-1.log`: 46 role tests passed, 0.79 seconds.
- `green-fix-round-1-regression-final.log`: 85 module / model-probe tests passed, 0.97 seconds. These tests intercept external HTTP before a socket or use probe fixtures; no real model, renderer or GPU is required. No full project suite ran.
- `lint-fix-round-1.log`: Ruff passed for planner hook and owned role/resolver/probe/tests.
- `types-fix-round-1.log`: mypy passed for role module and probe; existing unused-override note only.
- `source-manifest-fix-round-1.json`: exact current SHA-256 values for the six reviewed files.

An intermediate scoped planner regression also passed 95 cases with 2 runtime dry-run cases deselected; those existing planner tests include controlled local HTTP fixture servers, not real providers. Final verification above used module / probe files only. The request-setting and role-source rejection fixtures are in-memory validator fixtures, never persisted as acceptance reports or used to produce a freeze. The unchanged-binding validator positive case explicitly still fails the nominal acceptance gate because it lacks genuine/raw transport artifacts.

No real credential was read or validated in this fix round. A missing-credential gate and synthetic credential-echo withholding are software checks only. A real selected profile/key, real provider registry/date ID, nominal S01, missing-target/distractor reliability, edge capability, physical outcome and full T3b acceptance remain unverified. No accepted real-role snapshot was produced. Ready for scoped independent re-review of both fixes.

## Fix round 2 — alternate escaped credential echoes

The fix-round-1 review confirmed the original full-binding and exact-wire findings resolved, then reproduced a separate blocking credential-echo encoding issue. The reviewed baseline is preserved under `fix-round-2-baseline/`. This round changes only `scripts/probe_rgbd_roles.py` and `tests/test_rgbd_role_models.py`; the authorized planner byte hook and other source files are unchanged. Exact delta and six-file manifest are `fix-round-2.diff` and `source-manifest-fix-round-2.json`.

Before raw or parsed persistence, the probe now inspects both the untouched body decoded with JSON-compatible Unicode encoding detection and all recursively decoded JSON keys/values. Valid JSON Unicode/surrogate, quote, solidus, backslash and control escapes are inspected, including nested strings and repeated escape layers. Non-JSON and HTTP-error bodies use the same text inspection. Inspection is bounded to eight escape-decoding passes; remaining valid opaque escape layers are conservatively withheld. JSON structure traversal uses an explicit stack. No decoded/transformed text replaces the wire bytes or becomes the wire hash input: count and SHA-256 are captured from the original bytes first. Benign escaped bodies still archive exactly the received bytes and original hash.

Any detected credential causes the entire response body and parsed convenience artifact to be withheld and the attempt to be BLOCKED. No parsed response, scene/evidence field, or decoded reason escapes that failed observation hook. Derived attempt/error details and the top-level report also undergo credential inspection: sensitive details are replaced by a suppression marker, hash and verified numeric byte counts. Malformed textual counts cannot carry the credential through that smaller record; unknown counts remain null rather than being fabricated as zero. When a failing SecretStore prevents reading the key, arbitrary exception class names are kept opaque as a hash with a fixed PROBE_FAILED code; exception messages are never persisted. These records remain failures and cannot produce a nominal freeze.

RED evidence:

- `red-fix-round-2.log`: 12 of 13 alternate-encoding cases reproduced missing withholding on the reviewed baseline; the existing exact astral surrogate representation was already blocked.
- `red-fix-round-2-details.log`: a malformed sensitive count initially escaped detail suppression; now only actual nonnegative integer counts remain.
- `red-fix-round-2-report.log`: a synthetic profile exception class named after the synthetic credential initially appeared in the report; the top-level artifact guard now withholds it.
- `red-fix-round-2-unicode-encoding.log`: a UTF-16 non-JSON escaped echo initially bypassed UTF-8-only inspection; JSON-compatible Unicode encoding inspection now rejects it.
- `red-fix-round-2-unknown-count.log`: a withheld malformed count is null rather than a fabricated zero.
- `red-fix-round-2-unavailable-key.log`: a SecretStore exception name initially leaked before key retrieval; opaque error-class hashing now prevents that output.

Final software evidence:

- `green-fix-round-2.log`: 67 role tests passed (see log for exact recorded runtime).
- `green-fix-round-2-regression.log`: 106 role/model-probe tests passed (see log for exact recorded runtime). All external HTTP is intercepted by in-memory boundaries and all capture is existing observation fixtures; no sockets, actual model, renderer, GPU or full suite ran in this round.
- `lint-fix-round-2.log`: Ruff passed for owned modules and the existing narrow planner hook.
- `types-fix-round-2.log`: mypy passed for role module and probe; only the existing unused-override note remains.

Synthetic credential markers necessarily occur in test source and RED assertion logs; they are explicitly non-secret test data. No real credential was read, validated, printed or archived. Tests confirm the returned attempt/report objects and their written artifacts omit the synthetic literal credential, preserve exact original body hashes/counts when withheld, and never generate a freeze. Real profile/key validity, Max-role acceptance, provider date availability, edge acceptance and physical acceptance remain unverified. Ready for scoped independent re-review.
