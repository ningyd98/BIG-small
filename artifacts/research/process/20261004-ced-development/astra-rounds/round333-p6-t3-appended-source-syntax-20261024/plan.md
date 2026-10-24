# R333 appended test indentation correction plan

**Actual Astra:** `/root/astra_p6_t3_plan`, `gpt-6-astra`. **Implementer:** existing `/root/p6_t3_sol`.

ROOT preserved the AST-only `IndentationError` at line 5792 in `root-finding.json` and the exact failing source in `original-test.py` (307367 bytes; SHA256 `41da181694af5ded18124dc6d21ba1b35b97d3c1e854ba6331552185679a86b5`). Actual Sol failure evidence is also retained in `author-failure-evidence.json`, `author-failed-metadata-command.txt` and `author-original-traceback.txt` (chunk `07cf8e`, exit 1). No import, collection or product/test runtime occurred.

The public-control nested `after()` return at line 5785 has four leading spaces instead of sixteen. A source-only in-memory proposal inserting twelve spaces restores that return to `after()` and allows complete-module AST parsing and symbol-table construction. No additional syntax repair is needed. Actual source was not modified by the planner. All immediate input SHA256s are in `plan.json`; `planner-source-readout.json` records this inspection.

## Exact repair

- [ ] ROOT verifies the listed pins and current test equals frozen original. Keep Sol as sole writer.
- [ ] Same Sol inserts exactly **twelve ASCII spaces** at the start of line 5785. Change no other byte, statement, assertion, import or fixture.

```diff
-    return {"public": public, "actual_file_checks": file_checks,
+                return {"public": public, "actual_file_checks": file_checks,
```

- [ ] Sol saves a one-line diff and `implementation/source-proof.json` under R333. ROOT independently reconstructs expected bytes and records acceptance before resuming R331 source review.

## Source-only verification

Use stdlib byte reads, hashes, JSON, `ast.parse` and `symtable.symtable`; do not execute/import the module, run helper functions, collect tests or use `exec`/`runpy`/`importlib`.

1. After bytes equal the original snapshot plus that one twelve-space insertion: **307379 bytes**, SHA256 `45425d854e8f38f2fb3479d9cdd37560aaaed1c48ac5014510070a2eb437325f`.
2. Original **260206-byte prefix** remains byte-identical, SHA256 `dfe6ce74fd0fe2c8f1694b73e74766f0933cb5ad1f67e7a033838c89d9adaf29`.
3. Whole-module AST parsing and symbol-table construction succeed. The line 5785 `Return` is a direct member of nested `after()` inside `test_b_public_confirmed_publication_control`. Do not claim AST equivalence to invalid before syntax.
4. All other bytes, R331 plan, product files, runner and both ledgers are unchanged. RED/GREEN each remain **used 0 / remaining 1 / HELD**. Preserve R333 original failure and source snapshot.

This plan changes only the single indentation defect. R332 helper repair is independently accepted by `root-acceptance-reconciled.json`; that acceptance and its preserved original readout remain separate and untouched. No new agent, runtime allowance, retry/reset, historical edit or product scope is authorized. Acceptance establishes only source syntax correction; T3 behavioral gates remain held. Any new unexpected syntax/scope issue or failure of the exact reconstruction returns to actual Astra before broader repair.
