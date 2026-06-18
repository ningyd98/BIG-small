# Simulation Runtime Recovery

Startup recovery scans persisted jobs and artifacts:

- `QUEUED` remains queued.
- Expired `LEASED`, `STARTING`, or `RUNNING` jobs are marked `INTERRUPTED`.
- Complete artifacts can be restored as historical records.
- Incomplete artifacts become recovery evidence and require retry or review.
- Already complete jobs are not re-executed.

The safe recovery API is `POST /api/v1/simulation/runtime/recover` and requires a safety-reviewer role. It does not execute arbitrary commands.

The standalone command is:

```bash
python scripts/recover_phase11_runtime.py \
  --artifact-root artifacts \
  --database data/simulation_runtime.db \
  --dry-run
```
