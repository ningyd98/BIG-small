# R01 v4 range fix round 1

Status: **software fix verified and frozen for independent targeted re-review; actual calls 0**. Neither initial nor new `pilot-protocol/attempt-1` exists. Original REQUEST_FIX, report/owned pins/selection, initial protocol header/manifest/index and all its source archives remain unchanged.

Qualified `R01-V4-RANGE-01` was replayed from the independent log's last exact script without editing its bytes: initial exit1 retained a healthy4806 COMPLETE and incorrectly COMPLETE4807. The same script now exits0: healthy4806 remains COMPLETE with4807 callbacks/201 saved; extra4807 is INCOMPLETE with all4808 callbacks/201 saved and its last non-selected callback retained. The probe uses the unchanged initial header as a CPU fixture; that header's disabled gate is refused by the actual execution preflight. A separate short4805 regression retains4806 callbacks/200 saved and missing selected4806, reporting INCOMPLETE/RECIPE_DEVIATION.

The minimal runner change injects the frozen original4806 horizon into the actual sparse-recorder factory. `finish()` requires that exact horizon in addition to all existing continuity, identity, failure and selected-frame conditions; it records actual terminal step/time, expected horizon and explicit RECIPE_DEVIATION reason without cropping, migrating IDs, dropping failures or retrying. New header freezes `expected_physics_steps=4806` and `expected_physics_steps_is_admission_gate=true`. Execution entry and the first source-preflight operation reject a disabled gate, changed range or bool range before any backend/model or runtime loading. The only accepted actual protocol directory is the new `fix-round-1/pilot-protocol`.

Teacher/controller/guard/camera/decoder, v4 XML/registration and all201 IDs are unchanged. prepare.py received only formatter changes: its AST is identical to the detached original. Original live prepare/runner/tests were copied and hashed in `source-before/` before edits. All18 baseline records were checked: only the3 authorized live files changed; original reports, independent review3 files, selection/asset and the6 initial protocol/archive files match exactly. All201 original frame and9 input pins match. Native/source authority, continuous visibility, UTC/calibration/groups and future bounds remain unpromoted.

Final validation: **40 owned CPU tests passed in0.60s** (the original34 collection plus6 bounded range/policy cases), Ruff PASS, formatter-check PASS, and3 owned sources compiled in memory. Exact original RED→GREEN and healthy control remain saved separately, not counted as another test suite. Necessary closure is34 sources/434153bytes,32 reused archives and2 small new source copies;21 environment pins match. Source/header/manifest/index are quiet. `owned-pins.json`, `preservation.json` and `final-verification.log` give exact pins and checked scope; no Git or actual engine/provider/hardware action was performed.

New root command after independent re-review, from `/home/ningyd/文档/ChatGPT/BIGsmall` (preparation already frozen; do not repeat it):

```bash
MUJOCO_GL=egl PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python \
  artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-preparation/run_sparse_once.py \
  --execute-once --protocol-directory \
  artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-preparation/fix-round-1/pilot-protocol
```

No actual command was executed. The sparse pilot still cannot prove full-horizon visibility or satisfy the original0.005s marker-observability gap; it is one fresh excluded development-component experiment.
