"""Run the real frozen CLI with all new allocations redirected to a temporary software fixture."""

import argparse
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.graduation import g1_dual_trials as dual
from scripts.graduation import g1_visibility_radial_contact as contact
from scripts.graduation import g1_visibility_runtime as build
from scripts.graduation import g1_visibility_trials as trials
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write


class Boundary(Exception):
    """Deliberate software stop at the entrance to the native collector."""


def cli(repo, *args):
    output = io.StringIO()
    with (
        patch.object(sys, "argv", ["trials", "--repo", str(repo), *args]),
        contextlib.redirect_stdout(output),
    ):
        trials.main()
    return output.getvalue().strip()


def replace(path, data):
    path.write_text(json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n")


def witness(repo, generation, scratch):
    private = repo / build.PRIVATE
    tree, lock = build.verify_build(private, generation)
    assert ROOT == tree == Path.cwd()
    pre = tree.parent / "preflight.json"
    assert pre.is_file() and not any(scratch.iterdir())
    gate = repo / contact.SCREEN
    options = ["--gate", str(gate), "--gate-sha", contact.SCREEN_SHA]
    expected_prior = contact.supersedes(repo, private)
    real_batch, real_device = trials.batch_path, trials.device
    events, results = [], {}

    @contextlib.contextmanager
    def local_device(_):
        events.append("scratch_device_lock")
        with real_device(scratch):
            yield

    def native_boundary(_plan, folder, digest, case_id, **kw):
        assert folder.is_relative_to(scratch) and callable(kw["before_start"])
        batch, frozen = kw["context"]()
        row = next(r for r in batch["cases"] if r["id"] == case_id)
        alloc, _ = kw["case_reader"](folder, batch, row)
        assert alloc["runtime_build_sha256"] == generation and frozen == lock
        assert not (folder / case_id / "attempt.json").exists()
        events.append("reached_native_before_reserve")
        raise Boundary("software boundary before reserve and worker")

    def refuses(name, function, expected=None):
        n = len(events)
        try:
            function()
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            assert not expected or expected in str(exc), (name, str(exc))
            assert len(events) == n, (name, events[n:])
            results[name] = (
                type(exc).__name__
                + ": "
                + str(exc).replace(str(scratch), "<SCRATCH>").replace(str(repo), "<REPO>")
            )
        else:
            raise AssertionError("expected refusal: " + name)

    with (
        patch.object(trials, "batch_path", lambda _, label: real_batch(scratch, label)),
        patch.object(trials, "device", local_device),
        patch.object(dual.g1_mount_trials, "capture", native_boundary),
    ):

        def issue(label, group, *opts):
            return cli(repo, "issue-training", generation, label, group, *opts)

        refuses(
            "old_generation_new_label",
            lambda: cli(
                repo, "issue-training", contact.PARENT, contact.REPLACEMENT, "d02", *options
            ),
            "130 mm",
        )
        refuses(
            "old_label",
            lambda: issue(contact.REJECTED_LABEL, "d02", *options),
            "old or unregistered",
        )
        refuses("wrong_group", lambda: issue(contact.REPLACEMENT, "d01", *options), "unregistered")
        refuses(
            "foreign_gate",
            lambda: issue(
                contact.REPLACEMENT,
                "d02",
                "--gate",
                str(repo / build.FIT_DIRECTORY / "replay-release.public.json"),
                "--gate-sha",
                build.FIT_ROUND.release_sha256,
            ),
            "screen",
        )
        stamped = issue(contact.REPLACEMENT, "d02", *options)
        folder = real_batch(scratch, contact.REPLACEMENT)
        original = pinned(folder / "allocation.json", stamped)
        assert original["supersedes"] == expected_prior

        def call(h):
            return cli(repo, "capture", generation, contact.REPLACEMENT, h, "d02")

        try:
            call(stamped)
        except Boundary:
            assert events[-1] == "reached_native_before_reserve"
        else:
            raise AssertionError("130 mm registration failed to reach the boundary")
        results["legal_d02"] = "reached native before reserve"
        assert (
            not (folder / "d02" / "attempt.json").exists()
            and not (folder / "d02" / "instance").exists()
        )
        refuses(
            "duplicate_allocation", lambda: issue(contact.REPLACEMENT, "d02", *options), "already"
        )
        refuses("wrong_allocation_digest", lambda: call("c" * 64), "SHA256")

        def mutated_batch(name, fields, error):
            replace(folder / "allocation.json", original | fields)
            refuses(name, lambda: call(sha(folder / "allocation.json")), error)
            replace(folder / "allocation.json", original)
            assert sha(folder / "allocation.json") == stamped

        mutated_batch("wrong_preflight", {"preflight_sha256": "1" * 64}, "preflight")
        mutated_batch("unregistered_copy_sha", {"gate_sha256": "2" * 64}, "screen")
        mutated_batch(
            "different_source_sha", {"gate_source_sha256": build.FIT_ROUND.release_sha256}, "screen"
        )
        mutated_batch("different_scoring_sources", {"scorer_files_sha256": {}}, "scorer")
        mutated_batch("missing_supersession", {"supersedes": None}, "predecessor")
        gate_copy = folder / "gate.json"
        original_gate = gate_copy.read_bytes()
        replace(gate_copy, read(gate_copy) | {"matched_depth_inputs": 30})
        refuses("tampered_copy", lambda: call(stamped), "SHA256")
        gate_copy.write_bytes(original_gate)
        case_file = folder / original["cases"][0]["allocation_file"]
        original_case = case_file.read_bytes()
        altered = read(case_file)
        altered["geometry"]["asset_path"] = "foreign.xml"
        replace(case_file, altered)
        refuses("foreign_case_asset", lambda: call(stamped), "SHA256")
        case_file.write_bytes(original_case)
        refuses(
            "d01_without_d02_score",
            lambda: issue("train-radial30-contact-d01-01", "d01", *options),
            "score.json",
        )
        assert not (folder / "d02" / "attempt.json").exists()
        assert not (folder / "d02" / "instance").exists()
    return dict(
        schema="g1.visibility.radial30.capture-boundary-software.v1",
        fixture_only=True,
        generation=generation,
        static_screen_sha256=contact.SCREEN_SHA,
        preflight_sha256=sha(pre),
        events=events,
        checks=results,
        allocated_synthetic_batches=1,
        real_batch_writes=0,
        attempts=0,
        physics_steps=0,
        worker_runs=0,
        on_disk_proof={
            "label": original["label"],
            "supersedes": original["supersedes"],
            "gate_sha256": original["gate_sha256"],
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("repo", type=Path)
    p.add_argument("generation")
    p.add_argument("output", type=Path)
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="g1-software-capture-") as tmp:
        report = witness(a.repo.resolve(), a.generation, Path(tmp))
    assert not a.output.exists()
    write(a.output, report)
    print(len(report["checks"]), sha(a.output))
