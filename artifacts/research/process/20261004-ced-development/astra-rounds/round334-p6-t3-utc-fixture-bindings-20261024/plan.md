# R334 UTC fixture target correction plan

**Actual Astra:** `/root/astra_p6_t3_plan`, `gpt-6-astra`. **Implementer:** existing `/root/p6_t3_sol` only.

`root-finding.json` and `original-utc-helper.py` preserve the static defect: `_b_t3_utc` requires every listed module to expose `datetime`, but `vision.operational_windows` has no such binding. No runtime failure was executed. Current whole-test source is the exact R333 corrected generation: SHA256 `45425d854e8f38f2fb3479d9cdd37560aaaed1c48ac5014510070a2eb437325f`.

Finite AST inspection of all seventeen actual target files confirms that only `vision.operational_windows` lacks the module-level binding; the other sixteen directly import `datetime`. All targets are unique and resolve to existing source files. `plan.json.inputs` pins the sources; `planner-binding-readout.json` records actual import lines. This inspection is not a claim that runtime UTC injection already works.

## Minimal change

- [ ] ROOT verifies listed current pins, frozen helper and unused R331 ledgers. Keep independent R333 acceptance separate.
- [ ] Same Sol removes only the **30-byte substring** `, "vision.operational_windows"` from the `names` tuple inside `_b_t3_utc`:

```diff
-    names = ("vision.worker_runtime", "vision.worker_owner", "vision.operational_windows",
+    names = ("vision.worker_runtime", "vision.worker_owner",
```

- [ ] Keep all other test bytes and sixteen target names/order unchanged. Do not replace the `hasattr` assertion with a silent skip, add `raising=False`, change `ShiftedDateTime`, weaken any boundary assertion, or add a UTC clock binding to product code.
- [ ] Save minimal diff and `implementation/source-proof.json` under R334. ROOT independently reviews and records acceptance, then resumes the usual R331 source gate.

## Source-only proof

Use stdlib byte/hash/JSON/AST/symbol-table operations only; no imports, helper execution, collection or product/test runtime.

1. After bytes equal the pinned current whole test minus that one substring: **307349 bytes**, SHA256 `083bd235d54cb3961ec40a52d6eb997275a4cda3c9075297b4ffea95114dcb45`.
2. Module AST and symbol table parse; the tuple is exactly original seventeen minus the absent-binding module, with sixteen unique targets in the same order.
3. Source AST records actual `datetime` imports for all retained targets. Product source hashes remain unchanged.
4. Original **260206-byte prefix** remains identical, SHA256 `dfe6ce74fd0fe2c8f1694b73e74766f0933cb5ad1f67e7a033838c89d9adaf29`. Every other appended byte—including R333's fixed indentation, local +/-1-day and exact-D checks, external UTC boundaries and injection guards—remains unchanged.
5. R331 plan/runner/ledgers and historical evidence stay unchanged. RED and GREEN both remain **used 0 / remaining 1 / HELD**.

This accepts only the invalid target-list correction. It grants no new/reset runtime allowance, product modification, agent spawn, T3 behavior pass or B acceptance. Any broader target/source defect or failure of exact reconstruction returns to actual Astra before repair. Do not re-audit historical rounds.
