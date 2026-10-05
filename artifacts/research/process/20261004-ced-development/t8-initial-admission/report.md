# INITIAL source admission auditor — frozen software handoff

Date: 2026-10-04. Implementer scoped software checks pass. **The final T8/resource dependency independent review is PASS for software scope; this auditor independent review is PENDING. Actual billing remains UNAVAILABLE.** No genuine INITIAL source, method, selection or execution is admitted by this report.

Root authorized two new files: `src/cloud_edge_robot_arm/research/admission.py` and `tests/test_research_admission.py`. All other 766 files in `source/` are immutable references copied byte-for-byte from the explicitly released final T8/resource fix3 closure. Its manifest and this package's `source-hashes.json` are identical, SHA256 `db5ab161b94d4ee1c49b3f527cd4203b99475781d6cd2023148600f60bee2b22`. `ownership.json` distinguishes these two owned files from references. Every 768 hash and Python AST parse was checked, and the two owned live files match their frozen copies. Earlier fix1 evidence/logs remain historical; that dependency was REQUEST CHANGES and does not establish final acceptance.

## Behavior and typed boundary

`InitialSourceRegistration` freezes the owner's exact evidence root, exact `protocol.json` path, current `RoleRuntimeBinding`, and collector source inventory. Registrations use opaque allowlisted IDs. `InitialSourceAdmissionAuditor.audit(id, scope="INITIAL_SOURCE")` has no caller-supplied verifier, VALID callback, receipt or accepted flag. It writes no source evidence and keeps no admission cache.

Each audit inventories every regular raw file, including unconsumed FAILED/BLOCKED files, rejects symlinked roots/ancestors/nested files and source path escapes, hashes current collector and cloud/edge/device sources, loads the canonical v2 INITIAL protocol, calls the real `initial_spec_from_evidence`, and compares every reconstructed spec field plus role/model bundle identity. Before/after inventories and current source bytes must agree. Missing evidence gives UNKNOWN; malformed, drifted or inconsistent evidence gives INVALID. A rejected current-source audit retains the observed source digests. Hashes bind bytes and do not establish acceptance independently of reconstruction.

`ResearchAdmissionResult` contains detached immutable raw/current-source maps, inventory hash, protocol/role hash, reasons and separate source status. `method_admitted` and `execution_admitted` are always false and constructor enforcement rejects attempts to forge either true. A full genuine reconstruction could return VALID for INITIAL_SOURCE only. METHOD always returns UNKNOWN and records `method_risk_source_verifier_unavailable`, `method_weight_selection_verifier_unavailable`, and `execution_owner_registration_unavailable`, preserving the INITIAL outcome. The registered role identity is the owner's source binding; this auditor does not certify a fresh running provider, current plan, checkpoint, mode or physical owner snapshot.

## TDD and verification

The source did not exist before this bounded task (`baseline.json`). `red.log` records the qualified missing-module RED. Initial implementation passed 19 cases. Two additional intended RED cases for forged result admission flags are in `result-guard-red.log`; one intended RED for preserving observed source drift is in `source-digest-red.log`. Their GREEN regressions are retained. There are now 31 own tests covering registration, all symlink/path boundaries, malformed/rehashed protocols and summary metadata, missing/raw-omitted evidence, full comparison, source drift and races detected during audit, immutable aliases, complete failed-file inventory, and distinct closed METHOD scope.

Final verification used only the immutable full closure in `/tmp/initial-admission-final-independent-tylubn2u`, with no live imports from a moving `src` tree:

```sh
PYTHONPATH=src:. /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest -q tests/test_research_admission.py tests/test_research_resource_plan.py tests/test_ced_initial_freeze.py tests/test_ced_pilot_stages.py tests/test_research_pilot.py tests/test_research_protocol.py
/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m ruff check src/cloud_edge_robot_arm/research/admission.py tests/test_research_admission.py
/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m mypy --follow-imports=silent --no-incremental src/cloud_edge_robot_arm/research/admission.py
```

Results: **160 passed in 9.22s**, scoped Ruff two files passed, native mypy one source passed. Logs: `final-related-green.log`, `final-ruff.log`, `final-mypy.log`. Mypy has only the existing unused optional module configuration note. The related 129 reconstruction/resource cases are software checks. Root separately reported an independent final dependency software PASS: frozen129 CPU8.91s, downstream184 CPU40.66s, scoped Ruff/format9, cold mypy6 and all768 post-test hashes. That prerequisite verdict does not supply actual billing or INITIAL admission.

## Limits and review focus

There is no complete genuine INITIAL evidence locally. No public audit synthetic positive fixture grants actual source acceptance. A private pure field-comparison test exercises all-field/role comparisons but confirms the ordinary public missing-evidence path remains UNKNOWN. Metadata claiming REAL_RUNTIME/VALID/accepted cannot replace original raw evidence. The final resource compiler explicitly cannot verify remote billing from numeric caller fee rows; no independently joined billing source is available, so actual INITIAL remains NOT_RUN.

This module performs read-only repeated source snapshots, not an atomic filesystem transaction or persistent method budget transaction. Before/after checks detect observed changes; it does not claim immunity to adversarial change-and-restore between reads. The owner registration must itself be maintained by its authoritative source owner. Source changes, including the separately developed pose marker pipeline, require fresh evidence/bindings and cannot inherit admission from old hashes.

Actual risk provenance, finite candidate/weight selection, current execution-owner registration and native geometry/motion certificates remain separate unavailable prerequisites. The previously reviewed runtime composition adapter and existing sole SkillExecutor/native/Safety submission paths were not changed. No HTTP/model/capture/GPU/robot operation, actual INITIAL freeze, policy enablement, dispatch or physical success was produced. This is a bounded software source-auditing component, not completion of the research execution core.

Independent review should verify the exact frozen closure; challenge registration replacement and symlink escapes; rehash summaries/protocols or omit raw records; drift current source bytes; mutate caller/result nested data; and confirm no INITIAL-only status enables METHOD or EXECUTION. `review-package.diff` contains only the two new owned files. Root independently accepted the prerequisite software snapshot and coordinates this auditor review before an auditor acceptance claim.
