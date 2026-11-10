# R546 Grounded Observer Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for this one bounded task. Steps use checkbox (`- [ ]`) syntax. Existing authorization covers implementation; no extra review or sub-agent dispatch is required.

**Goal:** Bind cloud raw observers to their own attempt directories and counters, then clear two test import-order findings.

**Architecture:** Retain the current inline observer and capture its attempt index/counter dictionary through explicit default arguments. Run-level paid-start accounting stays shared. No transport, body-preservation, success-policy or pipeline changes.

**Tech Stack:** Existing Python 3.12, pytest and Ruff.

**Spec:** R546 request.json; R544 boundary repair plan and R542 integration constraints remain authoritative. Actual planner_model: `gpt-6-astra`.

## Global Constraints

- Only modify `scripts/probe_molmo_grounded_planner.py` and `tests/test_molmo_grounded_cli.py`; record R546 evidence under this round and link it in the phase report. Both source SHA256 values and original Ruff evidence matched during planning; recheck before editing.
- Preserve exact request/response bytes, exclusive numbered writes, failure manifests, paid-start counting, selected Sol transport/security, native budgets and default no-paid behavior. No new SDK/runtime/model/geometry changes.
- R544 reported functional127 PASS is prior evidence; this plan requires post-edit regression. R545 import preflight is independent and grants no model/cloud/hardware acceptance.
- Actual calls in this round remain zero. R542 cumulative native starts remain 0 load / 0 generation at plan time; caps remain <=1 / <=8, never reset by this round.
- No additional independent review or sub-agents. Keep historical failure/raw files unchanged; do not stage local raw, credentials, databases, SDK or weights.

## Review Focus

- An attempt-1 callback invoked after attempt 2 starts must still write under attempt-01.
- REQUEST and RESPONSE counters must stay separate within each attempt and never inherit attempt-2 values.
- Delayed request callbacks must still increment the existing shared paid-start ledger once per callback.
- Raw bytes and manifest hashes must survive delayed callbacks before finalization unchanged.
- Ordinary immediate callbacks, malformed reply/failure status and all existing R544 boundaries must remain compatible.

---

## Failure evidence and root cause

`original-ruff.stdout` (2710 bytes, exit1) records B023 at CLI lines365/366 for `observer_counts`, line368 for `index`, plus I001 at test lines259/289. The loop creates a new function but its closure cells refer to the enclosing loop variables; an observer retained from an earlier iteration can read the newest index and counter dictionary. Current synchronous production transport often finishes within an iteration, so this finding alone does not prove existing raw files were misattributed. A controlled deferred-callback test is warranted because wrong attempt attribution would corrupt evidence if the observer is retained or invoked later. No general asynchronous transport support or post-finalization callback mechanism is being added.

The I001 failures concern only the two listed local import blocks. Sort them using existing Ruff conventions without moving test logic or changing imports elsewhere.

## Task 1: Bind observer state and prove two-attempt isolation

**Files:** CLI observer block around lines362–373; test file's two local import blocks plus one focused regression.

**Interface:** The transport still calls observer with `(phase: str, path: str, data: bytes) -> None`. Bind state with keyword-only defaults so all existing three-positional-argument callers remain unchanged:

```python
def observe(
    phase: str,
    path: str,
    data: bytes,
    *,
    attempt_index: int = index,
    counts: dict[str, int] = observer_counts,
) -> None:
```

Use `counts` for both counter references and `attempt_index` for the attempt directory. Keep the body otherwise unchanged, including shared `paid_starts.append(sha256(data))`. Each function definition captures that iteration's freshly created dictionary; do not copy it on every callback, share one global counter, or bind a snapshot of paid_starts.

- [ ] **Step 1 — Freeze inputs and write a meaningful RED test.** Add `test_cloud_observers_keep_attempt_binding_when_callbacks_are_delayed` using two explicit request/descriptor pairs and two fixture cloud adapters. Reuse NativeFixture/resource stubs; no real model, network, cloud service or hardware. Intercept PlanningPipeline with a CPU fixture that retains observer1 during the first process call. During the second process call, after observer2 has been assigned, emit callbacks in this deterministic order: observer1 REQUEST(first) during attempt1; observer2 REQUEST(first) during attempt2; observer1 REQUEST(second, delayed); observer1 RESPONSE(first, delayed); observer2 RESPONSE(first). Use distinct nonsecret raw JSON byte strings. Return fixture PLANNED/geometry-ready results so main finalizes normally. Invoke delayed callbacks before final report/manifest creation; do not test or authorize background writes after completion.

  Assert attempt-01 contains request-0001, request-0002 and response-0001 with their exact assigned bytes; attempt-02 contains request-0001 and response-0001 only, no request-0002 or response-0002. Assert global paid_cloud_calls_started=3, two recorded attempts, and raw-manifest SHA256 matches all five files. Explicitly label all fake execution as CPU fixtures. The existing code should fail these path/byte assertions because retained observer1 uses attempt2's counter/index; preserve that RED result.
