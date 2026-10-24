# R338 terminal audit mode-boundary repair plan

**Actual Astra:** `/root/astra_p6_t3_plan`, `gpt-6-astra`. **Implementer:** existing `/root/p6_t3_sol`, after ROOT activation.

The frozen candidate applies LOCAL's new event/runtime/receipt proof requirements to every operational finalizer. Both genuine FOUNDATION and LOCAL sessions reach that path, but only LOCAL registers `_LOCAL_RUNTIMES`. This would block the protected FOUNDATION positive-publication path. No runtime failure was executed.

The five original candidate snapshots remain under `source-evidence/`. `mode-boundary-source-slices.json` records finite relevant definitions and original d66e shared finalizer/dispatch source. `plan.json.inputs` holds actual hashes. Independent ongoing implementation is not subject to whole-file rollback.

## Narrow authority-based dispatch

- [ ] Add private repository `_final_publication_mode(view)` classification. Resolve the genuine issued view/session, require it is the repository's actual current private session and worker-owned session, verify repository/worker identity and finalizer purpose, then call existing `_check_ingress`. Read the validated captured `session._mode` only. Allow exact LOCAL or FOUNDATION; reject unknown/foreign/drifted sessions. Never use public config, caller booleans/dicts, missing receipts or caught errors as a mode fallback.
- [ ] In `finalize_operational_publication`, run the new `_final_publication_sources`/TLS context insertion only for validated LOCAL. Keep original SQL preview, publish callback, checks, terminal rows, attempt/lease and filesystem behavior common and unchanged.
- [ ] In `_dispatch_writer`, stage/take/record the new audit only for validated LOCAL. **Both modes still execute actual proposal → COMMIT → `confirm_committed(ack)` exactly once in the original order.** Missing LOCAL context/proof denies; it cannot downgrade to FOUNDATION. Preserve cleanup and error propagation.
- [ ] Guard the three new source/stage/record helpers against non-LOCAL callers using that same private mode relation plus their existing caller/proof checks. Preserve every LOCAL app check, exact job/event completion join, terminal snapshot, actual manifest/root join and one-use audit CAS.
- [ ] In `operational_lease._rpc`, restrict only the newly added auxiliary final-proof minting to the validated LOCAL session mode. Preserve both modes' real broker confirmation and response-consumption path, timeouts and bounds. `_take_final_confirmation` independently rejects non-LOCAL. Do not change `confirm_committed`, ACK consumption or original lease authority.

No worker/test/operational-window changes are required for this correction. No new tests or nodes. Other ongoing authorized changes in these files remain separately attributed to R331.

## Truthful public summaries

Preserve existing summary behavior: a FOUNDATION or older operational row with no new valid audit is **UNKNOWN, accepted=false**, with empty confirmed paths and intact historical paths/status/results. An existing incomplete/invalid receipt remains **UNCONFIRMED**. Only non-operational legacy rows are **NOT_APPLICABLE**. Never fabricate CONFIRMED, synthesize local receipts or relabel FOUNDATION as non-operational. This does not alter FOUNDATION's actual file promotion or stored SQL history.

## Source-only verification

- [ ] ROOT checks applicability of frozen affected definition slices, then activates the same Sol. Do not demand rollback of independent local producer/cap/execution edits.
- [ ] Parse changed modules and build symbol tables without importing/executing them. Save exact scoped diff, before/after slices/hashes and `implementation/source-proof.json`.
- [ ] Produce a static path table for LOCAL, FOUNDATION, no-session legacy and invalid session. Show common real COMMIT/confirm remains unconditional, local audit remains compulsory only for LOCAL, and caller-controlled mode/proof absence cannot select FOUNDATION.
- [ ] Compare the original shared FOUNDATION path to the pinned Git slices modulo guarded new audit blocks. Preserve SQL/attempt/lease/file/exception behavior and the protected positive-test bytes. This is source evidence, not an A runtime replay.
- [ ] Show LOCAL's existing strict checks remain reachable and unchanged; summary classification is unchanged. No test/node/poll additions, no source validator weakening.
- [ ] Keep R331 plan/runner/evidence and both ledgers unchanged: RED **SPENT 1/0**, GREEN **unused HELD 0/1**. ROOT independently accepts the source correction and includes its actual new generation/provenance in the future GREEN gate.

R338 authorizes only the specified two-file audit mode guards. It adds no runtime/import/collection allowance, RED rerun, GREEN reset, agent or B acceptance. New root causes, wider public-summary changes or inability to classify securely require actual Astra before further affected repair.
