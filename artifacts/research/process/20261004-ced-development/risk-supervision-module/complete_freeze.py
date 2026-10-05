"""Complete artifact metadata after the preserved OpenCV distribution lookup failure."""
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
manifest = json.loads((HERE / "source-hashes.json").read_bytes())
owned = json.loads((HERE / "ownership.json").read_bytes())["owned_files"]
for name, digest in manifest.items():
    assert hashlib.sha256((HERE / "source" / name).read_bytes()).hexdigest() == digest, name
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    if name.endswith(".py"):
        ast.parse((HERE / "source" / name).read_bytes(), filename=name)
packages = {name: importlib.metadata.version(name) for name in ("numpy", "pydantic", "mujoco", "Pillow", "pytest", "ruff", "mypy")}
packages.update({dist.metadata["Name"]: dist.version for dist in importlib.metadata.distributions() if "opencv" in dist.metadata.get("Name", "").lower()})
(HERE / "environment.json").write_text(json.dumps({"python": platform.python_version(), "platform": platform.platform(), "packages": packages, "reader_operations": "read files, decode existing RGBD, MjModel compile constants; no MjData/step/render/capture/provider or actual training", "preserved_setup_failure": "freeze-result.log unavailable opencv-contrib-python-headless metadata name", "source_manifest_not_overwritten": True}, indent=2, sort_keys=True) + "\n")
diff = []
for name in owned:
    diff.extend(difflib.unified_diff([], (HERE / "source" / name).read_text().splitlines(keepends=True), fromfile="/dev/null", tofile="new/" + name))
(HERE / "review-package.diff").write_text("".join(diff))
print(json.dumps({"source_count": len(manifest), "owned": len(owned), "source_manifest_sha256": hashlib.sha256((HERE / "source-hashes.json").read_bytes()).hexdigest(), "all_source_copies_live_hashes_ast": "PASS"}, indent=2))
