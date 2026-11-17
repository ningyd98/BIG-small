# Actual review probe invocation

- Working directory: `/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall`
- HEAD: `4ed5cb50ada7b6b0ca6b3a2fd168aeca637e3cfa`
- Actual shell invocation: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" .venv/bin/python - <<'PY'`, followed by the exact Python body preserved in `lift-hold-exception-probe.py`, then `PY`.
- Tool result chunk ID: `4bdb91`.
- Exit code: `0`; elapsed tool wall time: `0.647138871 s`.
- `lift-hold-exception-probe.stdout.json` preserves the stdout copied from that actual tool result. It was copied to this file after the run; the original command did not redirect stdout to a file. No stderr was shown.
- The probe ran real MuJoCo approach/grasp/LIFT physics with rendering disabled. Its visual callback was identity; it did not run a complete worker, camera rendering, a model, or hardware. The observer raised a RuntimeError on the first LIFT hold step after the motion controller reported SUCCEEDED. This is an exception-cleanup probe, not new visual or physical acceptance evidence.

Equivalent replay command (not run again during this review):

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" .venv/bin/python \
  /tmp/bigsmall-grasp-audit-20261117/lift-hold-exception-probe.py
```
