# R332 selected-helper dependency correction plan

**Actual Astra:** `/root/astra_p6_t3_plan`, `gpt-6-astra`. **Implementer:** existing `/root/p6_t3_sol` only. **Purpose:** repair one static helper-selection omission before any R331 runtime launch.

ROOT's preserved `root-finding.json` reports `_t2_index` calling `sha(path)` at line 372 of the selected helper, with no definition/import of `sha`. `original-helper.py` is byte-identical to that reviewed helper. No helper/product/test import or runtime occurred; both R331 test slots remain unused.

`plan.json.inputs` pins the immediate files with actual SHA256. `planner-closure-readout.json` records source-only AST/symbol-table inspection of all 16 selected functions: the only unresolved module-global name is `sha`, referenced by `_t2_index`. The inherited implementation depends on `hashlib` and `stable_bytes`, both already present. This is a function-selection omission, not an observed product/runtime failure.

## Minimal repair

- [ ] ROOT verifies listed pins, preserved snapshot and unused R331 ledger state. Independent append-only T3 test preparation may continue.
- [ ] Existing Sol inserts this exact function from pinned R319 between `stable_bytes` and `checked` in R331 `implementation/resource-evidence-helpers.py`:

```python
def sha(path):
    return hashlib.sha256(stable_bytes(path)).hexdigest()
```

- [ ] Sol adds exactly one `sha` entry to R331 `implementation/inherited-functions.json`, with inherited source file/lines and matching source/local segment SHA using its existing convention. Preserve every existing entry and declared adaptation.
- [ ] Save minimal diff, before/after pins and source-only proof under R332 `implementation/`. ROOT independently reviews them and records R332 acceptance; the ordinary R331 source gate then binds new helper/provenance hashes.

Only those two R331 preparation files may change. Preserve runner, plan, ledgers, original snapshot, existing helper function/import/constant bytes, resource limits, product/test files and historical artifacts. No new dependency, agent or runtime allowance.

## Verification without execution

Use only stdlib source reads, `ast`, `symtable`, `hashlib`, `json` and byte comparisons. Do not import/run the helper, use `exec`/`runpy`/`importlib`, call helper functions, collect tests or import product/tests.

- Exactly one added top-level definition, `sha`; its source and AST equal the pinned inherited function.
- Removing the inserted block/separators reconstructs `original-helper.py` byte-for-byte; every existing function and other statement is unchanged.
- Recursively inspect symbol-table global references in all selected functions/nested scopes, accounting for module definitions/imports and builtins. The unresolved set must be empty; record the actual name/binding map.
- Existing provenance remains identical; only the exact `sha` entry is added, with matching source/local hash.
- Runner, plan, snapshot and ledgers retain their original SHA/state; R331 RED/GREEN remain unused.

Write this evidence to `implementation/source-proof.json` with actual after pins. This static defect needs no separate runtime check: existing R331 runtime gates remain held until their normal ROOT approval.

## Boundary

Acceptance means only that finite helper dependency selection and provenance are corrected. It does not mean T3 behavior passed or B is complete. Do not reopen the 255-input historical audit. New unrelated omissions, unexpected proof failures, behavior changes or broader scope require actual Astra before repair. Preserve all original evidence.
