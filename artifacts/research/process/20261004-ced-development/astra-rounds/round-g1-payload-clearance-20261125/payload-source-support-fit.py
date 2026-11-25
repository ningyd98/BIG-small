"""Bound only the named source-table support, using the original two loaded training trajectories."""
import json
from pathlib import Path

from scripts.graduation.g1_complete_cv_calibrate import digest

ROOT=Path.cwd();private=ROOT/'experiments/results/g1-payload-clearance-20261125'
runtime=ROOT/'experiments/results/g1-complete-cv-repair-20261125/builds/816ed631e9dd17b510d2853afda7995b87e210c6cf8259df799a8a4da6b491eb/runtime-source'
sources={};rows=[]
for name in ('fit-b','fit-c'):
    f=private/'solver-substeps-01'/name/'summary.json'
    r=json.loads(f.read_bytes())
    eligible=[x for x in r['rows'] if x['phase']=='LIFT' and -.001<=x['first_bottom_m']<=.025]
    for x in eligible:
        assert digest(f.parent/x['file'])==x['sha256'] and x['unexpected_contact_ticks']==0
    rows.extend(eligible);sources[name]=dict(summary_sha256=digest(f),corners_covered=len(eligible),steps=[x['step'] for x in eligible],max_observed_initial_gap_m=max(x['first_bottom_m'] for x in eligible))
results=dict(schema='g1.native-named-source-support.v1',fit=sources,
    original_classifier_sha256=digest(runtime/'src/cloud_edge_robot_arm/simulation/mujoco/backend.py'),
    old_gate_sha256=digest(runtime/'scripts/graduation/g1_complete_cv_clearance.py'),
    registered_face_bounds=['object_geom','table'],branches=len(rows)*9,steps_after_stop=240,xy_reserve_m=1.25*max(x['max_stop_cube_xy_drift_m'] for x in rows)+.0005,
    max_tilt_rad=1.25*max(x['max_cube_tilt_degrees'] for x in rows)*3.141592653589793/180,
    min_bilateral_normal_N=.8*min(min(x['min_bilateral_force_N']) for x in rows),
    max_support_force_N=1.25*max(x['max_table_force_N'] for x in rows),
    max_negative_support_distance_m=1.25*max(-x['min_solver_support_distance_m'] for x in rows)+.000025,
    max_current_gap_m=min(v['max_observed_initial_gap_m'] for v in sources.values()),
    source_xy_local_max_m=.01,require_current_signed_volume=True)
f=ROOT/'scripts/graduation/g1_complete_cv_source_support_profile.json'
with f.open('x') as dst:json.dump(results,dst,sort_keys=True,indent=2);dst.write('\n')
print(digest(f))
