# R222 — ordered local lease dispatch patch recovery

Actual planner: gpt-6-astra, /root/astra_status_plan. Plan only, awaiting ROOT gate.

The native apply failed to find heartbeat_lease context. Its real signature is identical at line 513; the failed patch first matched _local_read_scope around line 1293 and then searched backward. Correct hunk order and precise function context; do not change the signature or intended behavior.

The three targets currently equal their genuine R220 pre-failure archives byte-for-byte. The nine saved subsequent successful patches did not target them. No persistent modification by the failed batch is observed; this does not establish tool atomicity. The original UNKNOWN partial-write status, throw, absent structured result/numeric exit/streams remain intact.

Only operational_lease.py, sqlite_repository.py and worker.py under simulation_runtime may receive the exact prior un-applied delta. One native application, increasing source order: lease constructor/ingress; repository heartbeat before local_read_scope; worker owns-publication/cancel/timeout. Function-qualified contiguous context replaces ambiguous repeated import/try anchors. Preserve every intended added/deleted line, SQL literal and parameter. The seven regions and nine edit units are specified in plan.json.

ROOT checks current25/archive25, genuine earlier three baselines, protected211 and the exact corrected patch before application. Same actual gpt-6.1-sol author performs one CAS-guarded native patch, then one bounded stdlib byte/hash/diff readback with full after archives and immutable receipts. All other22 manifest records and protected211 remain unchanged during recovery. Source proof is not behavior validation.

No product/test/static/AST/import/SQL/probe/Git/network execution or new GREEN slot. Original RED1/0 remains spent; GREEN0/1 remains held. No unrelated broker consume/RPC redesign. Any new failure or scope change stops for genuine Astra planning. Successful text recovery only returns to original T2 source preparation, followed by the full candidate gate.

Complete full-SHA inputs, exact per-function boundaries, CAS, outputs, one-shot counts and capture limits are in plan.json/input-observation.json. Original failures and R220 patches are never overwritten.
