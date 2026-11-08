# R493 Persistent-key service transition implementation plan

> **For agentic workers:** Execute this bounded plan inline; no additional delegation. This is deployment of the already verified R489/R492 implementation, not a product modification.

**Goal:** Make persistent key storage usable in the existing local web service, preserving the three profiles and active selection.

**Architecture:** Replace only the positively identified old backend with the same application and bind, using the existing absolute database and automatic private default. Preserve Vite. The old in-memory key is unexportable; the user must save it once through the existing row action.

**Tech stack:** Existing Python virtualenv/Uvicorn/FastAPI, Fernet vault, existing Vite/React UI.

**Spec:** User “密钥固化，不要每次重新配”; R489 persistence plan, R492 private-default plan and software report. Canonical destination: `artifacts/research/process/20261004-ced-development/astra-rounds/round493-persistent-key-live-transition-20261108`.

## Evidence and boundaries

R492 frozen report: focused **56**, adjacent **39** (one renderer case excluded), unchanged R491 frontend **13**, final style/typecheck pass: **108** tests total. R492 scoped independent review has no findings; R491 keyboard hypothesis was not reproduced. Validate hashes before execution. The old live process still holds the sole session key; no live key migration or persistence has been proved.

Prior read-only discovery: backend PID **300100**, uid1000, starttime **8283996**, cwd repo, Uvicorn `cloud_edge_robot_arm.cloud.api.dev_dashboard_app:app`, loopback8000; parent1520/systemd and shared scope must remain. Vite PID **159968**, starttime **8153269**, loopback5173 remains. These are admission hypotheses, not permission to signal a reused PID. Known database is `/home/ningyd/文档/ChatGPT/BIGsmall/data/model_control.db`, with active `profile-4f24f5330ad644ad` and the three IDs listed in JSON.

No product edits, model tests, planner dry-runs, observations, GPU/render/physics/controller/hardware operations or paid-gate enabling. Do not access process memory/environ, credentials, vault bytes, full database payload or full unknown argv. No key export/relay or forced migration. No temporary XDG, explicit vault override or directory-permission workaround. The plan author performs no live operation.

## Executable steps

- [ ] **1. Readiness and identity admission.** Verify all input pins, R492 review source pins, 56 focused + 39 adjacent + 13 frontend passes and final style/typecheck. Revalidate PID 300100 uid1000 starttime8283996 cwd/repo, known uvicorn module, loopback8000 listener, and frontend159968 starttime8153269. Inspect only allowlisted command tokens; never dump argv/environ. Preserve parent1520 and shared systemd scope. Any mismatch stops before signaling.

- [ ] **2. Freeze nonsecret before-state and launch contract.** Bounded GET /health and /api/v1/model-control/{profiles,runtime,capabilities}, each timeout5s one request. Retain only allowlisted profile config, IDs, active, secret flags/kind and selected runtime identity; exclude api_key and last_test. Assert three expected IDs and active profile-4f24f5330ad644ad. Confirm candidate SQLite path exists regular and read-only SELECT profile_id and active_profile_id only matches live IDs; no payload/blob, vault or DB backup/hash. Verify stable real HOME/XDG and safe default directory ancestors using lstat only. Prepare detached launcher and receipts before stopping.

- [ ] **3. Replace exactly owned backend once.** Immediately recheck full identity and retain pidfd if supported. SIGTERM only that PID via pidfd where possible, wait <=30s. No SIGKILL/group/parent signals. If still alive or unexpected listener appears, stop. Launch exactly one new backend using absolute .venv Python and argv specified below, cwd repo, start_new_session=True, stdin DEVNULL, stdout/stderr to dedicated logs. Record new pid/starttime/uid and known argv. Do not invoke combined launcher that would create another Vite or initialize other runtime state.

- [ ] **4. Bounded health and metadata acceptance.** At most10 /health attempts timeout2s with <=1s spacing, overall30s. Then one bounded GET each profiles/runtime/capabilities. Require same three IDs, same nonsecret config and active ID; all returned storekind ENCRYPTED_FILE, actual secret_present false expected before user save; advertised modes ENCRYPTED_FILE and SESSION_ONLY. Exclude historical session presence/kind from config equality. READY alone is not credential validation. Verify new PID owns8000 and original Vite159968 remains. Unexpected present=true is not migration proof: record and stop for provenance review without reading vault.

- [ ] **5. UI available for one-time entry.** Optional one GET http://127.0.0.1:5173/models timeout5s plus bounded browser inspection of empty existing-profile key modal. Do not inspect password properties, type a key, submit or capture credential-bearing screenshots. Preserve Vite; no build needed for verified Vite source serving. Explain user saves same key once via existing active row 保存/更新密钥, with all model metadata retained. End ready_for_one_time_key_entry if user has not saved; no waiting/poll loop.

