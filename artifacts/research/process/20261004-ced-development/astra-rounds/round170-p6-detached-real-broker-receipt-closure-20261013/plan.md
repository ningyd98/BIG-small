# R170 Real Broker Receipt Contract Repair Plan

> **For agentic workers:** Retain the same sole Sol author and ROOT gating workflow.

**Goal:** Align detached receipt decoding and two caller-created T1 helpers with the actual broker producer.

**Architecture:** Preserve raw seven-field receipts without normalization. Immutable original acquisition and renewable current segment are separate same-domain records; neither detached codec nor caller fixture creates authority.

**Tech Stack:** Existing Python codecs; one stdlib text/hash metadata proof. No new test/static/Git command.

**Spec:** /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/plan.json, schemas.original_time/decision. Exact scope, fields, fixtures and 22 full input pins are in plan.json.

Actual Astra: **gpt-6-astra**, `/root/astra_status_plan`. This is source-informed planning, with no product edit or execution.

## Confirmed source mismatch

Real `_Segment.receipt()` exports `domain,event_id,lower_ns,upper_ns,deadline_ns,budget_ns,end_exclusive`. The broker preserves original acquisition on heartbeat, exports a separately renewed segment, places generation outside those receipts, and emits current as a three-field bracket. P5 deadline arithmetic is `lower_ns + budget_ns`; the hard-open test uses current upper strictly below the relevant segment deadline.

The draft instead treats original acquisition as an app event bracket, and its fixture/R169 patch invent segment `origin`/`generation`. R158 provides no approved alternate normalization that makes this valid. This is a real source-contract mismatch, not an executed test failure.

**R169 disposition: HELD_SUPERSEDED.** Its patch and metadata actions remain unactivated, used0; preserve its old plan/error and do not execute its predicted patch/hash.

## Limited repair

- [ ] ROOT verifies inputs and records the R169 disposition; preserve current shared/test before bytes.
- [ ] Sole author adds a pure exact seven-field receipt validator, updates `_original`/`_decision` and the envelope original-acquisition equality join. No broker/P5 producer change. Current segment may differ from original on heartbeat; compare current lease time only to current segment deadline. App hard/effective bounds remain solely in D_app.
- [ ] Change only `_b_detached_original` and `_b_decision` to produce that true field shape. Their data remain explicitly caller-created UNKNOWN descriptors. Generation2 has a distinct synthetic current receipt while the original receipt/hash remains fixed. Keep original app timing and all seven test bodies/A-prefix/legacy goldens unchanged.
- [ ] ROOT reviews the complete limited diff. Run only one newly authorized stdlib metadata action to prove text scope and unchanged seven domain drafts/producers/runner/golden/protected inputs, then save receipts and step report.
- [ ] Return to original T1 preparation. Only the existing unused t1_green may later run after the original fresh ROOT source/fixture/runner gate; this plan does not execute or release it.

## Boundaries

R158 remains2spent/13held; no new pytest/static/AST/import/SQL/probe/Git, no A40/RED/control rerun. Preserve actual raw broker values, original acquisition/epoch and original budgets; no cross-domain numeric clamp, no new app origin, no constructor authorization. The seven domain adapters stay pinned through this repair. UNKNOWN fixtures are not evidence of a real registered broker heartbeat or publication. Different failures/scope extensions require a new actual Astra plan.

