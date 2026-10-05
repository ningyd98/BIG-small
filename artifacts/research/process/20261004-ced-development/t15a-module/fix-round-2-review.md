# T15a fix round 2 independent re-review

Verdict: **PASS for the reviewed T15a software scope**. The original two persistence findings and the fix-round-1 provenance-phase bypass are closed. This is not INITIAL/FINAL, real pilot, formal research, provider/credential, or physical acceptance.

Reviewed the explicitly released `fix-round-2-review-package.diff` against preserved `fix-round-2-baseline/` and the current twelve-file source manifest/copies. All twelve working files matched saved copies and registered hashes. Manifest byte SHA256: `b560ef88dda321c8d00e17e3a37657b01c9feea98bcac84d00a22c4a753b1d40`. Base/head remains `ddbeb92a1aa1dfa8039f6260d6b5887c58072383`. Earlier full-scope requirements, passing checks and findings remain documented in `review.md` and `fix-round-1-review.md`; this round changed only the phase/protocol guards and regressions.

Formal binding now comes from the assignment's protocol hash rather than its untrusted provenance label. A bound assignment requires formal provenance and the frozen deadline. An explicitly supplied protocol is always checked by serialization/loading; a bound record cannot disable validation by relabeling itself, and cannot load/persist without its protocol. CLI resume still validates before adding records to completed, detects source/deadline/penalty/schema/phase inconsistency, and preserves original bytes on rejection. Clearing the assignment's binding is rejected by supplied-protocol validation and cannot match the frozen CLI assignment manifest.

Independent constructor reproductions now reject phase demotion, shortened failure penalties and unknown schemas. The newly hashed selection/.001/None payload rejects at loading both with and without a protocol. The scoped CLI regression verifies the same rejected phase payload yields NOT_RUN and leaves every original byte intact. No new blocking counterexample was found in the changed boundary.

Independent validation:

- `.venv/bin/python -m pytest -q tests/test_research_assignments.py tests/test_research_runner.py tests/test_research_power.py`: **55 passed in 29.22s**, exit 0.
- Ruff on the four modified Python files: **All checks passed**, exit 0.
- Direct former bypass outputs included `formal bound assignment cannot change provenance phase`, `unaccepted episode must retain exactly its frozen Tcap penalty`, and `unsupported episode record schema version`.
- The earlier full-scope independent review ran 71 relevant CPU dependency tests successfully; no unrelated broad-suite or live-runtime testing was repeated in this narrow fix round.

Only this review report was written. No network/cloud/model/GPU/render/physics execution, commits or production/test edits were performed. `source_verified` remains structural/file-hash metadata only and `accepted_task_success` remains always False; actual integration and an independent raw-source physics verifier remain required before accepting real research success. Power output and mock replay remain software-only evidence.
