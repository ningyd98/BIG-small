# R131 Pure metadata test-repair report recovery

Actual planner: gpt-6-astra /root/astra_status_plan. Status: pending ROOT activation. Sole author: /root/p6_stage_a_sol replacement GPT-6.1-sol. Planning is read-only text/JSON/hash inspection plus this plan; no product/test/AST/static/Git execution.

## Original failure and independent root-cause confirmation

Author's tool e48b42 exited1 with AssertionError at line10. Full returned combined output, exact command, finding and source index remain at:

`/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round129-p6-root-read-and-test-draft-review-20261011/implementation/stopped-report-count/`

Failure pins: finding e744b970d8b65dded050d8184086dde280e00672fdfaaeff2d539c9ccf500b48; source-index 3b1189a2cb0e919c71f610d7a7b91419fd35deea96637352e4aa7f75a542495c; command bc3c4b6478396337bd7e12f44a9a2106c2228cf13b256cb0a814ee4408adeb17; combined output52fdfed770456fa53fd719f3072fbc2826bf9b2137069aefbf38a40d9beff342. Separate original stdout/stderr were unavailable; preserve that limit.

The script selected R129 input paths by simulation_runtime/ prefix. Independent JSON inspection finds six exact matches: the five R127 owned production files plus protected state_machine.py. `assert len(production)==5` therefore fails. State-machine bytes did not drift; the selection criterion was wrong. This is report-metadata filtering, not pytest/product failure. The script already performed authorized test replacements and wrote after-test.py/limited-change.diff before its failing assertion, so it must never be replayed as a recovery command.

Current test is59070 bytes, SHA4a29c6792d0f4226d76f77572dbe63ee4b8d8be96936571739d3dd2b5e321908, equal to current-test.py and after-test.py. Before-test SHA2892f38005afd73126b64e7f7ca8ae0589ec47da99081a1ccf52b73742444b3c; diff SHA2e3c86307e93befa5bc60011f57d4b8104343c1c6ee92b05c6de10bdf4a96d7b. Indexed six original files and the five current production files/protected state-machine all matched. Target report is absent. Author and ROOT ledgers show R127 five commands0/1, inherited last3 remain0/1, final gateHELD. No product validation was consumed.

ROOT subsequently reported a distinct state-recording KeyError (tool51ef36). Its full originals were not yet provided for this plan. That issue is explicitly excluded and awaits a separate actual Astra plan; R131 does not write active-t12-state.json or fix the state shape. Report recovery is independent of it.

## Exact recovery scope

Create a new stdlib-only metadata generator at:

`/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round131-p6-test-report-count-recovery-20261011/implementation/generate-report.py`

It may read pinned plans/ledgers/before/after/diff/current bytes. It must not import or execute product/test code, AST/compile/collect, change a test/source/config, regenerate/overwrite snapshots/diff, or call the old failed script. All product/test paths are read-only.

Select the exact ordered set from R127 plan.json scope.owned_paths minus the single exact string `tests/test_operational_runtime_closure.py`; require uniqueness and equality to these five names, not any prefix:

- `/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py`
- `/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/simulation_runtime/repository.py`
- `/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py`
- `/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/simulation_runtime/worker.py`
- `/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/simulation_runtime/recovery.py`

Match each selected path against its exact R129 input record and verify original SHA/bytes. Check state_machine.py separately as protected, not production. No broad prefix, suffix guessing or deduplication that hides duplicates. All paths are complete absolute paths in handoff and output receipts.

Generate only this previously absent report:

`/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round129-p6-root-read-and-test-draft-review-20261011/test-draft-repair.json`

Complete validation and JSON serialization in memory before exclusive-create write (`open(...,'x')`). If target exists, do not truncate/replace/append; stop and preserve the condition. No other product or historical-evidence write is allowed. New invocation/stdout/stderr/exit receipts go under R131/implementation/report-generation only.

## Report content and honest evidence labels

The generated report includes:

