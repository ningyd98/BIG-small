"""Verify the replacement readback registration without opening the paid probe."""

import ast
import copy
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
from pathlib import Path
from unittest.mock import patch

import probe_scope as scope
import run_paid_probe as paid
from scripts import probe_rgbd_roles as roles

REVISION = scope.PLAN["reader_rebinding"]
FIELD = REVISION["allowed_file"]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def revision_source(commit):
    return subprocess.check_output(["git", "show", f"{commit}:{FIELD}"], cwd=scope.ROOT)


def split_function(source, name):
    (node,) = [
        n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name
    ]
    lines = source.splitlines(keepends=True)
    function = b"".join(lines[node.lineno - 1 : node.end_lineno])
    remainder = b"".join(lines[: node.lineno - 1] + lines[node.end_lineno :])
    return function, remainder


def validate_transition(old, new):
    previous, replacement = dict(old), dict(new)
    replacement.pop("reader_rebinding")
    previous["execution_base"] = scope.PLAN["execution_base"]
    pins = dict(previous["source_sha256"])
    pins[FIELD] = REVISION["current_reader_sha256"]
    previous["source_sha256"] = pins
    scope.require(
        previous == replacement, "changed scope, path, budget or an unauthorized source pin"
    )


def denied(action, text):
    try:
        action()
    except ValueError as error:
        scope.require(text in str(error), "the intended negative control did not reject")
    else:
        raise ValueError("expected a registration rejection")


def older_scope(path):
    spec = importlib.util.spec_from_file_location("previous_nominal_probe_scope", path)
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    return previous


def run():
    scope.require(
        os.environ["B0_OUTER_NET_NS"] != os.readlink("/proc/self/ns/net")
        and {
            ln.split(":", 1)[0].strip() for ln in Path("/proc/net/dev").read_text().splitlines()[2:]
        }
        == {"lo"},
        "a separate network namespace with only a loopback interface is required",
    )
    previous_path = scope.ROOT / REVISION["previous_plan"]
    scope.require(
        scope.sha(previous_path) == REVISION["previous_plan_sha256"],
        "previous registration changed",
    )
    previous = json.loads(previous_path.read_bytes())
    validate_transition(previous, scope.PLAN)
    for key, value in (
        ("current_nominal_real_output", "unregistered-output"),
        ("historical_nominal_attempts", 5),
        ("source_sha256", scope.PLAN["source_sha256"] | {"scripts/probe_rgbd_roles.py": "1" * 64}),
    ):
        candidate = copy.deepcopy(scope.PLAN)
        candidate[key] = value
        denied(
            lambda candidate=candidate: validate_transition(previous, candidate), "changed scope"
        )
    for name, expected in REVISION["unchanged_entry_sha256"].items():
        scope.require(
            scope.sha(previous_path.with_name(name)) == scope.sha(scope.HERE / name) == expected,
            "registered entry code was modified",
        )
    scope.require(
        Path(scope.__file__).parent.resolve() == Path(paid.__file__).parent.resolve() == scope.HERE,
        "probe entry resolved to a different registry",
    )
    old_source = revision_source(REVISION["previous_worktree_head"])
    new_source = revision_source(scope.PLAN["execution_base"])
    scope.require(
        digest(old_source) == REVISION["previous_reader_sha256"] == previous["source_sha256"][FIELD]
        and digest(new_source) == REVISION["current_reader_sha256"]
        and (scope.ROOT / FIELD).read_bytes() == new_source,
        "unregistered actual reader bytes",
    )
    old_func, old_remainder = split_function(old_source, REVISION["allowed_function"])
    new_func, new_remainder = split_function(new_source, REVISION["allowed_function"])
    scope.require(
        old_func != new_func and old_remainder == new_remainder,
        "reader change exceeds audited boundary",
    )
    nom_old = split_function(old_source, "verify_role_probe_evidence")[0]
    nom_new = split_function(new_source, "verify_role_probe_evidence")[0]
    scope.require(nom_old == nom_new, "nominal independent probe reader changed")
    prior_scope = older_scope(previous_path.with_name("probe_scope.py"))
    denied(prior_scope.preflight_inputs, "source changed: " + FIELD)
    history, report = scope.preflight_inputs()
    config = roles.read_role_config(paid.CONFIG)
    accepted = json.loads((scope.ROOT / scope.PLAN["current_preflight_public"]).read_bytes())
    role_map = {
        "cloud": roles.source_fingerprints(),
        "edge": roles._hash_sources(config["edge"]["source_paths"]),
        "device": roles._hash_sources(config["device"]["source_paths"]),
    }
    scope.require(role_map == accepted["active_role_fingerprints"], "nominal source maps changed")
    scope.require(
        report["probe_config"] == config["probe"]
        and config["probe"]["warm_runs"] == 3
        and len(report["attempts"]) == scope.MAX_SENDS == prior_scope.MAX_SENDS == 4,
        "bulk probe reservation differs",
    )
    scope.require(
        paid.OUTPUT == prior_scope.ROOT / prior_scope.PLAN["current_nominal_real_output"]
        and paid.LOCK == scope.ROOT.parents[2] / "cache/research/raw/nominal-role-probe.lock"
        and paid.EGL
        == scope.ROOT / "experiments/results/g1-visibility-pose-repair-20261124/egl.lock"
        and paid.EGL.is_file()
        and not paid.OUTPUT.exists()
        and not any(paid.OUTPUT.parent.glob("current-source-*")),
        "real nominal slot or shared locks changed or were used",
    )
    dry = scope.ROOT / "cache/research/raw/20261126-b0-role-preflight/current-wire-01/selection"
    scope.require(
        scope.sha(dry / "assignments.json") == scope.PLAN["dry_selection_sha256"]
        and len(json.loads((dry / "results.json").read_bytes())) == 480
        and all(
            row["status"] == "NOT_EXECUTED" and row["cloud_requests"] == 0
            for row in json.loads((dry / "results.json").read_bytes())
        ),
        "dry allocation no longer matches originals",
    )
    out = scope.ROOT / REVISION["private_offline_receipt"]
    out.parent.mkdir(parents=True, exist_ok=True)
    scope.write_once(
        out,
        {
            "preflight_passed": True,
            "old_preflight_rejection_expected": True,
            "new_reader_sha256": digest(new_source),
            "unchanged_nominal_reader_function_sha256": digest(nom_new),
            "new_ced_case_reader_function_sha256": digest(new_func),
            "unchanged_reader_remainder_sha256": digest(old_remainder),
            "new_plan_sha256": scope.sha(scope.PLAN_PATH),
            "old_plan_sha256": scope.sha(previous_path),
            "entry_code_sha256": REVISION["unchanged_entry_sha256"],
            "historical_probe_count": len(list(history.glob("attempt-*"))),
            "unexecuted_assignment_count": 480,
            "assignment_sha256": scope.sha(dry / "assignments.json"),
            "paid_batch_started": False,
            "paid_reservations": 0,
            "new_captures": 0,
            "actual_cloud_requests": 0,
            "actual_b0": 0,
            "formal_g2": 0,
            "hardware": 0,
        },
    )


def deny(*args, **kwargs):
    raise AssertionError("source registration check must stay offline")


if __name__ == "__main__":
    with patch.multiple(socket.socket, connect=deny, connect_ex=deny):
        run()
