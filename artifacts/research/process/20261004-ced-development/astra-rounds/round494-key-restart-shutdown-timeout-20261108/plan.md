# R494 Shutdown-timeout recovery plan

**Planner:** actual gpt-6-astra. **Status:** PLANNED, not executed. **Scope:** one controlled completion of the interrupted R493 restart; no product changes.

## Issue and evidence

R493 admitted backend1407005/start9392647, observed the user-saved active encrypted key, sent one pidfd SIGTERM, then timed out after30s with `backend_did_not_exit_after_sigterm`. No replacement was launched. Preserve all original artifacts.

The subsequent frozen read-only status at2026-11-08T15:43:00.322676+00:00 shows old process absent, no8000 listener, Vite still listening, health unavailable. My read-only `/proc/1407005` check agrees. The old backend log ends with waiting for connections, then application shutdown complete and finished server process. Thus delayed graceful exit is observed; an ongoing zombie/parent-reaping problem is not supported.

Installed Uvicorn closes listeners, requests connection shutdown, then waits for connections/tasks using `timeout_graceful_shutdown`; its default is None. Current app lifespan has no shutdown work. The accepted dashboard streams loop on receive and handle WebSocketDisconnect. Open WebSockets are a plausible drain contributor, but untimestamped logs do not identify the exact connection or duration. No persistence/source defect is demonstrated. Do not modify app, runner30s history, installed Uvicorn or shutdown flags to manufacture a fix.

## Execution

- [ ] **A. Admit recovered stopped state.** Verify input pins and HEAD15dae29bda07d9f1c09c77f77a8b7678da8c77ef (or explicitly record authorized artifact-only commit progression with identical source pins). Freeze original failure unchanged. Fresh read-only /proc status must show old1407005/start9392647 absent; fresh port8000 listener inventory must be empty. Require original Vite159968/start8153269 uid1000 cwd/dashboard owns5173. Revalidate exact saved launch contract and actual HOME/XDG/namespace with existing_environment logic, directory lstat only. No DB/vault read needed. If any other listener, live old process or reused PID exists, stop without signaling or launching; no inference from stale evidence.

- [ ] **B. Launch exactly once, no stop/retry.** Create separate R494 recovery runner and exclusive logs/receipts. Reuse frozen metadata/env/identity helpers only; do not execute saved-key runner main or import a module with side effects. Immediately recheck absence and vacant8000; Popen exact prior contract argv/cwd/environment, start_new_session=True, stdin DEVNULL, stdout/stderr dedicated0600 logs. No argv changes, timeout flag additions, new vault override or temporary XDG. Save PID/starttime and source/contract hashes. This completes the already initiated ordinary restart, not a second stop of old process.

- [ ] **C. Read-only readiness and persistence proof.** At most10 health attempts timeout2s, spacing<=1s, overall30s. Require new identity and port ownership. Then one snapshot of GET profiles/runtime/capabilities each timeout5s, sanitized through existing frozen allowlist. Compare exactly with saved-key-before-restart.json state: three IDs, active4f24f5330ad644ad, active config_version2, settings and timestamps unchanged, presence map true/false/false, all ENCRYPTED_FILE, advertised ENCRYPTED_FILE+SESSION_ONLY. Never compare against initial pre-save R493 state. Fresh process must have actual derived secret_present=true without any key POST/PATCH or key read. Verify Vite unchanged. This proves durable recovery, not provider validity.

- [ ] **D. Restore UI and record honest final status.** Optional one bounded GET /models via Vite and ordinary browser view without any credential field readback. No key re-entry request, save action, provider test or dry-run. Write recovery-result.json with persisted_key_survives_fresh_process=true, original timeout preserved, delayed graceful completion observed, one recovery launch, zero additional old-process signals, no key extraction/provider calls. Keep R493 failure immutable; report R493 transition as completed across R494 recovery, not originally clean30s success. Scoped artifact commit/push and SHA verification after source pins recheck.

## Unchanged launch and secret boundaries

Use the exact contract in R493/execution/launched-process.json: absolute repo `.venv/bin/python -m uvicorn cloud_edge_robot_arm.cloud.api.dev_dashboard_app:app --host 127.0.0.1 --port 8000 --log-level info`, cwd repo, absolute repo/data/model_control.db. HOME=/home/ningyd, XDG absent as recorded, default namespace `7c31639e813b398a533659d39804068dcc95de2e3634b9cf4bb5fea08f195c91`; no secret-dir override. Preserve ENCRYPTED_FILE, LOCAL_ONLY, experimentwrites=false, paid=false, and the same allowlisted ordinary environment. Do not use the temporary-XDG software check runner. Prepare detached process logs and PID receipt before launch. No source edits, tests, reinstall, process memory/environ/stack inspection, vault bytes/full DB payload, secret API export, hardware/model/capture calls, or further restart for proof.

The saved comparison baseline already has active `config_version=2` and saved timestamp; use that baseline. Actual presence after this fresh process is sufficient proof that the prior UI save survived shutdown. Do not ask the user to paste again or click a model test.

## Failure boundary

If fresh process dies or fails health/config/key-presence checks: preserve new evidence and no second launch, no key request/reset, no fallback or changes to DB/vault. If new process remains running and must be cleaned up, first revalidate its own pid/starttime/uid/module/cwd; send at most one SIGTERM via pidfd and observe up to90s total in <=30s chunks without additional signals. This longer observation is diagnostic, not a promise that shutdown succeeds. If still alive record identity/state/listeners and stop. Never SIGKILL, SIGINT, signal old PID/shared parent/group, kill Vite or launch while occupied. New root cause returns to Astra.

## Acceptance and delivery

Service healthy in a fresh process; saved active key presence true with ENCRYPTED_FILE; three profiles/config/active unchanged; Vite preserved. Record `persisted_key_survives_fresh_process` and the original timeout honestly. This does not prove provider validity or formal nominal acceptance. Keep original raw bytes and separate recovery receipts, then scoped commit/push with local/upstream/remote SHA checks. No additional user approval is needed for the already authorized restart completion.

Input SHA256 pins are embedded in plan.json, including original failure, saved metadata baseline, completed shutdown log, exact launch contract, source and installed Uvicorn. Do not Git-stage the dependency files themselves. Self-review: no speculative product fix, no old-process signal, finite revalidation/launch/cleanup, preserved key and failure, and correct saved-version2 baseline. Plan author performed only static/read-only inspection and draft writes; no API request, signal, test or launch.
