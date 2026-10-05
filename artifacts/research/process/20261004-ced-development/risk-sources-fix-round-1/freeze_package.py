"""Freeze owned fix plus exact historical dependencies, never moving helpers."""

from __future__ import annotations

import ast
import difflib
import hashlib
import importlib.metadata
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "risk-sources-module"
FIRST = HERE.parent / "t9-actual-risk-source-design"
OWNED = {"src/cloud_edge_robot_arm/research/risk_sources.py", "tests/test_research_risk_sources.py"}


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write(name: str, value: object) -> None:
    (HERE / name).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


if (HERE / "source-hashes.json").exists():
    raise RuntimeError("Released source is immutable; create another round instead")
prior = json.loads((OLD / "source-hashes.json").read_bytes())
assert sha((OLD / "source-hashes.json").read_bytes()) == (
    "b8eedda6ef991631a175d8a9c0ee71c4f61e514a0b2a45f9ea92c50475b4cbe8"
)
extra_setup = json.loads((OLD / "independent-related-setup.json").read_bytes())
extra = extra_setup["extra_raw_file_hashes"]
extra_root = Path(extra_setup["separate_marker_raw_sources_from_prior_independent_overlay"])
allowed = {"src", "tests", "scripts", "configs", "assets", "artifacts", "pyproject.toml"}
payloads, origins = {}, {}
for name, digest in prior.items():
    # Historical environment/cache conftests are not transitive project inputs.
    if name.split("/")[0] not in allowed:
        continue
    frozen = (OLD / "source" / name).read_bytes()
    assert sha(frozen) == digest, name
    content = (ROOT / name).read_bytes() if name in OWNED else frozen
    payloads[name] = content
    origins[name] = "owned fix1" if name in OWNED else "original b8eed frozen source"
for name, digest in extra.items():
    content = (extra_root / name).read_bytes()
    assert sha(content) == digest, name
    assert name not in payloads or payloads[name] == content, name
    payloads[name] = content
    origins[name] = "independently frozen marker fixture, exact registered original hash"
cli = "scripts/calibrate_rgbd_risk.py"
first_manifest = json.loads((FIRST / "source-ref-hashes.json").read_bytes())
content = (FIRST / "source" / cli).read_bytes()
assert sha(content) == first_manifest[cli]
payloads[cli] = content
origins[cli] = "first T9 read-only design frozen source"
for name, content in sorted(payloads.items()):
    if name.endswith(".py"):
        ast.parse(content, filename=name)
    target = HERE / "source" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    assert target.read_bytes() == content
for name in OWNED:
    assert (ROOT / name).read_bytes() == payloads[name], name
manifest = {name: sha(content) for name, content in sorted(payloads.items())}
write("source-hashes.json", manifest)
write("source-origins.json", origins)
write("ownership.json", {
    "owned_files": sorted(OWNED),
    "read_only_references": sorted(set(payloads) - OWNED),
    "source_snapshot": "source", "source_count": len(payloads),
    "namespace_basis": "historical b8eed 373-file namespace, with only owned production replacement",
    "current_live_namespace_claim": False,
    "excluded_historical_environment_conftests": len(prior) - 477,
    "production_files_changed_elsewhere": [], "prior_releases_modified": [],
    "scope": "RAW_EXECUTION consistency only; no risk/formal/METHOD acceptance",
})
write("environment.json", {
    "versions": {name: importlib.metadata.version(name) for name in
                 ["numpy", "pydantic", "mujoco", "pytest", "ruff", "mypy"]},
    "source_ast_parse": "PASS", "collector_provider_capture_actions": 0,
    "compiler_operation": "MjModel.from_xml_string only, no MjData/mj_step/render in reader",
})
diff = []
for name in sorted(OWNED):
    diff.extend(difflib.unified_diff(
        (OLD / "source" / name).read_text().splitlines(keepends=True),
        payloads[name].decode().splitlines(keepends=True),
        fromfile="original/" + name, tofile="fix1/" + name,
    ))
(HERE / "review-package.diff").write_text("".join(diff))
for name, digest in manifest.items():
    assert sha((HERE / "source" / name).read_bytes()) == digest
print(json.dumps({"source_count": len(payloads), "owned": len(OWNED),
                  "bytes": sum(map(len, payloads.values())),
                  "manifest_sha256": sha((HERE / "source-hashes.json").read_bytes())}, sort_keys=True))
