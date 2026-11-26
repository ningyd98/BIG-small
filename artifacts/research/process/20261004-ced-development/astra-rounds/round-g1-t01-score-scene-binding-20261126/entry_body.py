"""Exact inline child entry, independently attested beside the original module audit."""

import importlib.util
import json
import os
import sys
from hashlib import sha256
from pathlib import Path


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


registry, registry_hash, slot = sys.argv[1:]
registry = Path(registry).resolve()
require(digest(registry) == registry_hash, "recovery entry registry changed")
entry = json.loads(registry.read_bytes())
repo, tree, wrapper = (Path(entry[k]) for k in ("repo", "runtime_tree", "wrapper_path"))
inline = sys.orig_argv[sys.orig_argv.index("-c") + 1]
require(
    sha256(inline.encode()).hexdigest() == entry["inline_launch_sha256"]
    and digest(Path(entry["inline_source_path"])) == entry["inline_launch_sha256"]
    and digest(wrapper) == entry["wrapper_sha256"]
    and digest(tree / "runtime-build.json") == entry["runtime_sha256"]
    and Path.cwd().resolve() == tree
    and Path(sys.executable) == Path(entry["interpreter"]),
    "inline entry, runtime, wrapper or interpreter differs",
)
sources = {wrapper: entry["wrapper_sha256"]}


def independently_loaded_modules():
    found = {}
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if path.is_relative_to(repo) and not path.is_relative_to(tree):
            require(
                name == entry["wrapper_module_name"]
                and path in sources
                and digest(path) == sources[path],
                f"unregistered local recovery module: {name}",
            )
            found[name] = {"path": str(path), "sha256": sources[path]}
    return found


require(not independently_loaded_modules(), "unexpected preloaded recovery module")
spec = importlib.util.spec_from_file_location(entry["wrapper_module_name"], wrapper)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.OUT = registry.parent
sys.argv = [str(wrapper), slot]
module.main()
final = independently_loaded_modules()
require(
    len(final) == 1
    and digest(registry) == registry_hash
    and digest(Path(entry["inline_source_path"])) == entry["inline_launch_sha256"]
    and digest(Path(entry["supervisor_path"])) == entry["supervisor_sha256"]
    and digest(tree / "runtime-build.json") == entry["runtime_sha256"],
    "recovery program or frozen source changed during cold read",
)
area = registry.parent / slot
raw = json.loads((area / "result.json").read_bytes())
project = raw["cold_join_loaded_sources"]
require(
    project["scripts.graduation.g1_clearance_score"]["sha256"] == entry["frozen_scorer_sha256"]
    and project["scripts.graduation.g1_dual_observer"]["sha256"] == entry["frozen_observer_sha256"],
    "frozen project audit missing the original reader or detector",
)
with (area / "external-source-audit.json").open("x") as output:
    json.dump(
        {
            "pid": os.getpid(),
            "registry_sha256": registry_hash,
            "inline_launch_sha256": entry["inline_launch_sha256"],
            "runtime_sha256": entry["runtime_sha256"],
            "entry_condition": "development_recovery_with_both_source_manifests",
            "executed_wrapper_argv": sys.argv,
            "external_local_imports": final,
            "project_audit_sha256": sha256(
                json.dumps(project, sort_keys=True).encode()
            ).hexdigest(),
            "result_sha256": digest(area / "result.json"),
        },
        output,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    output.write("\n")
