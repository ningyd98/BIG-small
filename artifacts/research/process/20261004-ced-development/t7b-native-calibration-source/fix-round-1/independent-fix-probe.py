"""Replay the preserved exact SOFTWARE_ONLY formula probe with fixed assertions."""

import hashlib
from pathlib import Path

original = Path(__file__).resolve().parent.parent / "task2-independent-formula-probe.py"
data = original.read_bytes()
assert hashlib.sha256(data).hexdigest() == (
    "e379e75300ca4f97bc3fe6a66d18762b55755e4373570d25256554a2287e7bf0"
)
# Keep the original fixtures, isolated patches, real aggregation and oracle exact.
# Only the preserved historical assertions that expect the bug are replaced.
prefix = data.decode().split("assert diagnostics.assigned_group_count == 11", 1)[0]
exec(compile(prefix, str(original), "exec"), globals())
assert diagnostics.assigned_group_count == 11
assert diagnostics.independent_group_count == 10
for actual in (diagnostics.geometry_quantile, diagnostics.action_quantiles["MOVE_ABOVE"]):
    assert actual.group_count == expected.group_count == 10
    assert actual.rank == expected.rank == 10
    assert actual.bound_m is expected.bound_m is None
    assert actual.unavailable_group_ids == ('["a","b"]',)
    assert len(expected.unavailable_group_ids) == 1
print("FIX_CONFIRMED: exact original input retains UNKNOWN in both n10/rank10 quantiles")