- Original e48b42 failure path/hash/capture limitation and R131 recovery reference; actual author identity; pinned R127/R129 plan hashes.
- Existing before/after/current-test/diff absolute paths, SHA/bytes, equality of current to after, and the unchanged five production list; protected state_machine in a separate field. Verify saved diff against an in-memory difflib rendering with the same before/after labels; never rewrite it. No assertion that source edits were absent: R129 test-only edits have already occurred.
- D1–D4 source-only repair descriptions, limited changed-function/line references, known actual interfaces and resource cleanup notes, all explicitly pending ROOT diff/text review. No claims of runtime correctness from this report.
- Expected original20 plus new19 manifest from frozen R127, unchanged exactRED23 argv, textual before/after test names and parameter-ID/decorator review. Distinguish expected manifest/source review from actual collection; no pytest or AST is used to derive it. If text review cannot establish exact IDs, report the discrepancy and stop rather than blindly stamp39.
- Author/ROOT command counters and four held gates, original consumption history unchanged, no new validation/product edits by recovery.
- A finite source-only worker lifecycle tally with per-node/helper reasoning. Current author's proposed upper bounds are RED23=26 polls, newGREEN19=22 polls, originalGREEN20=20 polls: mismatch2 nodes each have2 fresh polls; nested_foreign_job has one additional actual second poll; binding subcases reuse one poll. These are source-derived estimates, not measured runs. Verify the finite call/loop map textually and list legacy acquire/start-only fixture activity separately so the meaning of poll versus other resource lifecycle is explicit; require the full applicable R127 lifecycle bound ≤64. If that cannot be substantiated from source, stop report generation without consuming validation or changing tests.
- No software/actual/formal acceptance; ROOT must review corrected draft/report/diff before resuming R127 test-first RED, and later final gates remain held.

## Single-use metadata execution and verification

After ROOT rechecks pins and activates, author writes the new metadata-only script and submits its text/hash for ROOT's finite read check. ROOT confirms no source/test writes, execution imports, hidden subprocess/probes or broad selection, and only allowed output paths. Then one generator process is allowed:

`/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round131-p6-test-report-count-recovery-20261011/implementation/generate-report.py`

cwd `/home/ningyd/文档/ChatGPT/BIGsmall`; env PYTHONDONTWRITEBYTECODE=1. This is one new metadata allowance, not product budget. Before invocation create the empty receipt directory only if its raw output files do not already exist. Capture actual generator stdout and stderr separately by runner stream capture or direct shell redirection, record exact argv/cwd/env/exit/timestamps and script SHA. Do not reconstruct streams from the old combined output. Only expected exit0 and valid report completes this recovery. On any failure preserve originals, stop and return to actual Astra; no retry/self-repair or budget reset.

After the generator exits, ROOT may do stdlib/text/hash-only report validation: output parses, pins/counts/argv/holds match, full test and five production bytes unchanged from the R131 input snapshot, all six preserved old evidence files unchanged, old target was absent and only new report/receipts were created. No product validation is authorized by this check.

Permitted ROOT new files, all under `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round131-p6-test-report-count-recovery-20261011/`: input-check.json, root-activation.json, executor-brief.md, dispatch.json, ledger.md/json, script-review.json, validation.json, step-report.md/json, phase-summary.md, and implementation generator/receipts. ROOT may append the outcome to the established phase summary. No active-state mutation under this plan. Preserve R127/R129/R130 plans, all failure originals and existing before/after/diff bytes.

## Acceptance and continuation

Accept R131 only as a correct, singly generated report with preserved history and unchanged source/budget state. ROOT then completes R129's report+diff textual review and explicitly resumes the same author's original R127 test-first sequence when satisfied. RED23 remains0/1 until that separate resume; R113 format_check/mypy/GREEN and R127 newGREEN remain held. No new pytest/static/AST/import/compile/GPU/model/Git/native/actual authority. Stage A remains LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO pending genuine validation and independent review; B/C/D and formal research acceptance remain unchanged.
