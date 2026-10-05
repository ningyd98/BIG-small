"""Preserved counterexample replay; SOFTWARE_ONLY, no native authority or data."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
source = BASE / "task2-independent-source-link-probe.py"
data = source.read_bytes()
assert hashlib.sha256(data).hexdigest() == "8098bf98b4faa7f953e76c90cedf2b87b96c3d957be7bfd4992aa6b960be0d3f"
text = data.decode()
assert text.count('assert group.status == "COMPLETE"') == 1
text = text.replace('assert group.status == "COMPLETE"', 'assert group.status == ("INCOMPLETE" if kind == "post_capture_preregistration" else "INVALID")\n        assert result.assigned_group_count == result.independent_group_count == result.geometry_quantile.group_count == result.action_quantiles["MOVE_ABOVE"].group_count == 1\n        assert group.geometry_error_m is None\n        assert len(result.geometry_quantile.unavailable_group_ids) == 1')
namespace = {"__name__": "independent_replay", "__file__": str(source)}
exec(compile(text, str(source), "exec"), namespace)
for kind in ("original_producer_drift", "original_asset_mismatch", "post_capture_preregistration"):
    print(json.dumps(namespace["probe"](kind), sort_keys=True))

fixed = BASE / "fix-round-1/independent-fix-probe.py"
print("preserved_component_collision_replay:")
exec(compile(fixed.read_text(), str(fixed), "exec"), {"__name__": "independent_replay", "__file__": str(fixed)})
