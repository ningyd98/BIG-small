# Resource compiler correction 2

Status: preserved candidate snapshot, awaiting final read-only dependency freeze and cold static correction; actual resource acceptance and physical research remain **NOT_RUN**.

The original two-file implementation and 538-file source snapshot remain untouched in `source/`; `fix-round-2-baseline/` preserves that release and its reports. Root's empty-response counterexample and failed frozen-replay setup logs remain unchanged. Complete source/test dependency closure is supplied by this release, rather than importing omitted helpers from a changing live tree.

The original request/response reader now hashes every present response, even a zero-byte file. A genuine empty payload has SHA(empty); an absent payload requires explicit absence, no path/hash, zero received bytes and an unsuccessful status. Stale hashes cannot be hidden by changing received length to0. The exact original four-attempt root counterexample now rejects while retaining its original evidence. Distinct valid empty/absent negative transport cases remain countable in the full failed denominator.

Actual B0 case costs now require exact request-ID wire association. The co-frozen T8 collector binds request and response role/provider/ID through the unchanged cost callback; its independent reader compares complete normative PLANNER/SUPERVISOR request bodies against registered frames and frozen settings, rather than a prompt substring. Other roles, identity swaps, changed provider/context/images and malformed original sources refuse acceptance. No declaration flag, software result or numeric summary grants budget readiness.

The successful-path P99/Tcap rule, full seven-method power/formal accounting, complete fixed G3 set, G4, measured auxiliary source costs, whole-tree storage, unknown billing, explicit ceilings and versioned20% planning reserve are unchanged. Legacy `budget.py` remains byte-identical to SHA `c1b92d2710e55fe73eb6e5099a9ed81bb78f7b71a2ac8a56406d2e9c2008514b`.

Candidate checks: live125 scoped CPU tests6.37s; immutable overlay125 tests6.73s; frozen downstream184 tests39.53s; Ruff and nine-file formatting PASS. Warm-cache live six-source mypy passed, but cold frozen mypy failed on existing read-only `cloud/planning/pipeline.py:487` optional-string inference. The exact failure log is retained and blocks final static release. RED/GREEN and the original root SHA-drift counterexample are retained. The true real-resource check still returns UNAVAILABLE with actual NOT_RUN and physical acceptanceFalse. No successful actual resource receipt or INITIAL was generated.

`fix-round-2-source-hashes.json` SHA256 is `f1242a752502acecbe6d7b9a5714c205a5fbecbebed5490666e11fa7e3329b56`; `fix-round-2-source/` contains767 manifest-bound files, two owned and765 read-only. All test sources/fixtures and exclusion originals are included. `fix-round-2-review-package.diff` compares only owned code with the preserved release. The T8 fix2 overlay is identical. Cold imports and every copied hash were verified; independent review is pending.

Reproduce inside the immutable overlay, using the repository virtualenv binary:

```sh
cd artifacts/research/process/20261004-ced-development/resource-plan-module/fix-round-2-source
PYTHONPATH=src:. /ABSOLUTE_REPOSITORY/.venv/bin/python -m pytest -q tests/test_research_resource_plan.py tests/test_ced_initial_freeze.py tests/test_ced_pilot_stages.py tests/test_research_pilot.py tests/test_research_protocol.py
```

This command is scoped software verification. It does not run a model, renderer or research experiment.
