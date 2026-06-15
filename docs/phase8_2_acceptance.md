# Phase 8.2 Acceptance

Phase 8.2 acceptance is executable.

## Required Commands

- `ruff format --check .`
- `ruff check .`
- `mypy .`
- `pytest -q`
- `python scripts/verify_phase8.py`
- `python scripts/verify_phase8_1.py`
- `python scripts/verify_phase8_2.py`
- `pip check`
- Phase 3-7 verification scripts

## New Guard Conditions

`scripts/verify_phase8_2.py` fails if:

- PCSC tasks do not produce multiple periodic ticks.
- Fault detection latency collapses to zero.
- Multi-crash recovery covers fewer than the nine Phase 8.2 crash points.
- Mode, network, or seed group metrics are all identical.
- PCSC has no run with at least two supervision decisions.

## New Tests

- `tests/test_phase8_2_pcsc_multiple_ticks.py`
- `tests/test_phase8_2_tick_step_interleaving.py`
- `tests/test_phase8_2_tick_observes_dynamic_fault.py`
- `tests/test_phase8_2_eteac_has_no_ticks.py`
- `tests/test_phase8_2_fault_detection_realism.py`
- `tests/test_phase8_2_transition_safe_boundary.py`
- `tests/test_phase8_2_crash_points.py`
- `tests/test_phase8_2_experiment_sensitivity.py`

## Run Sizes

- Smoke: 45 runs
- Validation: 675 runs
- Full benchmark: 2250 runs
