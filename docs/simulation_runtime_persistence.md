# Simulation Runtime Persistence

The default database is `data/simulation_runtime.db`. It is local runtime data and is ignored by git.

SQLite tables:

- `schema_migrations`
- `simulation_jobs`
- `simulation_job_events`
- `simulation_job_leases`
- `simulation_job_attempts`
- `simulation_metrics`
- `simulation_artifacts`
- `simulation_batches`

The repository uses CAS status updates, transaction-protected lease acquisition, monotonic per-job event sequence, and monotonic global stream sequence. Paths saved in the database are repository-relative artifact paths; credentials, tokens, raw controller configuration, and local absolute paths are not persisted.

Utility scripts:

- `scripts/init_simulation_runtime_db.py`
- `scripts/inspect_simulation_runtime_db.py`
- `scripts/recover_phase11_runtime.py --dry-run`

`recover_phase11_runtime.py --apply` writes restored records. The default is dry-run.
