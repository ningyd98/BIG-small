from __future__ import annotations

from pathlib import Path


def test_phase9_1_verifier_runs_at_least_500_safety_pressure_trials() -> None:
    source = Path("scripts/verify_phase9_1.py").read_text(encoding="utf-8")

    assert 'run_safety_pressure(args.output / "safety_pressure", trials=500)' in source
