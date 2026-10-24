# R344 Grounding Live Schema Adapter Implementation Plan

> **For agentic workers:** Same Sol, source-only after ROOT activation. No runtime or new agents.

**Goal:** Route the two live window checks to the strict validator for their genuine owner's mode.

**Architecture:** Resolve the actual current owner before validation, use its captured startup mode, and keep every subsequent registry/source/acquisition/window/clock check. Legacy and LOCAL history validators remain unchanged.

**Tech Stack:** Existing Python validation functions; stdlib AST/symtable/source/hash verification only.

**Spec:** Final R344 finding, R331 failed GREEN disposition and four frozen source files. Actual Astra: `gpt-6-astra`, `/root/astra_p6_t3_plan`. Implementer: existing `/root/p6_t3_sol`, awaiting ROOT activation.

## Original failure and evidence limits

Session70536/toolchunk `e80139` ended wrapper1/child-15 after 600.0875676120049s, timed_out=true. The leader was reaped, group_remaining=false and recorded cleanup_errors=[]. Raw stdout is exactly `FFFF`. Four completed resource sidecars report entered_behavior=true, assertions_completed=false and `RuntimeError: grounding original acquisition window unavailable`.

There is no JUnit and no runner source-after. HEAD changed from `18e1844b6ad870c10a07cd7a490e1a40dfd6fb2a` to `729bce11bbd55a4a869e25e52174da3d0db1825b`; runner capture stopped with `HEAD changed`, so subsequent case/DB/archive/resource aggregation was not completed. ROOT's later matching 300-pin observation is separate metadata, not a substitute for missing capture. Do not claim all nine nodes completed, complete capture or a passing candidate.

All 21 recorded inputs were rehashed. `plan.json` records their SHA256 plus the finding and new finite source/readout evidence. Original plans/gates/raw/sidecars/failure bytes remain intact.

## Root cause

LOCAL `export_record` emits `simulation.operational-window.local.v1` and `SEPARATE_D_LEASE_DECISION`. Both `_check_observation` and `_check_reference` call `_validate_references`, which only accepts legacy `simulation.operational-window.v1` and `UTC_LEGACY_VETO`. The local descriptor necessarily raises ValueError; `_check_observation` turns it into False, producing the observed outer grounding exception.

This is a sufficient deterministic rejection path for the shared observed failure. It does not establish why the complete command exhausted time or what occurred in uncompleted nodes. The real capture/adopt helper and enclosing worker scope provide no basis for changing fixture TTL, counters or authority. Existing `local_temporal._reference` provides strict LOCAL typed validation; it does not issue live authority.

## Exact narrow repair

Only `operational_windows._check_reference` and `_check_observation` may change. Exact old/new blocks and expected canonical successor SHA256 are in `plan.json`.

- [ ] ROOT accepts final failure/spend evidence, verifies selected source pins and activates the same Sol to thaw only these two definitions. Keep the original run's source gate unchanged as historical evidence.
- [ ] In each function, obtain `_current_owner()` before parser dispatch and preserve its existing no-owner behavior. Dispatch only on `owner._startup.mode`: LOCAL calls existing `local_temporal._reference` through a lazy local alias; FOUNDATION calls unchanged `_validate_references`; unknown mode rejects. Never select authority using the descriptor tag, caller flag or mutable public mode.
- [ ] Keep all downstream source logic unchanged: exact descriptor equality to actual owner export, registered observation/window and event linkage, `owner.check`, original policy/max_age and clock `within_age`, hard bounds and thread/source checks. Parsing alone grants no positive result. Preserve no-reference/no-owner None, explicit-reference/no-owner False, and no-owner reference UNKNOWN behavior.
- [ ] Sol saves immediate before/after source and exact diff. Use AST/symtable/text/hash only to prove the two exact replacements and unchanged other definitions, legacy/local parsers, worker code, test bytes and fixtures. Use `ast.get_source_segment` UTF-8 bytes without added newline for pins; do not execute validators or product code.
- [ ] ROOT independently reviews the exact diff and case matrix, then records source-only acceptance. HEAD/time/capture salvage remains separate R345 work.

## Static review matrix

Check genuine LOCAL and FOUNDATION paths; mismatched schema/mode and unknown mode; missing or foreign owner/window/observation; copied descriptors; malformed schema fields; and exhausted age/hard bounds or wrong thread/source. The proper existing typed parser must run, followed by all original live checks. `_validate_references` remains byte-for-byte legacy-only for its historical decoder callers; `local_temporal._reference` also remains unchanged.

## Preconditions and acceptance boundary

R331 RED and both ROOT/AUTHOR GREEN ledgers are SPENT1/0. This plan allocates no execution, parser probe, collection, test, retry, refund or replacement slot. No database access or old runner/raw/capture repair is authorized. Source-only implementation requires ROOT's review and narrow activation. Any future runtime needs a separate actual Astra disposition and authorization; the original GREEN cannot be reused.

Acceptance means source-level mode dispatch repaired while private authority remains strict. It is not runtime verification, T3/B-final/C acceptance, complete capture or real model/native/physics evidence.