- [ ] **Step 2 — Run expected RED only.** `/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest tests/test_molmo_grounded_cli.py::test_cloud_observers_keep_attempt_binding_when_callbacks_are_delayed -q -p no:cacheprovider`. Expected wrong/missing attempt-01 files, not unrelated dependency or mock setup failures. Keep original lint output. Any unrelated failure requires diagnosis/new Astra planning before repair outside this scope.
- [ ] **Step 3 — Implement exact binding and import sorting.** Add the default captures above and replace only the three late-bound body references. Sort the two local import blocks identified by original Ruff; do not run broad unsafe fixes or restructure the CLI. Preserve path argument compatibility even though body presently does not consume it. Do not change observer phase handling, filename numbering, callback order, paid-start semantics or exclusive-write behavior.
- [ ] **Step 4 — Run GREEN and R544/R542 regression.** Repeat the focused regression, then use the same existing app interpreter for `-m pytest tests/test_molmo_pointing.py tests/test_molmo_grounded_planner.py tests/test_molmo_grounded_cli.py tests/test_rgbd_planning.py tests/test_rgbd_top_grasp.py tests/test_rgbd_role_models.py -q -p no:cacheprovider`. Record actual collected/passed count; do not substitute prior127 PASS for this result. Use authorized host loopback permissions where required. Run existing Ruff with `--no-cache` on the two changed files, then the R544 eight-file scope, and `git diff --check`; expected all pass. No new full-suite rerun is required for this narrow repair when these pass; preserve independent full-suite evidence separately.
- [ ] **Step 5 — Record and commit explicit verified paths.** Write R546 implementation report with original/new SHA256, focused RED/GREEN, full selected regression counts, lint/diff results, commands, interpreter and exit codes. Link into R542/R544 phase report. Commit only verified scoped source/test and intended reports under the existing development-branch delivery policy; retain previous raw failure evidence and verify local/upstream/remote SHA if pushed.

## Preconditions, acceptance and stop boundary

Managed-worktree writes need existing approved access; tests use the existing app .venv and established loopback permission, with native/cloud/resource boundaries mocked. For independent app-interpreter stdin/import commands, explicitly set `PYTHONPATH=/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src` so imports resolve the managed worktree. Parent observed ModuleNotFoundError for grounded_planner when this variable was omitted and Python selected the original checkout installed package; this is a command invocation/path-selection issue, not a model/interface defect. Correcting that command environment is authorized within this plan without source changes. No template was created and no model started by that failed command. Native entry still uses only the R545 launcher to manage sys.path; do not replace its validated package ordering with this app-only PYTHONPATH command. Pytest already uses the correct configured project paths; parent reports its independent current regression249 PASS, which remains separate from post-repair verification. No dependency installation or actual model load is required. Acceptance is software observer-binding correctness, raw-byte provenance and lint compatibility only. Real-local inference, real cloud, physical and formal-research acceptance are NOT_PERFORMED by R546. If two-attempt behavior needs broader lifecycle/transport changes, current input hashes drift, other lint roots appear, or regression shows another defect, stop the affected repair and request the next actual Astra plan. The explicit deferred-callback RED failure is expected and already covered here.

## Verified inventory

- `scripts/probe_molmo_grounded_planner.py` — 20674 bytes — SHA256 `16e551fe9c145e4f6acc962c0252b363106ec1af47afe9f0047dda3315992bb3`
- `tests/test_molmo_grounded_cli.py` — 13580 bytes — SHA256 `5ef1b9cd3ceccc7ae5bc3a81205aae57fb874ea0a7b03bcca5266e548191cd2b`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round546-grounded-observer-binding-20261110/original-ruff.stdout` — 2710 bytes — SHA256 `adf1c96e72cd3a4e6b10ad17e7148a306072b29be0966134d7f0f42141215744`
- `AGENTS.md` — 1774 bytes — SHA256 `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round544-molmo-integration-review-fixes-20261110/plan.md` — 14404 bytes — SHA256 `f268088c71ca4efbd67fe6c6916f97ec82d625887b7423303fcc44d3cc3e3f70`

Self-review: both late-bound values captured, shared accounting intentionally preserved, a deterministic two-attempt RED/GREEN test is required, two import blocks only, no unresolved design choices or production changes by this planner.
