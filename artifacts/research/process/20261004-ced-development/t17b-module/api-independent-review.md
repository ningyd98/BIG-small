# T17 API independent software review

Verdict: **REQUEST CHANGES**, one reproducible P2 malformed-source rejection defect. No physical acceptance or source-coverage bypass was identified. Reviewer edited no production or test files.

Reviewed the explicit five-file `api-frozen-source/` release against `api-source-hashes.json`; all five frozen and live files matched. Manifest SHA256: `76ce4348ddb35b24dd1d08d523b06698cf476aefcdf2286d9b40c77fb879f292`. API/router/App integration were inspected; Python evidence/statistics/assignment dependencies were read as context only. The review does not assert a frozen entire dependency tree or actual T16b acceptance.

Independent exact command:

```bash
.venv/bin/python -m pytest -q tests/test_research_results_api.py
```

15 passed in12.69s, exit0, with the existing Starlette anyio BlockingPortal deprecation warning. Scoped Ruff for API/test/app and mypy for the API source passed (existing unused ROS configuration note only).

## P2 — Coherently hash-bound malformed assignment manifest escapes as HTTP500

Location: frozen `cloud/api/research_results.py:233–234`, before `manifest.pop`.

The API validates report/metrics/goals JSON shapes, but does not validate the parsed assignment manifest is a mapping before `.pop`. A producer's malformed `assignments.json` containing valid JSON `null`, accompanied by its correct SHA256 in the report source list, passes the earlier source-byte check. `_load_view` then raises uncaught `AttributeError: 'NoneType' object has no attribute 'pop'`; the public endpoint produces HTTP500 instead of its documented `409 research_artifact_invalid` rejection. This occurs both without a cache and after a previously complete cached view; no ordinary query/body injection or path selection is needed.

Independent minimal reproduction uses the existing 4200-assignment software fixture:

1. Replace only the registered `runs/assignments.json` bytes with `null\n`.
2. Replace report.source_hashes.assignments with SHA256 of those exact new bytes.
3. GET `/api/v1/research/runs/run-1/evidence`.

The TestClient default raises the uncaught AttributeError; with `raise_server_exceptions=False` the response is500. Existing malformed-shape regressions cover report/metrics/goals only; the assignment-null failure is not caught by the current exception tuple.

Requested fix: validate assignment manifest/container shapes before mutation/indexing and return409 for invalid source schemas. Add a regression using a coherently updated source hash, including a warm-cache request. Check analogous pool/source-table shapes without hiding unrelated programming exceptions behind a blanket catch. Preserve the current default actual NOT_RUN and zero physical acceptance.

## Confirmed independent probes

- Complete view retains4200 original BLOCKED/unaccepted records and600 paired groups. Export JSON equals the entire evidence view, including failures, protocol and software/actual status.
- Warm-cache mutations of each of the seven actual source files (protocol, assignments, records, pools, report, metrics, goals) are rejected409 rather than returning cached completion. All original bytes were restored afterward.
- Changing the registration to missing relative source paths returns explicit missing-source NOT_RUN with assigned_denominator=None; restoring the original registration returns the original complete view. Missing sources do not retain cached completion.
- Omitting the last failed assignment and record, rehashing the assignment manifest and updating both report source hashes still returns409 because the full frozen ordered assignment list is rebuilt. A self-consistent smaller summary cannot delete failed coverage.
- Existing auth/unknown ID/traversal/query/body tests pass. Server-owned relative paths reject traversal and symlinks; only GET routes exist. API cache returns deep copies and binds the actual seven file hashes plus registration configuration.
- `EpisodeRecord.accepted_task_success` is independently closed; declared typed completion/VALID/provenance fields cannot accept physical results. The API uses literal actual_status=NOT_RUN/formal_accepted=false/physical_success=0 and labels SOFTWARE_ONLY diagnostics separately. Candidate/accepted/start and risk/round-count sources remain explicitly missing rather than fabricated.

The independent runnable probe is archived as `api-independent-probes.py`, with actual output in `api-independent-probes.log`. It creates only a temporary CPU software fixture and does not dispatch hardware or model/network requests. Implementer/root were notified; a corrected immutable API release will be reviewed separately.
