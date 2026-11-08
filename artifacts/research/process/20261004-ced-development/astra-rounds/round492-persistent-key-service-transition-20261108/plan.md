# R492 deterministic private vault default before deployment

Actual gpt-6-astra plan under AGENTS.md. User persistence authorization remains sufficient. This finalized R492 is a **software deployment prerequisite only**. The earlier transition proposal is retained as `superseded-transition-draft.md/json` for history and is NOT executable authorization. Actual PID300100 replacement requires the subsequent R493 transition plan after these tests pass. Root installs this plan via reviewed escalation; planning writes only the Codex work draft directory.

## Newly observed issue and evidence

Read-only metadata in discovery.json shows repository ancestors ChatGPT/repo/data mode0775. Current factory selects DB.parent/.model-control-secrets; encrypted store correctly rejects group-writable ancestors. Therefore the proposed default cannot persist a key in this real installation. A one-off override would also be lost on a later normal launcher restart. Fix the deterministic default itself; do not chmod the project, relax encrypted-store checks, conditionally select paths based on permissions, or require repeated manual environment configuration.

Existing home/.local/.local/share are owner-private/non-group-writable; metadata only was inspected. No user vault/credential bytes or full DB payload were read. Earlier read-only SQLite queries were limited to known profile IDs/active ID; no further DB access is needed in this round. R489 backend49, adjacent39/1deselected; R491 Escape audit2, final frontend13 and typecheck pass. Independent reviewer has no confirmed findings. These earlier results do not cover the new default selection.

## Exact design and scope

Modify only `src/cloud_edge_robot_arm/model_control/secret_store.py` and `tests/test_encrypted_model_secret_store.py`, plus R492 report/docs. The local work/run_r489_check.py may gain test-process-only XDG isolation; it is test tooling, not deployment configuration. No launcher or encrypted_secret_store.py implementation change.

Factory precedence stays: SESSION_ONLY returns memory; invalid mode rejects; explicit MODEL_CONTROL_SECRET_DIR uses its existing semantics. Otherwise choose private base from nonempty absolute XDG_DATA_HOME, or `Path.home()/'.local'/'share'` when unset/empty. Reject relative nonempty XDG_DATA_HOME with sanitized SecretStoreError instead of silently falling back. Do not create directories in factory.

Default directory is:

```text
<data_base>/BIGsmall/model-control-secrets/<sha256-of-normalized-absolute-database-path>
```

Define normalized DB path as `os.path.abspath(os.fspath(database_path))`; encode its string as UTF-8 and use all64 lowercase SHA256 hex characters. This removes dot segments without reading DB contents or following a DB symlink. Same normalized absolute path -> same directory across processes/cwd; distinct actual configured DB paths -> distinct namespaces. A relative DB argument means the actual DB location relative to that launcher's cwd; do not pretend different DB files are identical. Existing standard console/linux launchers already pin absolute MODEL_CONTROL_DB; dev factory follows whatever actual DB path it uses. Stable HOME/XDG plus same DB path require no secret-directory override on future launches.

No probing or import of the old DB-adjacent vault and no automatic migration: R489 has not deployed/persisted the user's key. Existing explicit override remains usable for intentionally chosen stores. If someone changes HOME/XDG or database path later, that is a different storage location; do not promise cross-location recovery. Keep all encryption/permission/symlink/corruption/locking semantics unchanged.

## RED before implementation

1. Pin/recheck inputs. Extend existing autouse test isolation to set XDG_DATA_HOME to a fresh private tmp_path child0700 and clear secret-dir/store overrides. Fallback tests mock Path.home to a temp directory and remove XDG; do not change the real process HOME or write a real user's directory. Subprocess fixtures must receive the same explicit temp XDG setting. For adjacent tests run via checker with XDG_DATA_HOME set to a newly created0700 temporary validation directory; preserve caller HOME, never reuse actual user data. Record only temp-path metadata, not vault bytes.
2. Add `test_default_vault_persists_when_database_parent_is_shared`: make a tmp_path/shared directory mode0775, choose its profiles.db, set a separate private temp XDG root, leave MODEL_CONTROL_SECRET_DIR unset. Through real create_secret_store set a fictional key, recreate the factory and recover it (fresh subprocess boolean success is preferred using existing helper). Assert no vault was created under shared DB parent and its0775 mode stays unchanged. Against current factory expect SecretStoreError at set_secret because it uses the shared parent; this is the intended behavioral RED. Save unique R492 default-path-red stdout/stderr/rc and source hashes before implementing; fixture/import mistakes are not product RED.
3. Implement only deterministic default calculation/imports/docstring. No dependency addition or store security changes. Add behavior checks: (a) same absolute DB path after chdir/new process recovers original key; (b) two DBs with identical profile ID under one XDG root retain distinct values; (c) unset/empty XDG uses mocked private home fallback, without secret-dir override; (d) invalid relative XDG rejects, explicit directory override still wins and SESSION_ONLY ignores XDG; (e) factory remains lazy; malformed/unsafe XDG ancestor remains safely rejected by existing store, not redirected elsewhere. Existing rotate/delete/corruption/concurrency tests continue unchanged except their test-only directory targeting. The existing API corruption fixture that assumes tmp_path/.model-control-secrets must point to the actual created factory namespace, not an unrelated old directory; no assertion weakening.

## Verification and return to deployment planning

4. Run focused GREEN once:

```text
.venv/bin/python -m pytest -q tests/test_encrypted_model_secret_store.py
```

Then with the isolated temporary XDG root in checker child environment run the existing selected backend regression command:

```text
.venv/bin/python -m pytest -q tests/test_phase11_2_model_control_backend.py tests/test_model_control_rgbd_snapshot.py tests/test_openai_sol_visual_migration.py -k 'not test_fake_ollama_models_download_activate_and_planner_dry_run'
```

No frontend changes: the final R491 frontend13/typecheck receipts remain applicable; do not rerun them just to broaden testing. Capture every attempt uniquely with command/rc/duration/output hashes. Correct ordinary test fixture/path issues within this declared scope; a new product cause requires Astra. No live API, model, GPU, render, physics or service action.
5. Report actual pass counts, default calculation and unchanged security boundaries. Preserve original R489 plan and evidence, record that R492 supersedes its DB-parent default and test-isolation assumption. No current real vault migration or key persistence claim. Root commits/pushes named verified changes/records with local/upstream/remote SHA checks, avoiding unrelated worktrees.
6. Return to R493 for the already-authorized controlled service transition. It must use the deterministic new default (no one-off secret-dir workaround), retain the verified actual DB and existing active profile, keep paid=false and require one final user key-only entry. Old PID300100 and existing Vite remain untouched until R493 readiness. Revalidate their identities rather than relying on stale discovery. The superseded R492 transition draft may supply nonsecret context only; it does not authorize restart now.

## Self-review and acceptance

Acceptance: a real set/get/reopen against a0775 DB-parent succeeds using private deterministic namespace, separate DBs cannot collide, normal same-DB restarts need no secret-dir setup, explicit opt-out/override preserved, all security tests and selected backend checks pass without user-home writes. The root cause is path selection, not encryption permissions. No repo mutation/tests/live action by this planner; source hashes and discovery pinned in plan.json. Current user key is still only in the old process and is not exported or moved.
