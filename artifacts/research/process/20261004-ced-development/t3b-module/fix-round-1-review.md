# T3b fix round 1 independent review

Date: 2026-10-04. Reviewed `fix-round-1.diff`, original `review.md`, appended `report.md`, current six-file source manifest, and the narrowly authorized planner constructor/`_post` byte hook. All six current SHA-256 values match `source-manifest-fix-round-1.json`.

**Verdict: REQUEST CHANGES.** The original P1 full-binding gap and P2 reserialized-wire-evidence gap are resolved in the submitted implementation. A newly reproduced credential-echo bug remains blocking before real keys are used.

## Resolved findings and verified boundaries

- Full binding: `validate_role_probe_bindings` now reconstructs the bundle/edge identity, rehashes current cloud/edge/device/config sources, compares original request hash, and checks each wire-boundary/final effective request setting. Expected bodies use the bound settings. No successful software fixture is accepted by the nominal gate.
- Wire evidence: request/response `.raw` bodies preserve exact bytes and hashes; parsed `.json` files have separate hash names. The existing `_post` supplies bounded responses before JSON decoding, including non-JSON and HTTP error bodies. Acceptance checks raw hashes, counts, and production summaries.
- Observer accounting: request observer failure precedes transport and sent-cost creation; response observer failure retains one ERROR attempt and received-byte count. Exceptions are sanitized; no retry/fallback or header/key argument was added. The hook changes are confined to the authorized constructor/transport surface.
- Scoped independent command: `.venv/bin/python -m pytest -q tests/test_rgbd_role_models.py -k 'raw_observer or credential_echo or current_edge_and_device or unchanged_role_bindings'` — **7 passed, 39 deselected, 0.24s**. External HTTP is replaced by in-memory boundaries; no socket, renderer, GPU, or real credential was used.

## P1 — alternate JSON escaping bypasses credential withholding and writes the decoded key

Location: `scripts/probe_rgbd_roles.py:481-493`.

The suppression check searches only the literal credential bytes and the exact encoding produced by `json.dumps(secret)`. JSON allows equivalent alternative encodings. A response containing the test credential with its first character written as `\u0063` contains neither searched pattern. The subsequent `json.loads` decodes it, and `_write(response.json, parsed)` persists the complete plaintext credential.

An isolated CPU review probe used an in-memory mocked HTTP body `{"error":"\\u0063redential-marker"}` with the synthetic key `credential-marker`, the existing observation fixture, and `_attempt`. It produced `status=COMPLETE`, `wire_artifact_suppressed=false`, and `parsed_credential_echo_written=true`. Artifacts are under `/tmp/ced-t3b-review-hkvhigv4`; they are deliberately malformed software evidence and never an acceptance probe or freeze. The existing literal-echo regression passed but does not cover this encoding.

Decode/inspect JSON strings recursively before writing either raw or parsed convenience artifacts, and suppress the entire body plus any derived parsed/evidence fields when any decoded value/key contains the configured credential. Retain only bounded byte count/hash and a suppression marker; propagate BLOCKED. Cover Unicode escapes, escaped solidus/other valid equivalent JSON escapes, nested values, and HTTP-error bodies. Do not redact and label the result exact raw evidence.

## Scope still unverified

No real nominal S01, provider registry/date-ID availability, missing-target/distractor reliability, edge acceptance, physical outcome, or full T3b acceptance was established. Typed planner/execution/frozen-loader and cancellation/zero-dispatch integration remain root-owned. No full project suite, GPU, renderer, or network execution ran in this review. Only this review file was added; production/test code was not edited.
