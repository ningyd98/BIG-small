# V4 terminal sparse pilot offline result

**PASS in sparse diagnostic scope.** One post-terminal reader verified and strictly decoded every predeclared frame: **201/201 OBSERVED**, zero UNKNOWN, raw failure or decoder exception. The fixed old selection contained 189 UNKNOWN and 12 OBSERVED; paired step results are **189 UNKNOWN→OBSERVED and 12 OBSERVED→OBSERVED**. No selected step was dropped or migrated.

The unchanged detector uses genuine saved RGB-D, ID 7 and the frozen **75 mm / local X 160 mm** asset registration. No truth enters detection. New measured minimum tag sides range **27.0–30.016662 px**, median **28.0 px**. The pilot evaluates the combined size/offset variant; their individual contributions remain unresolved.

The reader reconciled **4807 callbacks (0..4806), 201 allocated/saved captures, zero failed captures, 10366 complete operation pairs, 743 commands and the original 120 settling steps / 9 actions / 2 dwells**. Every selected capture has full 37-qpos/33-qvel/0-act/9-ctrl evidence bound to the support-aware guard byte domain; all protected components and nested monotonic brackets match. All **4807 physical scorer samples** independently reconstruct from source observations.

New versus old records, excluding only episode_id, have zero differences across **4807 physical states, 4806 actuator states, 743 commands and 4807 scorer samples**. This comparison covers every recorded field, not all internal state. Old full qpos remains unavailable; no old pose was substituted. All 34 necessary live/archive source pins and 21 environment pins match. All **223 new raw files** are included in the before/after immutable inventory; all **266 inventoried inputs** stayed byte-identical.

The one GNU-time reader run exited 0: **41.75 s wall time, 2,389,828 KiB peak RSS (~2.28 GiB)**. Acquisition script wall time is separately **49.518431729 s**. Selected frames total **16,790,554 compressed bytes / 421,564,947 original JSON bytes**. This offline work made **201 detector calls and zero model/reset/physics/renderer/provider/hardware calls**. Recorded camera calls sum to 213 (1 setup + 1 bootstrap + 10 boundaries + 201 extra); no render total was measured here.

CPU checks: qualified missing-behavior RED 17 cases → **17 PASS (0.25 s)**; an actual-format preflight mismatch was retained as RED before correcting only this new reader. Ruff and compile pass. Evidence: `offline-verification.json`, all 201 `offline-markers.jsonl` rows, `reader-resource.log`, `offline-source-pins.json`, before/after input inventories and bounded CPU/static logs.

**The derived sparse maximum gap is 2.1166666836000267 s, exceeding the original 0.005 s requirement. Continuous visibility remains NOT_ESTABLISHED; native/source authority, future stability and independent calibration-group admission remain unavailable.** This result supports a separately frozen full-horizon v4 collection. Existing external UTC/hardware limitations remain those in the R01 terminal report; this pilot does not resolve them.

Exact one-run command (already completed; do not retry):

```sh
/usr/bin/time -v -o artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-preparation/fix-round-1/offline/reader-resource.log env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-preparation/fix-round-1/offline/verify_sparse.py --decode-once > artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-preparation/fix-round-1/offline/reader.log 2>&1
```

Working directory: repository root. All output is in this new offline directory.
