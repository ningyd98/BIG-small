# Molmo2-ER + OpenCV grounded cloud planning

User decision (2026-11-10): use Molmo2-ER for identification and localization, OpenCV with aligned raw depth for geometry, and retain existing cloud planning and program validation. This is the selected architecture, authorized for development; no further model search or architecture approval is needed.

## Scope and approach

Integrate a native, single-RGB Molmo pointing provider into the existing InitialPlanningRequest -> PlannerDraft -> PlanningPipeline path. Two explicit object/destination queries bind to one immutable RGBDObservation. Accept one unambiguous point per query or explicit ABSENT; reject malformed, contradictory, multiple or out-of-range output. Preserve native normalized 0..1000 units and map once to original image coordinates.

Raw optical-z float32 metres, calibration, source and timestamps remain bound to the observation. Use the existing OpenCV/RGB-D geometry, top-grasp calibration and source restrictions; no metric depth is inferred from a display PNG. Missing depth, absent/ambiguous targets, stale data and invalid calibration cannot produce an actionable draft.

The configured cloud model remains unchanged (current selected Sol profile stays Sol). It chooses only whitelisted skill intent using the grounded scene; its outputs cannot replace Molmo pixels, OpenCV geometry or trusted contract fields. Reuse the existing transport, credential store, planning schema/semantic checks, SafetyShield and execution path. Preserve visible pose markers, top camera and controller.

## Alternatives considered

1. Selected: native Molmo pointing + deterministic RGB-D geometry + existing cloud planning/validation. Supported by local native DEV16 signals and separates model semantics from calibrated measurement.
2. Full dual-image JSON directly from Molmo: current published template rejects system role and full generation mode is unverified; outside this implementation.
3. Replace the cloud model or train a depth VLM: unnecessary for the selected architecture and outside scope.

## Delivery and acceptance

Deliver a usable opt-in adapter/factory and CLI configuration, strict parsing and binding tests, a local native provider using the already validated BF16 runtime without modifying model/SDK files, and an integration diagnostic with complete request/result accounting. Defaults and frozen historical runs remain compatible. No model auto-download, paid cloud call, robot dispatch, hardware acceptance, formal heldout claim, or public push is implicit in software validation. A small real local Molmo smoke may run after resource and input identity checks; record real calls separately from replay tests.

Acceptance is software integration and bounded development evidence, not G1/G2 or physical task success. Existing research selection, calibration and formal experiment gates remain in force. Raw model output and raw sensor files remain local under established delivery rules.
