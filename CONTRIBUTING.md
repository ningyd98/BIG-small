# Contributing

## Development Environment

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev,sim-mujoco,sim-analysis]"
```

## Branch and Commit Rules

- Use a topic branch unless the maintainer explicitly asks for direct `main` work.
- Use Conventional Commit prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`, `chore:`.
- Do not rewrite pushed `main` history, squash pushed commits, or force push.

## Required Checks

```bash
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/check_docs.py
```

Run environment-specific verifiers only on hosts that satisfy their documented requirements.

## Documentation Rules

- Update docs when behavior, public entrypoints, safety boundaries, or verifier status changes.
- Keep README concise; put detailed command lists in `docs/verification.md`.
- Do not claim real robot validation without authoritative hardware evidence.

## Artifact Rules

- Accepted artifacts may be committed only when they are part of an explicit validation task.
- Do not commit large caches, private site data, real controller IPs, serial numbers, credentials, or raw operator tokens.
- Generated logs and authoritative evidence must be clearly distinguished.

## Safety-related Changes

Any change to SafetyShield, HardwareExecutionGate, real robot acceptance levels, operator confirmation, or real hardware scripts must update:

- tests
- safety docs
- acceptance docs
- verifier behavior
- changelog

## Real Robot Review Rules

Real robot code must fail closed by default. It must not silently fall back to Mock, MuJoCo, Isaac, or simulation adapters in production/hardware mode.

Never add a script that automatically runs multiple hardware motion levels. Hardware motion requires explicit site configuration and operator approval.
