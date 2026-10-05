"""Freeze a numerical-only owner replacement over exact reviewed fix1 inputs."""

from __future__ import annotations

import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PRIOR = HERE.parent / "risk-sources-fix-round-1"
OWNED = {"src/cloud_edge_robot_arm/research/risk_sources.py", "tests/test_research_risk_sources.py"}


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write(name: str, value: object) -> None:
    (HERE / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


if (HERE / "source-hashes.json").exists():
    raise RuntimeError("Released source snapshot is immutable")
prior = json.loads((PRIOR / "source-hashes.json").read_bytes())
assert sha((PRIOR / "source-hashes.json").read_bytes()) == (
    "bb8cc8f658ebde7a8ec52d4702d8fc30d7470a4272c57ce8c5778fdd14270c1a"
)
manifest, diff = {}, []
for name, digest in prior.items():
    previous = (PRIOR / "source" / name).read_bytes()
    assert sha(previous) == digest, name
    payload = (ROOT / name).read_bytes() if name in OWNED else previous
    if name.endswith(".py"):
        ast.parse(payload, filename=name)
    target = HERE / "source" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    manifest[name] = sha(payload)
    if name in OWNED:
        diff.extend(difflib.unified_diff(
            previous.decode().splitlines(keepends=True),
            payload.decode().splitlines(keepends=True),
            fromfile="fix1/" + name, tofile="fix2/" + name,
        ))
write("source-hashes.json", manifest)
write("ownership.json", {
    "owned_files": sorted(OWNED), "read_only_references": sorted(set(prior) - OWNED),
    "source_count": len(prior), "source_snapshot": "source",
    "namespace_basis": "exact reviewed fix1/511 closure with only owned replacements",
    "current_live_namespace_claim": False,
    "prior_releases_modified": [], "production_files_changed_elsewhere": [],
    "scope": "narrow _number finite conversion boundary; no admission change",
})
write("source-origins.json", {
    name: "owned numerical fix2" if name in OWNED else "exact immutable fix1/511 reference"
    for name in prior
})
(HERE / "environment.json").write_bytes((PRIOR / "environment.json").read_bytes())
(HERE / "review-package.diff").write_text("".join(diff))
for name, digest in manifest.items():
    assert sha((HERE / "source" / name).read_bytes()) == digest
for name in OWNED:
    assert sha((ROOT / name).read_bytes()) == manifest[name]
print(json.dumps({"source_count": len(manifest), "owned": len(OWNED),
                  "source_manifest_sha256": sha((HERE / "source-hashes.json").read_bytes())}))
