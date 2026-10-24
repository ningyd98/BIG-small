# R350 — stopped after third node; two current-generation nodes accepted

R350 preparation and source-only review were accepted under the actual Astra plan. Its source gate pins 381 immutable files at HEAD `729bce11bbd55a4a869e25e52174da3d0db1825b`. Exactly one fresh first-node allowance and eight exclusive unused R346 transfers were adopted. Historical failures, ledgers and gates remain unchanged.

| Node | Actual result | ROOT decision |
| --- | --- | --- |
| t3_01 startup/grounding memory | Wrapper 0, child 0; 316.398 s outer; one exact JUnit pass; one genuine completed resource sidecar; one observed poll | Accepted, disposition SHA256 `e7ab8ecfa26c350076e7c522db20d10f9d514c916360e3cc2f7e5f1d0ddff060` |
| t3_02 startup/grounding SQLite | Wrapper 0, child 0; 317.971 s outer; one exact JUnit pass; one genuine completed resource sidecar; one observed poll | Accepted, disposition SHA256 `763723e559dcb5422018519045b7a71ae71d4315764bb0d51fd96adaed2320ee` |
| t3_03 UTC provenance memory | Wrapper 1 in 600.727 s; child -15; enclosing 600-second bounded operation raised DeadlineExpired; no JUnit, completed sidecar or completed case | Rejected, disposition SHA256 `0bedfe1d03ab005a798ad18317bd90d52a78b5fc92b7d22e8007a87cada3c47d` |
| t3_04 through t3_09 | Not launched | Six HELD slots; stop-on-first-unaccepted rule applies |

The accepted nodes preserve SOURCE_BINDING_ONLY grounding, the original time/hash joins, real worker and database paths, and CPU software scope. They do not qualify native/model/physical behavior. These results belong to the exact frozen R350 source generation.

The third attempt was reserved once as `7e22cd60-ba3a-41c7-b564-58d534b5406d`, actual session 93248, final tool chunk a813fc. Child elapsed through cleanup was 600.0115213539975 s. The leader was reaped, the process group was empty, and cleanup reported no errors. Original `result.timed_out=false` and outer `timed_out=false` are preserved alongside the actual DeadlineExpired traceback. The discrepancy is a future classification question, not a reason to rewrite history. The cause of noncompletion is UNKNOWN: there is no child stack or completed case. Only the first `memory-1` scenario directory was observed.

All 381 source pins match before, after and on independent ROOT readback. All 2,501 recorded HEAD samples were accepted, with maximum successful gap 0.2617440200119745 s. There was no successful observed-child-exit tail receipt; no such coverage is claimed. The seven finalization receipts were saved: raw process, source-after, persistent inventory and prerequisite completed; resources, JUnit and cases failed because required completion evidence was absent. The terminal completion record truthfully has `behavior_candidate_pass=false`.

ROOT independently verified 40 existing regular files totaling 15,227,476 bytes, plus two exact database byte copies. These are retained file bytes, not a coherent database backup claim. Missing resource sidecars leave actual failed-node allocations and polls UNKNOWN, not zero. The first two accepted nodes observed two polls; an exact total for all three attempts is unavailable. The failed allocation is consumed and never refunded.

Both R350 ledgers now have three SPENT slots and six HELD slots. The historical R346 first failure remains SPENT; its eight original records remain nonexecutable under the exclusive transfer overlay. No R350 retry, later-node launch, product edit, commit or push was performed after this failure.

Actual Astra R351 was requested with 50 pinned inputs, the original failure and retained evidence. Intake SHA256: `15d8b481ec7348b2faf3344bb436e223d134bbc52a37e44a531d34c858abf23e`. Same Sol remains frozen pending ROOT review of an actual Astra plan. Bounded T3, full B, C, native/physical behavior, formal research acceptance and a complete remote reproduction package remain unaccepted. The fresh independent T3 review seat remains unused.
