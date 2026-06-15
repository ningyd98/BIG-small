# Phase 7 Acceptance

Run:

```bash
python -m pytest tests/test_phase7_*.py -q
python scripts/verify_phase7.py
```

`scripts/verify_phase7.py` checks:

- Skill Cache SQLite restart, promotion, invalidation.
- Cache hits cannot bypass SafetyShield.
- Risk snapshot determinism and missing-input fail-closed behavior.
- AUTO decision matrix.
- Dwell time, cooldown, and switch limit anti-flapping.
- Mode transition prepare/commit/abort, CAS, and idempotency.
- SQLite restart recovery of prepared transitions.
- Phase 5 and Phase 6 dual-mode regression.
- Production profile blocks InMemory, mock, and unconfigured AUTO paths.
- AUTO capability is not advertised before configuration.
- Production source scan for placeholder and bypass paths.

The verifier returns non-zero on any failed check and does not mask sub-process failures.
