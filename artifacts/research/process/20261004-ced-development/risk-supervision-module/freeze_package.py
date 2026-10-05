"""One-time immutable bounded supervision source and fixture closure."""
from __future__ import annotations

import ast
import difflib
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PRIOR = HERE.parent / "risk-sources-fix-round-2"
OWNED = {"src/cloud_edge_robot_arm/research/risk_supervision.py", "tests/test_research_risk_supervision.py"}

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def write(name: str, value: object) -> None:
    (HERE / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")

if (HERE / "source-hashes.json").exists():
    raise RuntimeError("Source release is immutable")
prior_bytes = (PRIOR / "source-hashes.json").read_bytes()
assert sha(prior_bytes) == "4ed1a5a571cfca7d43a77ca79c86964ec08da887e87663031df55078cbfac552"
prior = json.loads(prior_bytes)
imports = json.loads((HERE / "imported-production-paths.json").read_bytes())
assert not any(name.endswith(("visual_owner.py", "raw_episode_v3.py")) for name in imports)
names = sorted(set(prior) | set(imports) | OWNED | {"tests/test_research_admission.py"})
manifest, origins, diff = {}, {}, []
for name in names:
    if name in prior:
        assert sha((PRIOR / "source" / name).read_bytes()) == prior[name], name
    payload = (ROOT / name).read_bytes()
    if name.endswith(".py"):
        ast.parse(payload, filename=name)
    if name == "src/cloud_edge_robot_arm/research/risk_sources.py":
        assert sha(payload) == "0bf79e3ef94ee33fec9e3642b7c77f956efa6e1a1f015de17d567d0f585c983a"
    target = HERE / "source" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    manifest[name] = sha(payload)
    origins[name] = ("new owned file" if name in OWNED else "unchanged independently reviewed RAW fix2 reference" if name in prior and prior[name] == sha(payload) else "explicit current quiet read-only dependency")
    if name in OWNED:
        diff.extend(difflib.unified_diff([], payload.decode().splitlines(keepends=True), fromfile="/dev/null", tofile="new/" + name))
write("source-hashes.json", manifest)
write("source-origins.json", origins)
write("baseline-source-hashes.json", prior)
write("baseline.json", {"new_production_module_absent": "red-initial-missing-module.log and red-contract-missing-module.log", "qualified_missing_module_red_count": 23, "baseline_ref_manifest_sha256": sha(prior_bytes), "original_red_test_bytes_not_separately_archived": True})
write("ownership.json", {"owned_files": sorted(OWNED), "read_only_references": sorted(set(names) - OWNED), "source_count": len(names), "source_snapshot": "source", "namespace_basis": "Reviewed RAW fix2 511 paths with explicit current quiet read-only versions; 67 actual imports; owned2; concrete INITIAL test helper", "current_complete_live_namespace_claim": False, "excluded_unrelated_moving_new_files": ["src/cloud_edge_robot_arm/repositories/event_autonomy/visual_owner.py", "src/cloud_edge_robot_arm/research/raw_episode_v3.py"], "prior_releases_modified": [], "actual_source_acceptance": "UNKNOWN", "scope": "diagnostic reconstruction, not actual risk admission"})
write("environment.json", {"python": platform.python_version(), "platform": platform.platform(), "packages": {name: importlib.metadata.version(name) for name in ("numpy", "pydantic", "mujoco", "Pillow", "opencv-contrib-python-headless", "pytest", "ruff", "mypy")}})
(HERE / "review-package.diff").write_text("".join(diff))
for name, digest in manifest.items():
    assert sha((HERE / "source" / name).read_bytes()) == digest, name
    assert sha((ROOT / name).read_bytes()) == digest, name
print(json.dumps({"source_count": len(manifest), "owned": len(OWNED), "source_manifest_sha256": sha((HERE / "source-hashes.json").read_bytes())}, indent=2))
