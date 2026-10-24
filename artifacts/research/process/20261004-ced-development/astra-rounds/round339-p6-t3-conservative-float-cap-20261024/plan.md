# R339 Conservative Float Cap Implementation Plan

> **For agentic workers:** Follow the existing same-author execution workflow after ROOT activation; no new agents or runtime actions. Use the existing execution skill/workflow only within this plan's scope.

**Goal:** Make the new original D_app seconds cap provably no larger than its exact nanosecond cap.

**Architecture:** Retain all owner, thread, clock, hard-bound and positive-value checks. Replace only the floating-point round-trip comparison with an exact integer-ratio comparison.

**Tech Stack:** Existing Python binary64 float, `float.as_integer_ratio()`, `math.nextafter`; standard-library AST/source/hash verification.

**Spec:** `root-finding.json`, the frozen `original-cap-source.txt`, and R331 conservative original-budget contract. Actual planner: `gpt-6-astra`, `/root/astra_p6_t3_plan`. Implementer: existing `/root/p6_t3_sol`, pending ROOT activation.

## Evidence and cause

The frozen `OperationalWindowOwner._remaining_app_seconds` segment has SHA256 `278da2ca8e6d25b1067a8cc0e7fde56ac1eb6c8b7f3ca5f16bbcf8e298e3e999`; the current selected definition matches it. Full input hashes are in `plan.json`; selected source, including unchanged owner checks, is in `source-slices.json`. This is a static semantic finding, not an executed product failure.

For remaining=1, the nearest binary64 seconds value is 4835703278458517 / 2^82. Its numerator times 10^9 exceeds 2^82 by 301175296. Twice that excess is below 10^9, proving the chosen binary64 value is nearest yet above the exact cap. The exact product is less than half an upper ULP above 1 because 301175296 × 2^53 < 2^82, so multiplying back rounds to 1.0. The original condition misses this excess. `exact-integer-proof.json` records this integer certificate; no float probe or product call was run.

## Global constraints and review focus

Only the selected definition may change under R339. Preserve original owner/thread/source checks, original clock read and token, min over original hard deadlines, both positive checks, exceptions and return type. No new origin, clock read, renewal, tolerance, global numeric policy, dependency or test. Positive integer nanoseconds, exact representability, upward and downward rounding, and existing expiration rejection are covered by the mathematical and source proof. Existing finite conversion behavior remains the scope; do not broaden overflow behavior.

RED remains SPENT with original evidence unchanged. GREEN remains UNUSED/HELD. Nine nodes and the 15 worker-poll limit remain unchanged. No product import/call, pytest, collection, numerical trial or additional runtime allowance. Independent R331/R338 changes may continue outside this definition; whole-file hashes are observations, never rollback prerequisites.

## Single task: exact comparison

**Modify:** `src/cloud_edge_robot_arm/vision/operational_windows.py`, `OperationalWindowOwner._remaining_app_seconds` only.

- [ ] ROOT verifies input hashes and the selected live definition against the frozen segment, then activates the same Sol. Target drift requires applicability reconciliation; a new cause or wider scope returns to Astra.
- [ ] Sol replaces the single line `if seconds * 1_000_000_000 > remaining:` with:

```python
        numerator, denominator = seconds.as_integer_ratio()
        if numerator * 1_000_000_000 > remaining * denominator:
```

Keep the existing indented `seconds = nextafter(seconds, 0.0)` and every other line unchanged. Use a surgical edit, not replacement of an old whole-file snapshot.

For a finite positive nearest binary64 value s=p/q, integer cross multiplication exactly detects s > remaining/10^9. If above, its immediate predecessor is at or below the exact value; otherwise it already satisfies the cap. The minimum valid integer remaining is 1, whose predecessor seconds value remains positive. The original rejection still applies.

- [ ] Sol saves immediate before/after segment hashes and exact diff; standard-library AST parses the current source as text and proves the selected successor equals the frozen definition after this single replacement. No importing or executing the product. Compare non-target spans to the immediate edit input, separately attributing concurrent edits; never demand rollback of independent work. Exact expected successor segment SHA is recorded in `plan.json`.
- [ ] ROOT independently repeats source/hash/AST checks, reviews the integer proof and unchanged guards, confirms unchanged runtime budgets, then records narrow static acceptance and passes the successor into later R331 GREEN gate preparation.

## Actual prerequisites and acceptance boundary

Only metadata work is authorized here. All original R331 actor/source/HEAD/resource gates remain required before any future GREEN, including applicable R337 HEAD disposition and relevant correction acceptances. This plan neither releases GREEN nor creates a command slot. No execution result, T3 pass, B final gate, C/native/model/physics acceptance or historical rerun is inferred from this proof.