- [ ] **6. Conditional persistence proof after direct user UI save.** Only after user save acknowledgement/explicit user confirmation, one metadata GET must show active profile secret_present=true and ENCRYPTED_FILE. No key reading/export. Perform at most one additional ordinary restart with same validated launcher/DB/HOME/XDG and identical PID admission, then metadata true + same config/active proves store recovery. Record persisted_key_survives_restart only on this evidence. If user does not enter during task, mark verification pending and finish ready_for_one_time_key_entry; never request key in chat.

- [ ] **7. Receipts and scoped delivery.** Keep exact raw operational logs and filtered metadata receipts, timing/exit/status, source pins and command manifest. No secrets/full env/DB/vault bytes in artifacts/Git. Report software108pass separately from live transition/persistence. Commit and push only named R489–R493 source/test/docs/reports already in authorized scope and verify local/upstream/remote SHA; preserve unrelated nested worktrees. New root cause or unexpected failure requires next Astra before repair.

## Exact launch contract

Use `subprocess.Popen(argv, cwd=repo, env=allowlisted_env, start_new_session=True, stdin=DEVNULL, stdout=dedicated_log, stderr=dedicated_log)` from a small R493 operational runner. Do not use the R489 test runner (it deliberately creates temporary XDG directories). Use absolute argv below; record only explicit nonsecret launch settings. Prepare the runner and log paths before stopping the old backend. Do not detach through a tool PTY that might terminate its child on exit.

```text
/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m uvicorn cloud_edge_robot_arm.cloud.api.dev_dashboard_app:app --host 127.0.0.1 --port 8000 --log-level info
```

Set HOME to the actual account `/home/ningyd`, PYTHONPATH to repo/src, MODEL_CONTROL_DB to the absolute path above, MODEL_CONTROL_SECRET_STORE=ENCRYPTED_FILE, DASHBOARD_AUTH_MODE=LOCAL_ONLY, DASHBOARD_EXPERIMENT_WRITES_ENABLED=false, BIGSMALL_VLM_ALLOW_PAID_CALL=false. Omit MODEL_CONTROL_SECRET_DIR. Preserve only necessary ordinary nonsecret OS variables in the allowlist; do not copy undocumented model/hardware configuration or credentials. The absence of hardware actions is enforced by the endpoint allowlist, not by an invented environment flag.

Use stable actual-user absolute XDG_DATA_HOME only if positively established from the executing account's nonsecret configuration; otherwise standard unset/empty XDG selects `/home/ningyd/.local/share`. Reject temporary/test or relative bases, and record the selection without dumping environment. This must match subsequent normal launchers for the same user and DB. The full SHA256 DB namespace is `7c31639e813b398a533659d39804068dcc95de2e3634b9cf4bb5fea08f195c91`. Preflight with `lstat` of existing ancestors only; do not create, inspect or reset vault files. Existing absent vault is expected and will be created by the user save. If a configured stable XDG cannot be established consistently, stop before replacing the old process.

Metadata comparison allowlist: profile_id, display_name, provider_kind, base_url, chat_completions_path, model_name, temperature, max_tokens, timeout_seconds, max_retries, json_mode, enabled, active, endpoint_hash, config_version, created_at, updated_at, secret_updated_at. Record secret_present/kind separately. Exclude api_key and runtime.last_test. Do not log unexpected unstructured responses; redact endpoint userinfo/query if encountered and retain a hash for equality. Runtime comparison uses active_profile_id/provider/model/endpoint_hash/config_version only. Do not reactivate or rewrite profiles to make comparison pass. Expected active model remains gpt-6.1-sol, max_tokens4096, timeout30; capture remaining settings from the live pre-state.

## Recovery and acceptance

Before SIGTERM failure leaves old service untouched. After SIGTERM the memory key is unrecoverable; do not claim rollback can restore it. If new process fails health/metadata, terminate only the still identity-matched new process, wait <=30s, keep logs/DB/frontend intact, and report bounded stopped state requiring new Astra diagnosis. No automatic retry, old-source rollback, vault reset, fallback or secret migration.

A successful first transition ends **ready_for_one_time_key_entry**, with key presence false and the existing `/models` row action available; tell the user to paste the same key once there, retaining name/base/model. Never ask for a key in chat. Only the conditional user save plus ordinary restart may produce **persisted_key_survives_restart**. Health/READY and ENCRYPTED_FILE labels do not establish provider validity, paid-call permission or nominal R469 qualification; nominal remains NOT_RUN.

Input pins (source, reviews, receipts and prior discovery; no DB/vault) are embedded in `plan.json`. Preserve original stdout/stderr and append unique stage receipts. Self-review completed: bounded ownership checks/recovery, stable default across launches, no source changes or secret access, actual presence vs stale metadata, and software/live/nominal boundaries covered. No new confirmation gate is introduced for the already authorized local development restart.
