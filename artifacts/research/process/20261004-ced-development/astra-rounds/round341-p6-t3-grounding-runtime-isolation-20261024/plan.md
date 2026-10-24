# R341 Grounding Runtime Isolation Implementation Plan

> **For agentic workers:** Continue with the existing same-Sol workflow after ROOT activation. No new agents or runtime actions.

**Goal:** Select the intended local runtime without querying unrelated unadopted runtimes.

**Architecture:** Use the existing sealed original-description registry only as a shortlist, validate the unique live owner/runtime on its original thread, then read its durable original and retain the real private binding path.

**Tech Stack:** Existing Python registries and owner checks; standard-library AST/symtable/text/hash verification.

**Spec:** `root-finding.json`, three untouched source snapshots and R331 contract. Actual planner: `gpt-6-astra`, `/root/astra_p6_t3_plan`. Implementer: existing `/root/p6_t3_sol`, pending ROOT activation.

## Evidence and cause

`_initialize_local` calls `_register_local_original` before bootstrap initialization and adoption. Registration stores the actual runtime in `_LOCAL_RUNTIMES`. Current `bind_step_grounding` evaluates every registered runtime's `original.digest()`, while `original` first reads `supervision_source_publication` and raises if no coherent publication exists. Thus an unrelated real registered runtime still in bootstrap can abort the requested valid grounding, including by accessing a foreign owner/thread source.

This is a source-reachability finding, not an observed runtime failure. `planner-readout.json` and `source-slices.json` preserve the finite chain. All input SHA256 values are in `plan.json`. The current target matches the frozen `bind_step_grounding` segment. No original failure/snapshot is changed.

## Narrow implementation

Only the local selection/binding block and its local imports in `src/cloud_edge_robot_arm/vision/owner_registration.py::bind_step_grounding` may change. Keep all deterministic checks and the complete binding payload. Do not modify registration, adoption, runtime getters, `_local_bind_grounding`, operational clocks/caps or tests.

- [ ] ROOT verifies source applicability and activates the same Sol. Preserve R340's exact successor, its original plan/failure and unrelated source bytes.
- [ ] Compute the requested canonical descriptor using the existing `operational_windows._json(original.local_time.to_payload())`, imported under an unambiguous alias. Snapshot `_LOCAL_RUNTIMES.items()` and shortlist pairs by `_LOCAL_ORIGINALS.get(owner) == desired_descriptor` only. During scanning do not call runtime getters, repository methods or clock reads. Require exactly one pair before live validation; missing and duplicate matches reject.
- [ ] Validate that selected pair: exact owner/runtime types, runtime-to-owner identity, unchanged registry pair and sealed descriptor, genuine `_OWNERS` entry, not closed, captured LOCAL startup mode and original thread. Check captured startup job/run/attempt/lease/worker fields against `current_identity`; check runtime source repository/IDs, binding and session against the actual startup worker. Both private original descriptions must match the sealed descriptor, and source hashes must agree. Do not search for another candidate when a selected check fails.
- [ ] Call selected `owner._check_app_live()` before any selected publication/original getter. Then obtain only that runtime's `original`; require exact local original type, full identity, digest, local-time descriptor and source-hash equality. Let missing, stale or incoherent selected publication fail closed. Do not swallow exceptions or substitute serialized authority.
- [ ] Invoke the same selected runtime's `_local_bind_grounding` directly from `bind_step_grounding` with the unchanged payload and observation. Preserve its caller-code guard, publication/checkpoint/revision/generation/frame checks, observation-window checks, two-authority locking, transactions, receipts and replay behavior.
- [ ] Sol records minimal diff and before/after target SHA. ROOT independently reviews AST/source order and the case matrix, verifies all non-target bodies and nonlocal behavior unchanged against the immediate baseline, then saves a narrow static acceptance report.

## Review focus and source-only verification

The case matrix in `plan.json` covers unrelated same/foreign-thread bootstrap runtimes in any registry order; a genuine unique target; missing/duplicate registrations; forged descriptions; closed/revoked/expired/foreign-thread/source-drifted targets; selected pre-adoption runtime; and changes to publication/frame state after selection. Prove from source that unrelated runtime getters are unreachable, ambiguity rejects before getters, and selected liveness plus downstream strict binding still apply. Description equality only selects an object to validate; it never issues authority.

Use standard-library AST/symtable and source/hash comparison only. Preserve original snapshots, all prior failures and R340 cap. No product imports/calls, tests, collection, probes, new test cases or runtime commands. Do not freeze or restore whole files merely because evidence snapshots have different hashes; review affected definitions and attribute independent changes.

## Prerequisites and acceptance

ROOT's plan/pin review and activation are required before implementation. RED remains SPENT and GREEN UNUSED/HELD; nine nodes, max15 worker polls and all original allowances remain unchanged. This plan does not release GREEN or authorize HEAD drift. Original actor/source/HEAD/resource and applicable correction gates remain necessary for future execution.

Acceptance means source-only lookup isolation with genuine selected-owner authority and unchanged producer checks. It does not claim runtime success, T3/B-final completion or C/native/model/physics results. Any new cause or unexpected validation failure returns affected work to Astra.
