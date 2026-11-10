# R553 Frozen Evidence Packaging Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for this bounded packaging task. Existing authorization applies; no source repair, extra review or sub-agents.

**Goal:** Deliver frozen diff/failure evidence without modifying its bytes or triggering textual whitespace checks.
**Architecture:** Deterministic gzip archives plus a publication index; original files remain unchanged locally.
**Tech Stack:** Existing Python gzip/hashlib and Git.
**Spec:** R553 request.json and parent clarification to include the failure log; actual planner_model `gpt-6-astra`.

## Failure, scope and evidence

Original `git diff --cached --check` exited2 on line13 of the two R552 unified diff files. Their canonical blank-context lines include a space; stripping it would alter the recorded patch. R553 original-staged-check.log also contains literal offending lines and must be archived rather than staged as text. All four request inputs matched bytes/SHA256. Read-only Git inspection confirmed both diff originals are staged additions; the failure log was not staged.

Package exactly three originals: R552 actual-edit.diff, R552 planner-ruff.diff, R553 original-staged-check.log. Create adjacent `.gz` files, R553 publication-index.json and a short implementation report. Unstage only the two diff originals; leave all three original working files intact. Do not normalize whitespace, edit .gitattributes/Git whitespace settings, change source/runtime/cloud responses, restage directories broadly, or touch already audited unrelated staged content.

## One task

- [ ] Recheck four input hashes and save current staged path/status inventory. Preserve original logs. Confirm the two diff originals remain newly staged additions before changing their index entries.
- [ ] Compress each original independently with existing Python `gzip.GzipFile(fileobj=BytesIO(), filename="", mode="wb", compresslevel=9, mtime=0)`. Write only new adjacent archive paths with exclusive-create semantics. Generate each compressed byte sequence twice in the same environment and require byte equality. Do not place current time or original filename in gzip headers.
- [ ] Require `gzip.decompress(archive_bytes) == original_bytes` for all three files, with identical decompressed length/SHA256. Build publication-index.json listing original relative path/bytes/SHA256, archive relative path/bytes/SHA256, algorithm/mtime/filename policy, and local-original retention. The index explains published archives are lossless containers for original evidence; they are not normalized replacements or a full raw reproduction bundle.
- [ ] Use explicit `git restore --staged -- <R552 actual-edit.diff> <R552 planner-ruff.diff>` only. Recheck local originals' hashes immediately afterward. Stage the three exact `.gz` paths, publication index and intended R553 plan/report files. Never stage any of the three plaintext originals; failure log remains local unstaged. Do not alter other staged files.
- [ ] Run `git diff --cached --check` and require exit0. Review **all** staged paths/status/sizes against existing R550–R552 derived-publication scope plus these named R553 artifacts; retain private raw/cloud bodies, DB/keys/model/SDK exclusions. Confirm only intended index-path replacement/additions occurred, all originals still exist/hash-match, and staged archive blobs themselves decompress to the original hashes (not merely working-copy archives). Record actual counts rather than reuse a stale audited-file total.
- [ ] Write implementation report with original failure, three roundtrip/hash checks, deterministic-generation check, staged-boundary audit and final check exit. Preserve the original failed log; new textual reports summarize it without reproducing trailing-space lines. Commit/push only under existing delivery authorization; packaging does not grant upload permission for private cloud raw.

## Preconditions and acceptance

Existing Python/Git and approved managed-worktree/index access suffice. No install, runtime/GPU/model/cloud call or code tests are needed. Acceptance is three exact-byte roundtrips, deterministic archive bytes, unchanged local originals, intended staged-path boundary and clean staged diff check. Any other staged failure or scope issue requires separate actual Astra planning; do not strip additional evidence opportunistically.

R550 actual result remains unchanged: one additional native load/two generations/one cloud response, actual REQUEST_MORE_OBSERVATION due to freshness, no returned contract or hardware/formal acceptance. Offline content success is not a live PLANNED outcome. R553 adds zero actual calls and changes no budget or experimental result.

## Verified inputs

- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round553-frozen-diff-publication-20261110/original-staged-check.log` — 311 bytes — SHA256 `1297ff39da528c2b0aff28d674d2233b126fb773e90dfb462a4540289bb109be`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round552-r550-observer-import-order-20261110/actual-edit.diff` — 847 bytes — SHA256 `f4429f9e9e6117944264762788f34d4b0ec3bb0e310429d1a95d9bd4161f5b1c`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round552-r550-observer-import-order-20261110/planner-ruff.diff` — 867 bytes — SHA256 `649a8592f918d67a70d8cbcdc6cf10e37ac64e0a7debec0578180344fd18575e`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round550-molmo-sol-live-interface-20261110/delivery-preflight.json` — 413 bytes — SHA256 `f95aaeed7fcf9970c84a442ef653e396a896fd1a5fddb2275ffc94f4aa811f70`
