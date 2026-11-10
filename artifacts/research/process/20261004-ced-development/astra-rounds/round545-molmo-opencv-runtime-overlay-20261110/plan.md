# Molmo/OpenCV Runtime Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Existing user authorization covers this bounded runtime repair; no architecture approval is needed.

**Goal:** Launch the existing grounded diagnostic with installed OpenCV/app dependencies while retaining the validated Molmo Torch/Transformers runtime unchanged.

**Architecture:** A separate round-local launcher appends the existing app site-packages to the runtime's existing search order, verifies exact imports, then delegates to the unchanged CLI with runpy. No new environment, installation or package copying is needed.

**Tech Stack:** Existing Python 3.12 Molmo r505 interpreter; Torch 2.6.0+cu124, Transformers 4.57.1, NumPy 2.5.3, OpenCV 4.14.0.

**Spec:** R545 `request.json`; R542 integration plan remains in force. CLI is independently under R544 review and is not edited here.

## Global Constraints

- Actual planner_model `gpt-6-astra`; round `round545-molmo-opencv-runtime-overlay-20261110`; five request input hashes verified before planning and again before saving.
- No writes to existing runtime, .pth files, model assets, SDK, application modules or `scripts/probe_molmo_grounded_planner.py`. No network, installer, dependency replacement, CUDA initialization or model construction for R545 verification.
- Create only `implementation/launch_molmo_grounded.py` plus scoped tests/logs/reports under this round. Preserve original failure and planner preflight bytes.
- Set `PYTHONDONTWRITEBYTECODE=1`, run Python `-B`, and set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` for preflight/launcher execution. Existing runtime search paths must precede appended app site-packages.
- Existing R542 smoke budget remains at most one load start/eight generation starts, currently unspent; this repair consumes zero. No paid cloud or hardware run.

## Review Focus

- A later package path accidentally preceding validated Torch/Transformers must fail the identity preflight.
- A cv2 import alone may miss NumPy ABI incompatibility; execute CPU image/component operations and Torch/NumPy roundtrip.
- New app modules also need cryptography; import the entire CLI dependency chain, not just cv2.
- A launcher must preserve CLI arguments, default dry-run behavior and existing resource/security admission.
- Concurrent R544 code changes must not be hidden by an overlay; record source hashes and recheck compatibility before eventual native execution.

---

## Failure, root cause and observed proof

Original import exited 1 with `ModuleNotFoundError: No module named 'cv2'` (original-import.stderr, 117 bytes). Runtime discovery shows cv2 and cryptography absent from the r505 search path; baseline.pth supplies the validated Molmo Transformers and .venv-vlm packages. The app environment already contains the missing dependencies, so the bounded hypothesis is that appending its site-packages supplies only missing imports while retaining validated packages.

**This actual Astra planner tested that hypothesis without a model load:** original r505 interpreter, app site-packages appended at tail, managed-worktree root/src added for project imports; preflight exit 0, stderr empty. `cv2.cvtColor` on uint8 RGB, `cv2.connectedComponentsWithStats` with expected foreground area 4, and `torch.from_numpy(...).numpy()` equality passed. AutoProcessor, AutoModelForImageTextToText, molmo_pointing, grounded_planner and the diagnostic CLI all imported. `torch.cuda.is_initialized()` was false. No model/processor from_pretrained call, generation, paid cloud request or hardware action occurred.

Observed imports:

| Module | Version | Exact origin relative to original repo |
|---|---|---|
| torch | 2.6.0+cu124 | `.venv-vlm/lib/python3.12/site-packages/torch/__init__.py` |
| transformers | 4.57.1 | `artifacts/research/process/20261004-t7-parallel-local-models-physics/molmo/.venv/lib/python3.12/site-packages/transformers/__init__.py` |
| numpy | 2.5.3 | `.venv-vlm/lib/python3.12/site-packages/numpy/__init__.py` |
| cv2 | 4.14.0 | `.venv/lib/python3.12/site-packages/cv2/__init__.py` |
| pydantic | 2.13.5 | `.venv-vlm/lib/python3.12/site-packages/pydantic/__init__.py` |
| cryptography | 50.0.2 | `.venv/lib/python3.12/site-packages/cryptography/__init__.py` |

Full import paths, module entry-file SHA256, original/effective sys.path and check results are preserved in `planner-r545-import-preflight.stdout`; probe source and empty stderr are alongside it. Entry-file hashes attest those inspected files, not the entire SDK or a reproducible full environment.

## Task 1: Isolated append-only launcher

**Files:** Create `implementation/launch_molmo_grounded.py`, `implementation/test_runtime_overlay.py`, and R545 implementation report only.

**Interfaces:** `configure_overlay() -> dict[str, object]` establishes and reports verified imports; `main(argv: list[str] | None = None) -> int` consumes launcher-only `--preflight` or otherwise forwards all arguments unchanged to the existing CLI. The CLI interface itself is unchanged.

- [ ] **Step 1: Recheck input identity and preserve RED.** Verify request hashes, including frozen CLI and baseline.pth; preserve original missing-cv2 stderr. Use existing planner import proof as supported GREEN hypothesis; no redundant broken import rerun is needed. Record current original runtime interpreter and managed checkout paths.
- [ ] **Step 2: Implement the minimal launcher.** Invoke using `/home/ningyd/文档/ChatGPT/BIGsmall/datasets/model-cache/ordered-small-vlm-20261109/runtimes/molmoer-r505/bin/python -B`. Validate that executable and the existing baseline paths. Append exactly `/home/ningyd/文档/ChatGPT/BIGsmall/.venv/lib/python3.12/site-packages` once via `sys.path.append`, never insert it ahead of runtime paths or use site.addsitedir (which could execute additional .pth code). Add managed project root/src for repository imports. Import/assert the exact Torch and Transformers versions, origins and inspected entry-file hashes from planner preflight; retain NumPy origin as observed and assert cv2/app origin. Fail with a clear preflight error on drift; never fall back or install.

  For `--preflight`, repeat the recorded CPU ABI operations and all integration/CLI imports, print version/path/hash and zero-load evidence, then exit. Otherwise set sys.argv to existing CLI path plus unchanged supplied arguments and invoke `runpy.run_path(cli_path, run_name='__main__')`; preserve SystemExit code. Do not add native/paid flags, override defaults, bypass admission, or construct the model in configure_overlay. Resolve the managed repo path relative to the launcher or use its exact verified path; never execute the original checkout's old CLI accidentally.
- [ ] **Step 3: Validate without GPU or cloud.** Run the launcher `--preflight`: exit 0, same Torch/Transformers origins, CPU ABI tests PASS, all app imports PASS, CUDA uninitialized. Run launcher `--help`: existing CLI help, exit 0, no model load. Add a small argument-forwarding test using a stub runpy boundary and a drift-rejection test for wrong Torch/Transformers origin; no network/mock model success claims. Run Ruff on launcher/tests and `git diff --check`; verify all existing runtime/.pth/CLI hashes unchanged. Capture stdout/stderr, command, interpreter and actual exit codes.
- [ ] **Step 4: Record runtime acceptance and hand back.** Write `implementation-report.md` with launcher/source hashes, exact import inventory, preflight/forwarding outcomes and model-load/generation counts zero. Link from R542 phase report. Commit only scoped launcher/tests/derived evidence under existing development delivery rules. No claim that imported SDK or CLI proves native model inference, cloud success or physical behavior.

## Runtime preconditions and acceptance boundary

The original r505 interpreter, its baseline.pth, the two validated package roots and original app site-packages must already exist and remain readable. Managed-worktree writes and any host access required for shared-library imports use already authorized execution permissions. No package installs or new private virtualenv are authorized/needed by this plan. The read-only proof used the existing environment successfully; retry only to verify the final launcher, not to explore alternative dependency stacks.

R545 acceptance is runtime import/CPU ABI compatibility plus unchanged delegation. Actual model generation remains a separate R542 bounded smoke after R544 review and existing manifest/resource/lock checks. The overlay does not grant paid-cloud access or change geometry/source/freshness restrictions. If the independently reviewed CLI changes, capture its new approved hash and repeat read-only imports; do not alter R545 original evidence. New missing dependencies, version/origin drift, ABI failures or any necessary source/runtime change require the next actual Astra plan before repair. Independent R544 work may continue.

## Exact inputs and evidence

- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/AGENTS.md` — 1774 bytes — SHA256 `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/scripts/probe_molmo_grounded_planner.py` — 17581 bytes — SHA256 `0739d011c7ef40bcd185b36397bb29eeadb6d0080846a25a4249fa79d4a242f1`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round545-molmo-opencv-runtime-overlay-20261110/original-import.stderr` — 117 bytes — SHA256 `4e10976c497f74edde2010d9fbcf6d66f916817f23508021418657856f6e321b`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round545-molmo-opencv-runtime-overlay-20261110/runtime-discovery.stdout` — 831 bytes — SHA256 `7e038d4f040565f134ef395ed5e21aae5677dbb9b7e387f8c24373a415bff5e7`
- `/home/ningyd/文档/ChatGPT/BIGsmall/datasets/model-cache/ordered-small-vlm-20261109/runtimes/molmoer-r505/lib/python3.12/site-packages/baseline.pth` — 223 bytes — SHA256 `c27799d1447657bb728396e8a7df833ee725b483943faf5724f73904805920b1`

Planner proof files:

- `planner-r545-import-preflight.py` — 2158 bytes — SHA256 `691da3a69795a333a08a61e7a33e6bc237773b25622f97f1811065aee281b87f`
- `planner-r545-import-preflight.stdout` — 4426 bytes — SHA256 `654de3974d33c6519bf7c211c6a76d1c0f1ec943d7435f595f6ee7dbb9d9bedc`
- `planner-r545-import-preflight.stderr` — 0 bytes — SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

Self-review: one bounded runtime task, exact dependency precedence, actual CPU ABI proof, unchanged CLI, no unresolved design decision. No production edits were performed during planning.
