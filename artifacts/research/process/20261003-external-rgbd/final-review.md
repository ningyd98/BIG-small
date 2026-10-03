# External RGB-D final independent review — initial findings

Date: 2026-10-03. Reviewed the deployment specification/plan, transfer/archive/deployment implementations, CLI, fixed source manifests, prior reader/integration review records, and focused test coverage. This report concerns software behavior only. No real-data acceptance has completed; an ongoing download is not a verified RGB-D deployment. No implementation files were edited and no full test suite was repeated.

## Remaining substantive findings

### F1 — Interrupted bundle assembly cannot resume (P1)

`deployment.py:436–453` calls `extract_archive(parts, bundle, ...)` again before continuing interrupted per-file assembly. Once one file has been renamed out of the completed bundle, archive reuse checks every listed file in the bundle and rejects that now-missing member. The surviving assembled file does not enable recovery.

Focused reproduction used a temporary, clearly synthetic two-member tar: interrupt immediately after the first `source.replace(target)` completes. The next `extract_dataset` call raises `INCOMPLETE: completion marker or published HASH mismatch`. Raw deployment remains unpublished, so it does not produce a false completion, but the documented continuation path is broken.

Required correction: persist the verified assembly inventory before the first move and roll forward from that journal, accepting a member only after checking whether the verified bytes are in the bundle or assembled stage. Do not invoke bundle reuse validation on an intentionally depleted bundle.

### F2 — Authentication refusal becomes a network blockage (P2)

`transfer.py:450–456` maps every HTTP status exception to `NETWORK: HTTPStatusError`. The CLI maps that to `BLOCKED_NETWORK`; there is no `BLOCKED_AUTH` classification for 401/403. An unauthorized/gated source is consequently reported with the wrong recovery condition and retried as a network failure.

Focused MockTransport reproduction of HTTP 403 through the persistent HF transport yielded `NETWORK: HTTPStatusError`. No real credentials, terms, or remote endpoints were used.

Required correction: classify HTTP authorization refusals before sanitizing the error text, preserve credential redaction, and avoid retrying a known authorization refusal as transient network failure.

### F3 — Cancellation waits for active download workers (P1)

`transfer.py:546–554` uses a `ThreadPoolExecutor` context manager. A `KeyboardInterrupt` while consuming `as_completed` enters its implicit `shutdown(wait=True)` before `scripts/rgbd_data.py` can record `INTERRUPTED` and return 130. Running HTTP workers have no cancellation signal. A long transfer can continue for its full remaining duration after cancellation.

Focused reproduction replaced one worker with a 0.6-second synthetic task and injected `KeyboardInterrupt` at `as_completed`; the handler was delayed by 0.609 seconds, equal to worker completion. This does not test live network cancellation, but it directly demonstrates the executor lifecycle.

Required correction: propagate cancellation to active workers and queued futures, check it at bounded points in the HTTP streaming loop/backoff, preserve partial files, and wait only for cooperative worker exit before publishing the interruption state.

### F4 — Standalone validation can label revision-A raw data as revision B (P1)

`deployment.py:189–204` checks only the existence of `raw/<dataset>/COMPLETE.json`. It does not compare its identity with the requested source/revision/selection. Discovery then passes the requested plan revision to the reader. The `extract` command has an identity check, but independently callable `validate`/`index` bypass it.

Focused reproduction created a temporary raw completion marker whose identity revision was A and called `discover` with revision B. A stub reader received B and returned references labeled B. The reproduction isolates the missing orchestrator gate; the normal reader likewise receives its revision argument from this unchecked plan.

Required correction: validate the completed raw deployment identity against the requested plan before discovery and validate index provenance against the plan for independently callable preview/smoke operations. Preserve mismatched data for inspection rather than relabeling it.

### F5 — Discovery quarantine preservation is only a partial closure (P2)

The prior integration finding is improved: `discover` writes `discovery-quarantine.json`, including when all trajectories fail discovery. However, `validate_dataset` still initializes a new frame quarantine and returns only its count. `quality.json` and `deployment.json` therefore omit quarantined source trajectories from their primary failure totals. `run_operation` also counts groups using episode basenames rather than the canonical task/trajectory identity, and deployment scope does not prove that accepted RoboMIND trajectories remain complete after frame quarantine.

Required correction: include distinct source-trajectory and frame quarantine counts/reasons in quality and deployment reports; count canonical accepted trajectory identities; require complete retained trajectories before the minimum ten-trajectory scope claim. Root agent has acknowledged this correction.

## Prior finding closure checked

- Reader R1: `_dataset` now rejects both nonempty `Dataset.external` and `Dataset.is_virtual`, in addition to forbidden HDF5 links.
- Reader R2: a different depth resolution now receives `K_depth=None`, so camera geometry is unavailable.
- Integration fixture smoke claim: smoke checks loaded sample provenance before writing a `real_dataset` report.
- Integration empty RGB: `DatasetSample` rejects empty RGB.
- Integration robot-base gate: it now requires metric optical-Z depth, depth intrinsics, and an explicitly directed camera/depth-camera to robot-base transform.
- Integration episode collision: loader windows now include task and source file; sample/group IDs include task. Deployment acceptance counting is addressed separately by F5 above.

## Other review results and verification limits

The inspected transfer path pins a full HF revision, binds partial files to source/revision/path/size/hash identity, retains partial data, verifies fixed size and upstream SHA256 when available, records local-only hashes honestly, locks the shared budget ledger across processes, and strips authorization before cross-domain redirects. Archive helpers reject traversal/links/special members, test complete multipart archives, check selected expansion/storage, and publish only completed staging directories. The assembly fault is at the orchestration layer above those helpers.

The existing status defaults remain `NOT_VERIFIED`; download completion does not itself set a real verified scope. Smoke fixtures cannot legitimately substitute for actual samples. This review makes no `SMOKE_VERIFIED`, `PILOT_VERIFIED`, or `FULL_VERIFIED` claim.

All reproductions ran via `PYTHONPATH=src .venv-data/bin/python` and used automatically deleted temporary data plus local mocks. They were software fault probes, not source-backed acceptance. The reported 133 passing tests and Ruff/mypy results were supplied by the parent workflow and were not rerun here. Source files were frozen during this review; root/implementation agents are correcting the above findings before the requested focused re-review.

Result at initial review: **CHANGES REQUIRED**. A final closure note should be appended only after focused checks of these exact findings.
