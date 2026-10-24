# R346 individual T3 validation — first-node failure and stop

ROOT executed only `R346:t3_01`, the memory-backed `test_private_startup_to_transaction_grounding` node, after R348 source correction acceptance and the complete new 347-pin source gate. This is **one failed command, zero accepted nodes, eight commands not run**. It is not T3, B9, whole B, native, physical or formal acceptance.

The exact reserved outer launcher returned 1 after 129.54263916698983 seconds. The actual selected child returned 1; elapsed through owned-process cleanup was 129.21119930999703 seconds. Neither child nor outer launcher timed out. The observed failure is `ValueError: exact source binding scope required`: the local grounding producer supplied `DURABLE_BINDING_ONLY`, while the existing decoder requires `SOURCE_BINDING_ONLY` for this nonpublication tag. Correct repair semantics are assigned to actual Astra R349 before any change.

The selected ROOT and AUTHOR slots are both SPENT, used 1 / remaining 0. The other eight slots remain HELD, used 0 / remaining 1. Original R331 RED and GREEN remain SPENT; no attempt was refunded and no diagnostic successor was launched.

## Actual evidence

- Original stdout is 9,620 bytes; JUnit records one failed selected node with zero errors or skips. The child stderr is empty.
- All seven independent stage receipts and the terminal completion record exist. Completion states candidate false. The resources, JUnit and case stages reject behavior; their persistence succeeded. The expected case completion record was never produced and remains absent.
- Both source-before and source-after accepted the exact same 347 pinned inputs and exact HEAD `729bce11bbd55a4a869e25e52174da3d0db1825b`. ROOT independently rechecked all current pins.
- All 539 sampled HEAD observations were accepted; the largest measured completion gap was 0.2550562579999678 seconds. This is sampled evidence, not continuous observation.
- Owned child cleanup reports leader reaped, process group empty and no cleanup errors. The genuine resource sidecar records 402 allocations, 402 initialized resources and 402 observed cleanups; two worker constructions and one normally returned poll. Entered behavior is true; nested assertions completed is false.
- ROOT independently verified all 40 observed regular basetemp files, totaling 8,178,261 bytes, the two requested database byte copies, and the original resource sidecar copy. No database engine was opened by capture or ROOT. File copies do not constitute a transactionally coherent database backup.
- The original runner booleans `artifact_retention_complete=false` and `required_evidence_complete=false` are preserved. Available retained bytes and completed finalization do not substitute for missing behavioral completion evidence.

The original result, raw files, source gate, receipts and history remain unchanged. The ROOT disposition is `root-t3_01-disposition.json`, SHA256 `8b7cc1a487a7d303d4e27740d9c8f26c349d48ee0168a24fc5bb4a9d634d2c06`. The selected-slot reconciliation receipt is `root-launch/t3_01-root-ledger-reconciliation.json`, SHA256 `d38cd17ee89a5892a5382e3e45ee394ff78c186f0f83978681800c5f65105bd3`.

## Next boundary

All product, test, helper and runner writers are frozen pending actual Astra R349 and ROOT source-only activation. A changed product generation cannot reuse the frozen R346 gate. Any future execution requires an explicit prospective plan, valid budget lineage, a new frozen source gate and individual reservation. No current failure is repaired by rewriting historical evidence.
