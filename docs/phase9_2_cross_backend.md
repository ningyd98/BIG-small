# Phase 9.2 Cross-Backend Validation

Phase 9.2 compares MuJoCo and Isaac using paired scenario/seed runs. The first validation suite uses:

- `S01_NORMAL_STATIC`
- `S16_PAYLOAD_MASS_VARIATION`
- `S17_CONTACT_FRICTION_VARIATION`
- `S19_CAMERA_NOISE_AND_OCCLUSION`
- `S22_COLLISION_NEAR_MISS`
- `S14_EMERGENCY_STOP`

Each backend uses the same seeds `0..4`, same semantic robot model, same initial state, same task target, same obstacle semantics, same payload/friction definitions, same safety policy, and same result schema.

Run existing artifacts verification:

```bash
python scripts/run_phase9_2_cross_backend.py --output artifacts/phase9_2/cross_backend
```

Run paired experiments on a compatible Isaac host:

```bash
python scripts/run_phase9_2_cross_backend.py \
  --run-experiments \
  --output artifacts/phase9_2/cross_backend
```

Generated artifacts:

- `mujoco_runs.jsonl`
- `isaac_runs.jsonl`
- `paired_runs.jsonl`
- `metric_deltas.json`
- `statistical_summary.json`
- `cross_backend_report.md`
- `reproducibility_manifest.json`

The verifier checks backend identity, run id uniqueness, commit SHA, scenario/seed pairing, process/environment provenance, config hash, result hash, validation flags, and required metric completeness. Isaac failure never falls back to MuJoCo.

Metric deltas are interpreted as semantic consistency, trend consistency, numeric difference, and backend-specific effects. Exact numeric equality is not required.
