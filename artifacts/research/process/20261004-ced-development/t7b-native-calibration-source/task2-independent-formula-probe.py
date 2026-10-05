"""CPU-only synthetic/non-native component-key collision probe.

No renderer, physics, model, cloud, hardware or Git runs. No measured data or
native registration is claimed. Patch revalidation and per-group reconstruction
ONLY to isolate the REAL reconstruct_registered_calibration aggregation/rank.
The valid geometry schema comes from an existing SOFTWARE_ONLY test helper.
"""

from unittest.mock import patch

from cloud_edge_robot_arm.research import native_geometry_calibration as producer
from cloud_edge_robot_arm.vision.native_calibration import NativeCalibrationRegistration
from tests.test_native_calibration_source import geometry


def allocation(group_id, ancestor):
    return {"group_id": group_id, "ancestor_ids": [ancestor]}


allocations = [
    allocation("a", "shared-origin"),
    allocation("b", "shared-origin"),
    allocation("a|b", "independent-origin-ab"),
    *[allocation(f"z{index}", f"independent-origin-z{index}") for index in range(8)],
]

payload = {
    "source_scope": "SOFTWARE_ONLY",
    "geometry": geometry(),
    "groups": allocations,
    "supported_actions": {"MOVE_ABOVE": 10.0},
}


def synthetic_group(registration, registry, allocated, scope):
    group_id = allocated["group_id"]
    residual = None if group_id == "a" else 0.001
    return producer.CalibrationGroupResult(
        group_id=group_id,
        status="INCOMPLETE" if residual is None else "COMPLETE",
        allocated_frames=1,
        missing_frames=int(residual is None),
        unknown_frames=0,
        failed_actions=int(residual is None),
        geometry_error_m=residual,
        action_errors_m={"MOVE_ABOVE": residual},
        reasons=("synthetic_unknown",) if residual is None else (),
        fingerprints=("synthetic-original:" + group_id,),
    )


# Exact concrete class remains under the real public entry point's type check;
# constructor/source checks are intentionally outside this arithmetic-only probe.
registration = object.__new__(NativeCalibrationRegistration)
with patch.object(NativeCalibrationRegistration, "revalidate", return_value=payload), patch.object(
    producer, "_group", side_effect=synthetic_group
):
    diagnostics = producer.reconstruct_registered_calibration(registration)

# A tuple-safe independent oracle retains one unavailable score per real component.
by_id = {group.group_id: group for group in diagnostics.groups}
expected_scores = {}
for index, component in enumerate(diagnostics.components):
    residuals = [by_id[group_id].geometry_error_m for group_id in component]
    expected_scores[f"component-index-{index}"] = (
        None if any(value is None for value in residuals) else max(residuals)
    )
expected = producer.conformal_group_quantile(expected_scores)
print("scope=SOFTWARE_ONLY_SYNTHETIC_NON_NATIVE")
print("isolated_patches=NativeCalibrationRegistration.revalidate,_group")
print("called_real_entry_point=reconstruct_registered_calibration")
print(f"assigned_group_count={diagnostics.assigned_group_count}")
print(f"components={diagnostics.components!r}")
print(f"diagnostic_independent_group_count={diagnostics.independent_group_count}")
print(f"actual_geometry_quantile={diagnostics.geometry_quantile!r}")
print(f"actual_action_quantile={diagnostics.action_quantiles['MOVE_ABOVE']!r}")
print(f"expected_tuple_safe_quantile={expected!r}")
assert diagnostics.assigned_group_count == 11
assert diagnostics.independent_group_count == 10
assert diagnostics.geometry_quantile.group_count == 9
assert diagnostics.geometry_quantile.bound_m == 0.001
assert diagnostics.geometry_quantile.unavailable_group_ids == ()
assert diagnostics.action_quantiles["MOVE_ABOVE"].bound_m == 0.001
assert expected.group_count == 10
assert expected.rank == 10
assert expected.bound_m is None
assert len(expected.unavailable_group_ids) == 1
print("COUNTEREXAMPLE_CONFIRMED: unavailable component overwritten by ambiguous string key")
