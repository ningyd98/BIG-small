# R355 — exact R354 diagnostic baseline references

Actual planner: `/root/astra_p6_t3_plan`, `gpt-6-astra`. Ready for ROOT review; metadata disposition only.

ROOT recorded a real R354 plan-reference conflict in `original-baseline-finding.json` (source chunk `b87fc6`): owned_scope and source_gate select R350, while inherited capture fields still identify R346 ancestry. No candidate edits or execution preceded the finding. I verified all ten pinned inputs and all four reported fields against the original R354 JSON. The two helper files are byte-identical; the runners are distinct versions.

The sole prospective baseline is:

- Runner: `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round350-p6-t3-successor-lineage-execution-20261024/implementation/run-evidence.py` — 65392 bytes, SHA256 `2ca5fea7e93c2d322bf6081a8b57f381701d27995a8f2e99c377536dffaa7904`.
- Whole helper copy source: `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round350-p6-t3-successor-lineage-execution-20261024/implementation/resource-evidence-helpers.py` — 27181 bytes, SHA256 `bc13daf2a87ff80606c62ed3628e63c1c700ac3000803efa5b20d3c3392cb98b`.

For future R354 adoption only, R355's effective references take precedence over R354 `capture.baseline_runner` and `capture.whole_helper`. R354 `owned_scope.new_runner` and `source_gate.lineage` already mean these R350 sources. The preserved R346 fields are historical ancestry, not another prospective baseline. No arbitrary descendant or alternative runner is authorized.

Do not rewrite R354 plan.md, plan.json, source-readout or intake. After ROOT accepts R355 and explicitly releases the held runner/helper preparation, the same actual `/root/p6_t3_sol` records both plan pins, these effective references and the old references labeled historical in the new R354 adoption metadata. It uses the exact R350 runner for only the changes already allowed by R354 and copies the R350 helper whole, byte-identically. ROOT's new source review/gate/acceptance must pin both plans and the actual new runner/plugin/helper hashes. Historical R348/R350 source acceptance cannot stand in for acceptance of the new runner. Compare unchanged segments against R350, preserving R354's no-pin-cycle and mutable-ledger rules.

ROOT may verify this with inert JSON, SHA/bytes and the already authorized AST/source-diff review; no import, help, probe, test or diagnostic execution is added. Already activated observer-only preparation remains unaffected: its23 targets and limits are unchanged. This disposition does not silently release runner, binding, ledger or gate preparation through that partial observer activation.

There are zero new allowances or runtime/diagnostic commands. R354's one diagnostic remains HELD and requires the existing new source gate and individual reservation; all600/15/240/900-second bounds and algorithms remain unchanged. R350 three SPENT/six HELD and R351 SPENT1/0 remain unchanged. Acceptance resolves references only, not source correctness, behavior, root cause or runtime permission. New pin changes or failures stop affected work for actual Astra.

## Input pins

- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round355-p6-t3-diagnostic-baseline-reference-20261024/root-intake.json` — 3383 bytes; SHA256 `2d1f232c6a8d3f89a93e5c978df4ef28e3648a9677f7e6f7d561c5ae7fc18007`.
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round355-p6-t3-diagnostic-baseline-reference-20261024/original-baseline-finding.json` — 2633 bytes; SHA256 `53017dd726776ed2182c3134eb586a313d35d7e4099ae5fbb1a0e30938924ea0`.
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round354-p6-t3-live-noncompletion-evidence-20261024/plan.json` — 63924 bytes; SHA256 `76e611bde7f12851a59bb8fafbb4b4a91b129ba36af32857b335c908b6fa6784`.
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round354-p6-t3-live-noncompletion-evidence-20261024/plan.md` — 11199 bytes; SHA256 `be86415d34fdb58a54dcbc6293cc359bf6d34cc2713e971142ba5a3a1ba9bad2`.
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round354-p6-t3-live-noncompletion-evidence-20261024/source-readout.json` — 144736 bytes; SHA256 `1a8aa9806e20cd9a2bc0518ee6b0fade3db4e5ba88ce784634c04d0556ef1e73`.
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round354-p6-t3-live-noncompletion-evidence-20261024/root-intake.json` — 32865 bytes; SHA256 `9620583ba5d3ddf79b9698115894304a1b8caff00263ce4f6327485d05deef9c`.
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round346-p6-t3-successor-execution-capture-20261024/implementation/run-evidence.py` — 57557 bytes; SHA256 `264ba312e849a44a93fba942015c539ce2b78568787352685530707eb1b0b9ef`.
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round346-p6-t3-successor-execution-capture-20261024/implementation/resource-evidence-helpers.py` — 27181 bytes; SHA256 `bc13daf2a87ff80606c62ed3628e63c1c700ac3000803efa5b20d3c3392cb98b`.
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round350-p6-t3-successor-lineage-execution-20261024/implementation/run-evidence.py` — 65392 bytes; SHA256 `2ca5fea7e93c2d322bf6081a8b57f381701d27995a8f2e99c377536dffaa7904`.
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round350-p6-t3-successor-lineage-execution-20261024/implementation/resource-evidence-helpers.py` — 27181 bytes; SHA256 `bc13daf2a87ff80606c62ed3628e63c1c700ac3000803efa5b20d3c3392cb98b`.
