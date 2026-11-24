"""Bind the 130 mm contact repair to its verified 115 mm software and fresh geometry screen."""

from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.graduation import g1_visibility_mount_runtime as mount
from scripts.graduation import g1_visibility_radial as fixture
from scripts.graduation import g1_visibility_runtime as build
from scripts.graduation.g1_formal_runtime import require
from scripts.graduation.perception_io import pinned, sha

PARENT = "f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892"
PARENT_PREFLIGHT = "8e12a9e9ab1417c43d9ed5a2f98f30ee41f572225838f1bfbaa55073d7bebe01"
PLAN_SHA = "6a8eb89a5609a01dbbd5560c28a5379b95b72c7061522299185c7ced94fc3d9c"
DIRECTORY = build.ROUNDS / "round-g1-radial30-contact-20261125"
SCREEN = DIRECTORY / "screen-selection.public.json"
# The author of the independent geometry screen publishes before generation creation.
SCREEN_SHA = "4625888d3a356cbf7c856517240a3e1c37cadaa13ee27a6ff1c2ded59ae90178"
MODULE = build.PREFIX + "g1_visibility_radial_contact.py"
ADAPTERS = (build.BUILDER, build.RUNNER, mount.ADAPTER)
ASSIGNMENTS = {"train-radial30-contact-d02-01": ["d02"], "train-radial30-contact-d01-01": ["d01"]}


def check_screen(record):
    fields = dict(
        schema="g1.visibility.radial30-screen-selection.v1",
        plan_sha256=PLAN_SHA,
        parent_generation=PARENT,
        candidate_offset_mm=30,
        selected_offset_mm=30,
        asset_sha256=mount.spec_for(30)["asset_sha256"],
        eligible=True,
        optical_anchors=31,
        matched_depth_inputs=31,
        dense_states=3432,
        optical_pass=True,
        clearance_pass=True,
        negative_controls_pass=True,
        unauthorized_contact_steps=0,
        unproved_separation_steps=0,
        zero_integrations=True,
    )
    require(
        all(type(record.get(k)) is type(v) and record[k] == v for k, v in fields.items()),
        "independent 130 mm optical, depth, contact or negative controls do not qualify",
    )


def check_identity(lock):
    binding = lock.get("radial_contact", {})
    require(
        SCREEN_SHA is not None
        and binding.get("screen_sha256") == SCREEN_SHA
        and binding.get("plan_sha256") == PLAN_SHA
        and lock.get("parent_runtime_build_sha256") == PARENT
        and lock.get("radial_assembly") == mount.spec_for(30),
        "130 mm slots require the current 130 mm qualification and generation",
    )


def qualification(repo, parent, requested_sha):
    require(
        SCREEN_SHA is not None and requested_sha == SCREEN_SHA,
        "unreleased 130 mm static screen or different generation",
    )
    plan = pinned(repo / DIRECTORY / "plan.json", PLAN_SHA)
    require(
        plan["parent_generation"] == PARENT
        and plan["only_new_offset_mm"] == 30
        and sha(repo / DIRECTORY / "plan.md") == plan["plan_md_sha256"],
        "wrong 130 mm plan",
    )
    for name, h in plan["inputs_sha256"].items():
        source = parent if name in ADAPTERS else repo
        require(sha(source / name) == h, "changed radial contact plan input: " + name)
    screen = pinned(repo / SCREEN, requested_sha)
    check_screen(screen)
    sources = screen["input_artifacts_sha256"]
    require(
        all(
            screen[k] in sources.values()
            for k in ("optical_summary_sha256", "clearance_summary_sha256")
        ),
        "130 mm optical or clearance summary missing",
    )
    for name, expected in sources.items():
        path = repo / name
        require(
            not Path(name).is_absolute()
            and path.resolve().is_relative_to(repo)
            and sha(path) == expected,
            "changed or foreign 130 mm static evidence: " + name,
        )
    return {
        key: screen[key]
        for key in ("plan_sha256", "optical_summary_sha256", "clearance_summary_sha256")
    } | {
        "screen_sha256": requested_sha,
        "screen_file": SCREEN.as_posix(),
        "parent_preflight_sha256": PARENT_PREFLIGHT,
    }


def overlays(repo, parent, prior, adapter_source=None):
    source = repo if adapter_source is None else adapter_source
    old, spec = mount.spec_for(15), mount.spec_for(30)
    files = prior["runtime_files_sha256"]
    fit = build.FIT_ROUND
    detector = {
        build.GRID: fit.grid_sha256,
        build.DETECTOR: build.TIMING_DETECTOR_FILES[build.DETECTOR],
    }
    require(
        prior["radial_assembly"] == old
        and build.issued_timing_round(prior) == fit
        and prior["detector_files_sha256"]
        == prior["radial_timing"]["detector_files_sha256"]
        == detector
        and all(sha(repo / name) == files[name] == digest for name, digest in detector.items())
        and sha(repo / fit.directory / "replay-release.public.json") == fit.release_sha256
        and sha(repo / fit.directory / "paired-budget.public.json") == fit.budget_sha256,
        "different 115 mm parent, observer or timing release",
    )
    name = spec["asset_path"]
    xml = fixture.build_xml((parent / mount.V2_XML).read_bytes(), 30)
    require(
        name not in files
        and MODULE not in files
        and files[old["asset_path"]] == old["asset_sha256"]
        and sha(repo / name) == hashlib.sha256(xml).hexdigest() == spec["asset_sha256"],
        "130 mm development asset bytes or inherited inventory differ",
    )
    provider = mount.replacement(
        (parent / build.ASSET).read_text(), "RADIAL_OFFSET_MM = 15\n", "RADIAL_OFFSET_MM = 30\n"
    ).encode()
    return name, {
        **{f: (source / f).read_bytes() for f in (*ADAPTERS, MODULE)},
        name: xml,
        build.ASSET: provider,
    }


def manifest(prior, updates, qualification):
    before = prior["runtime_files_sha256"]
    files = {**before, **{name: hashlib.sha256(data).hexdigest() for name, data in updates.items()}}
    return {
        **prior,
        "parent_runtime_build_sha256": PARENT,
        "radial_assembly": mount.spec_for(30),
        "radial_contact": qualification,
        "runtime_files_sha256": files,
        "source_changes": {
            name: {"before": before[name], "after": files[name]}
            for name in updates
            if name in before
        },
        "additional_files_sha256": {
            name: files[name]
            for name in set(prior["additional_files_sha256"]) | (files.keys() - before.keys())
        },
        "scorer_files_sha256": {name: files[name] for name in prior["scorer_files_sha256"]},
    }


def parent_inputs(repo, private, requested_sha, adapter_source=None):
    parent, prior = build.verify_build(private, PARENT)
    parent_preflight = pinned(parent.parent / "preflight.json", PARENT_PREFLIGHT)
    evidence = qualification(repo, parent, requested_sha)
    _, updates = overlays(repo, parent, prior, adapter_source)
    return parent, parent_preflight, updates, manifest(prior, updates, evidence)


def prepare(repo, private, requested_sha):
    parent, _, updates, lock = parent_inputs(repo, private, requested_sha)
    return build.install_build(private, parent, updates, lock)


def verify(repo, private, generation, lock):
    check_identity(lock)
    tree, sealed = build.verify_build(private, generation)
    parent, parent_preflight, _, expected = parent_inputs(repo, private, SCREEN_SHA, tree)
    require(lock == sealed == expected, "foreign 130 mm sources, scorer, static screen or parent")
    return parent, parent_preflight
