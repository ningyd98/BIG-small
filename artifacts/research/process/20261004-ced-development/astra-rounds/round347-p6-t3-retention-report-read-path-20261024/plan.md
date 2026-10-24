# R347 Existing Retention Report Read Plan

Actual planner: `gpt-6-astra`, `/root/astra_p6_t3_plan`. Scope: ROOT metadata only.

Tool `49efd1` exited1 with FileNotFoundError because the report was guessed at the round root. Finite filename discovery located the existing report at:

`artifacts/research/process/20261004-ced-development/astra-rounds/round345-p6-t3-interrupted-evidence-and-head-20261024/recovery/retention-step-report.md`

Original finding/failure pins are preserved in `plan.json`. This is not a product or retention failure.

After reviewing this plan, ROOT should verify this is the expected regular nonsymlink file, require raw SHA256 `efad3d19f1d8ffbee6bd2aa2d3e6d7ff91537f9c1c5c5cd4ff41b98ffebd5823`, then display those same verified UTF-8 bytes. Record actual path/size/hash and read outcome in a new R347 metadata disposition. A mismatch must be recorded, not repaired by rewriting the report.

Do not create, move or rewrite reports, repeat retention or the failed compound command, reread unrelated successful evidence, or run product/helper/tests. R345 byte verification and R346 planning can continue independently. No runtime budget or prior status changes. Acceptance covers only correct path/hash/read, not report content or product success.
