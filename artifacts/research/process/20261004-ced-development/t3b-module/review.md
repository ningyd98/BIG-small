# T3b independent module review

Review date: 2026-10-04. Scope: supplied `review-package.diff`, `report.md`, relevant existing transport/profile/capture code, and ced.research.v2 sections 4, 5, 8 plus roadmap T3b. The new-file package snapshots match the inspected working files. Read-only source review; no tests, model calls, network calls, GPU, renderer, or physical experiments were run. Only this review was written.

**Specification verdict: REQUEST CHANGES for the nominal probe/freeze gate; partial compliance for the role identity and resolver contracts.**

**Code-quality verdict: REQUEST CHANGES.** The dataclasses, defensive source-map copy, canonical hashing, null API identity, existing profile/SecretStore/endpoint/transport reuse, dated-ID selection, and default no-execution boundary are sound. The tests use refusal/malformed HTTP fixtures and explicitly do not claim real acceptance. The report accurately keeps real cloud/edge/physical/T3b acceptance unaccepted. Existing 26-pass log was inspected, not reproduced.

## Findings

### P1 — nominal acceptance does not revalidate the full role/request binding before writing a freeze

Location: `scripts/probe_rgbd_roles.py:173-176`, `:198-209`, `:281-288`, `:342-343`; request settings are created at `vision/role_models.py:200-220`.

`can_accept_role_probe` only reconstructs/rechecks the CLOUD snapshot and its sources. It never checks `bundle_hash`, the edge snapshot against `edge_provider_hash`, current device source hashes against `device_pipeline_hash`, or actual adapter endpoint/chat path/timeout/payment settings against `cloud.request_config_hash`. Its expected request is built from the current adapter in `_attempt`, so equality with that expected summary is not a comparison with the original role configuration. The cloud fingerprint list does not include device-only files such as tracking, execution, and SafetyShield. Consequently changing one of those sources during a real probe, or changing the adapter endpoint/chat path while retaining its model, can leave the initial bundle accepted and written to `roles-frozen.json`. This is a module-owned nominal freeze gap, separate from pending execution integration.

Persist the canonical request settings and device/edge source maps, derive the actual transport configuration from the adapter, and revalidate all identities/current hashes and the bundle digest before acceptance. Include negative gate cases for device/edge source drift and endpoint/chat-path drift. No real service execution is needed to verify rejection.

### P2 — archived response JSON is not the received wire evidence

Location: `scripts/probe_rgbd_roles.py:382-386`, `:393-413` (existing `_post` decodes raw bytes in `vision/planner.py:247-261`).

The instrumentation receives an already decoded dictionary and writes sorted, indented JSON. `response_sha256` therefore hashes a reserialization, while the ledger records the actual raw response length. For the supplied whitespace-bearing 20-byte fixture, `response.json` cannot reproduce the received byte string/hash. HTTP error and non-JSON responses have no response artifact at all, only exception type and ledger count. The request artifact is also a reserialization rather than the exact transmitted bytes. Actual accounting is preserved, but the handoff's “actual request/response artifacts” claim exceeds what an independent auditor can reconstruct.

Expose a bounded raw-byte observation hook at the existing transport boundary and archive/hash those exact request/response bytes, including failure responses, without Authorization headers. Keep parsed JSON as a separate convenience artifact.

## Cannot verify / integration dependencies

- Typed `RGBDPlannerAdapter.role_snapshot`, planner/execution/frozen-loader binding, cancellation/late reply causing zero dispatch, and replacement of the legacy single-model hash are root-owned pending integration. Their absence is not charged to this module as an additional finding.
- The ordinary immutable snapshot digest observes declared bindings; it is not proof of immutable remote weights or genuine physical execution.
- No real nominal S01 acceptance, missing-target/distractor probe, provider registry discovery, edge capability acceptance, or physical task acceptance is established by this package. The report is candid about these limits; the module must remain unaccepted for those scopes.
- Whole-project regression and the earlier interrupted real-boundary deviations were not reproduced in this review.

No separate Minor finding.
