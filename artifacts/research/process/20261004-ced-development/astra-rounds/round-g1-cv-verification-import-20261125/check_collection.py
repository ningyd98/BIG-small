"""Collect the delivery tests in either order, checking the source of each affected import."""

import hashlib
import importlib
import json
import sys
from pathlib import Path

import pytest
from scripts.graduation.perception_io import write

ROUNDS = Path(__file__).resolve().parent.parent.relative_to(Path.cwd())
PARENT = ROUNDS / "round-g1-cv-grasp-validation-20261125"
RESEARCH = [
    PARENT,
    ROUNDS / "round-g1-cv-static-mass-verification-20261125",
    ROUNDS / "round-g1-cv-sweep-route-binding-20261125",
    ROUNDS / "round-g1-cv-qualification-entry-20261125",
]
REGRESSION = [
    ROUNDS / "round-g1-general-cv-grasp-20261125/test_surface_pilot.py",
    *[
        Path("tests") / f"test_{name}.py"
        for name in (
            "graduation_g1_visibility_selection",
            "graduation_g1_visibility_radial_runtime",
            "rgbd_top_grasp",
            "graduation_g1_radial30_capture_admission",
            "graduation_g1_visibility_replay",
            "graduation_g1_visibility_vision",
            "graduation_g1_visibility_trials",
            "graduation_g1_visibility_radial_screen",
            "graduation_g1_visibility_deadline",
            "graduation_g1_visibility_radial",
            "molmo_point_association",
        )
    ],
]


class CheckSources:
    def __init__(self):
        self.result = None

    def pytest_collection_finish(self, session):
        nodes = [item.nodeid for item in session.items]
        assert len(nodes) == len(set(nodes)) == 245
        frozen_items = [i for i in session.items if i.path.name == "test_recovery_route_v2.py"]
        assert len(frozen_items) == 2 and all(
            type(i).__name__ == "FrozenTimingTest" for i in frozen_items
        )
        modules = {}
        for short in (
            "g1_visibility_selection",
            "g1_visibility_replay",
            "g1_visibility_radial_screen",
        ):
            name = "scripts.graduation." + short
            path = Path(importlib.import_module(name).__file__).resolve().relative_to(Path.cwd())
            assert path == Path("scripts/graduation") / (short + ".py")
            modules[name] = str(path)
        cached = [getattr(m, "__file__", None) for m in sys.modules.values()]
        assert not any("runtime-source" in Path(p).parts for p in [*sys.path, *cached] if p)
        self.result = dict(
            node_count=len(nodes),
            sorted_nodeids_sha256=hashlib.sha256(
                json.dumps(sorted(nodes), separators=(",", ":")).encode()
            ).hexdigest(),
            child_nodes=[i.nodeid for i in frozen_items],
            workspace_modules=modules,
            frozen_paths_or_module_files_in_parent=0,
        )


if __name__ == "__main__":
    order, output = sys.argv[1:]
    groups = {"research-first": RESEARCH + REGRESSION, "repository-first": REGRESSION + RESEARCH}
    check = CheckSources()
    status = pytest.main(
        ["--collect-only", "-q", "-p", "no:cacheprovider", *map(str, groups[order])],
        plugins=[check],
    )
    if status or check.result is None:
        raise SystemExit(status or 1)
    write(Path(output), {"order": order, **check.result})
