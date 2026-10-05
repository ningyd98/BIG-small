# T18 independent review

Verdict: **REQUEST CHANGES**. Two P2 manifest binding/coverage counterexamples are reproduced against the released nine-file source snapshot. The module consistently keeps research_accepted false and physical/dependency reproduction NOT_RUN; findings concern the claimed integrity/metadata and complete-record boundary, not actual physical acceptance.

## P2 — two coordinated index omissions hide an inventoried failed original

`reproducibility.py:171` compares the index's self-declared assignment list only with its self-declared record mapping. It checks identities inside indexed files, but never detects inventoried episode files omitted from both declarations, nor binds the index to the authoritative frozen assignment manifest during integrity verification.

Frozen reproduction starts with the released `bundle(tmp_path)` fixture containing FAILED a and BLOCKED b, both original files in artifact_hashes. Remove a from `index['assignments']` and `index['records']`, recompute the index file hash and outer manifest content hash, leaving `records/failed.json` present and inventoried. `verify_reproduction_bundle` returns **integrity_valid=true**, assignment_count=record_count=1, no errors. Thus the advertised complete failed/blocked assignment coverage can be changed by editing the same metadata it trusts. The current omission test removes only `records['a']`, so it catches inconsistent lists but misses this consistent subset.

Required correction: when formal run paths are present, compare the index with the authoritative source-bound assignment set/full frozen pool and original run identities; detect source record files in the declared inventory that are excluded from the index. If a generic bundle has no independent expected assignment source, label coverage as unverified rather than asserting full assigned coverage from a self-declared index. Add coordinated list+mapping deletion and orphan inventoried-record regressions. T16's formal full-pool rebuild already protects the analysis stage, but integrity-only verification must accurately expose its own coverage limits.

## P2 — model snapshot metadata may contradict the bound frozen protocol

`reproducibility.py:232` checks manifest.protocol_hash against the loaded FrozenProtocol, but does not compare manifest.model_snapshot_hash with frozen.spec.model_snapshot_hash. The declared model hash is syntax-checked only. A valid byte inventory and consistent analysis can therefore be labeled a matching reproduction while its model identity contradicts the same bound protocol.

Frozen reproduction uses the released full 600-group/seven-method/4200 BLOCKED record fixture. Change only outer manifest.model_snapshot_hash to `f*64`, recompute its content hash; the inventoried protocol still has model_snapshot_hash `a*64`. `rebuild_analysis(..., software_only=True)` succeeds, with integrity_valid=true, numeric_rebuild=SOFTWARE_ONLY and matches_saved_analysis=true. The contradictory hash was never checked. Exact output is in `independent-counterexamples.log`.

Required correction: cross-check model identity with the bound frozen protocol before numeric rebuild; source/dataset/asset/model declarations must clearly distinguish byte integrity of declared inventory from verification of the executing analysis implementation, actual checkpoint availability and complete source provenance. A source aggregate over an arbitrary example.py file is not proof that the imported analysis implementation has been reproduced; dependency/physical replay remain correctly NOT_RUN. Add a rehashed contradictory-model regression and report unverified provenance scopes explicitly rather than implying whole-source/model recreation from declaration hashes.

## Evidence and scope

All three owned files and six released reference copies match their declared SHA256 hashes. Current T16 acceptance.py/metrics.py changed through the approved independent review fix after T18 release, so strict verification used `/tmp/ced-t18-review-7y7eiddw` with all nine frozen files overlaid. `independent-hash-check.json` and `independent-snapshot-root.txt` record this distinction. No production files were edited by this reviewer.

The released **15 CPU tests passed in 6.54s** (`independent-scoped.log`); scoped Ruff passes. Scoped mypy2 traversed an inherited non-owned dependency and reported `cloud/planning/pipeline.py:487` str|None-to-str assignment incompatibility; no T18-owned type error was reported (`independent-mypy.log`). The full software fixture's archived 2400 pool and all4200 failed records rebuild through the same production analysis function; saved metrics/goals match and no physical success is claimed. Path traversal is rejected, JSON/JSONL indexed identities are re-read, stored structured command arguments are not executed, and fresh output preserves existing reports. No full suite, model/GPU/network/physical experiment was run.

The two counterexamples are additional to existing GREEN tests, not failures of those tests. They leave research_accepted false, which is appropriate, but require tightening integrity/coverage/model binding before accepting the T18 software boundary.
