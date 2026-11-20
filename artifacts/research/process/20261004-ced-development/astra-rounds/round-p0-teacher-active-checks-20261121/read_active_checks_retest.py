"""Read fresh active-check retest evidence using the frozen independent reader logic."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from hashlib import sha256
from importlib import util
from pathlib import Path
from types import ModuleType
from typing import Any

ASSIGNMENT = "native-dev-whole-action-20261121-0001"
OWNER = "whole-action-egl-active-checks-development-20261121"
PARENT_SHA = "5413b71737266d49098d144bb562ec05b183534c9b1b6d25b788dafcb76b78b0"
PRIOR = Path(__file__).resolve().parent.parent / "round-p0-teacher-whole-action-20261120"


def load_reader(name: str) -> ModuleType:
    path = PRIOR / f"{name}.py"
    spec = util.spec_from_file_location(f"active_checks_{name}", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"missing independent reader {name}")
    reader = util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    return reader


def physical_reader() -> ModuleType:
    reader = load_reader("read_whole_evidence")
    # Only this unregistered module instance is bound to the new development identity.
    reader.ASSIGNMENT = ASSIGNMENT
    reader.PARENT_FREEZE_SHA256 = PARENT_SHA
    return reader


def validate_identity(release: Path, reader: ModuleType) -> tuple[str, Path]:
    require, read_json = reader.require, reader.read_json
    owner = release.parent
    source = owner / "source"
    require(
        release.name == "release" and owner.name == OWNER,
        "the fixed active-checks retest release is required",
    )
    protocol = read_json(release, "protocol.json")
    claim = read_json(release, "diagnostic-claim.json")
    registration_sha = reader.registration(protocol, claim, release)
    begin = read_json(owner, "worker-begin.json")
    process = read_json(owner, "process-begin.json")
    end = read_json(owner, "process-end.json")
    require(
        begin["assignment_id"] == ASSIGNMENT
        and begin["scope"] == reader.SCOPE
        and begin["registration_sha256"] == registration_sha
        and type(begin["pid"]) is int
        and begin["pid"] == process["pid"] == end["pid"]
        and process["cwd"] == str(source)
        and process["registration_file_sha256"]
        == end["registration_file_sha256"]
        == reader.sha_file(reader.original(release, "protocol.json"))
        and process["freeze_sha256"]
        == end["freeze_sha256"]
        == reader.sha_file(reader.original(owner, "source-freeze.json"))
        and protocol["expected_environment"]["source_root"] == str(source),
        "process, claim, source and fixed active-checks registration do not join",
    )
    return registration_sha, source


def sqlite_accounting(sql: dict[str, Any], timing: dict[str, Any], require: Any) -> dict:
    fields = (
        "reads_attempted",
        "reads_completed",
        "readonly_snapshots",
        "read_wall_ns",
        "action_reads_attempted",
        "action_reads_completed",
        "action_read_wall_ns",
    )
    require(
        all(type(sql.get(k)) is int and sql[k] >= 0 for k in fields)
        and sql["mode"] == "UTC_LEGACY_VETO",
        "SQLite diagnostic receipt has invalid checkpoint counts or clock mode",
    )
    counts = timing["span_count_by_label"]
    require(
        sql["reads_attempted"] == counts.get("sqlite", 0) <= counts.get("owner_check", 0)
        and sql["reads_attempted"] >= sql["readonly_snapshots"] >= sql["reads_completed"]
        and sql["reads_attempted"] >= sql["action_reads_attempted"] >= sql["action_reads_completed"]
        and sql["reads_completed"] >= sql["action_reads_completed"]
        and sql["read_wall_ns"] >= sql["action_read_wall_ns"],
        "SQLite diagnostic receipt differs from original check spans",
    )
    return {
        **{key: sql[key] for key in ("mode", *fields)},
        "recorded_sqlite_spans": counts.get("sqlite", 0),
        "recorded_owner_check_spans": counts.get("owner_check", 0),
    }


def pre_post_span_counts(release: Path, timing: dict, reader: ModuleType) -> dict | None:
    if not timing["reached_original_post"]:
        return None
    source = reader.original(release / "run/originals", "whole-action-timing.json")
    raw = source.read_bytes()
    reader.require(
        sha256(raw).hexdigest() == timing["trace_sha256"],
        "verified timing original changed before independent window counting",
    )
    trace = json.loads(raw)
    start = timing["marks"]["pre_start"]["ns"]
    stop = timing["marks"]["post_context"]["ns"]
    return dict(
        Counter(
            row["label"]
            for row in trace["spans"]
            if start <= row["start_ns"] <= row["end_ns"] <= stop
        )
    )


def read(release: Path, mode: str) -> dict:
    reader = physical_reader()
    registration_sha, source = validate_identity(release, reader)
    if mode == "physical":
        return reader.read_run(release, source)
    lifecycle = reader.read_json(release / "run", "collection-result.json")
    final = lifecycle["whole_action_diagnostic"]
    recipe = reader.read_json(release, "protocol.json")["recipe"]
    source_closure = reader.verify_outer_source(release, source, recipe, registration_sha)
    imports = reader.base.verify_imports(release / "run", source, registration_sha)
    reader.require(
        lifecycle["assignment_id"] == ASSIGNMENT
        and lifecycle["scope"] == reader.SCOPE
        and final["registration_sha256"] == registration_sha,
        "timing lifecycle belongs to another release",
    )
    timing = load_reader("read_whole_action_timing").read_run(release)
    return {
        **timing,
        "assignment_id": ASSIGNMENT,
        "registration_sha256": registration_sha,
        "source_closure": source_closure,
        "actual_imports": imports,
        "sqlite_checkpoint_accounting": sqlite_accounting(final["sqlite"], timing, reader.require),
        "pre_post_fully_contained_spans": pre_post_span_counts(release, timing, reader),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    parser.add_argument("mode", choices=("physical", "timing"))
    args = parser.parse_args()
    try:
        report = read(args.release.absolute(), args.mode)
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, allow_nan=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
