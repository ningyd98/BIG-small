"""Resume only unused R439 stages after the reviewed, exact source overlay is frozen."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
ROUND = Path(__file__).resolve().parents[1]
BASE = ROUND.parent


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def pin(name):
    path = ROOT / name
    if not path.is_file() or path.is_symlink():
        raise ValueError("required regular source missing: " + name)
    raw = path.read_bytes()
    return dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def run(stage):
    commands_path = ROUND / "implementation/commands-r453.json"
    commands = load(commands_path)
    if stage not in ("prepare", "first-full", "independent-read"):
        raise ValueError("only original unused prepare/full/read stages may resume")
    overlay_path = ROUND / "implementation/source-overlay-r453.json"
    overlay = load(overlay_path)
    if overlay["status"] != "SCOPED_REVIEW_ACCEPTED_SOFTWARE_VALIDATED":
        raise ValueError("reviewed source overlay unavailable")
    for row in overlay["files"]:
        if pin(row["path"]) != row:
            raise ValueError("frozen source or evidence changed: " + row["path"])
    if stage != "prepare":
        prepared = load(ROUND / "validation/prepare/result.json")
        if prepared["returncode"] != 0 or not prepared["reaped"] or prepared["source_drift"]:
            raise ValueError("fresh reviewed protocol preparation did not pass")
    if stage == "first-full":
        # This evidence is written only after an explicit human response and the
        # R450 host checks/one permitted stop. Its absence never authorizes a stop.
        prerequisites = load(
            BASE / "round450-gpu-exclusivity-precondition-20261108/implementation/actual-preconditions.json"
        )
        if prerequisites["status"] != "ACTUAL_PRECONDITIONS_PASSED":
            raise ValueError("R450 actual prerequisites and service authorization unavailable")
    if stage == "independent-read":
        collected = load(ROUND / "validation/first-full/result.json")
        if not collected["launched"] or not collected["reaped"] or collected["remaining_live"]:
            raise ValueError("sole collection process must exit and be reaped before readout")
    directory = ROUND / "validation" / stage
    directory.mkdir(parents=True, exist_ok=False)
    template = load(BASE / "round425-t7b-completion-kernel-20261104/validation/green/spec.json")
    env = {
        key: value.replace(template["directory"], str(directory))
        for key, value in template["env"].items()
        if not key.startswith("R424_") and key != "SIMULATION_RUNTIME_DB"
    }
    for key in (
        "TMPDIR", "XDG_CACHE_HOME", "BIGSMALL_R158_T2_RESOURCE_DIR",
        "BIGSMALL_R175_RESOURCE_DIR", "BIGSMALL_R223_RESOURCE_ROOT",
        "BIGSMALL_R223_CASE_ROOT", "DASHBOARD_ARTIFACT_ROOT",
    ):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    current = {row["path"]: row for row in overlay["files"]}
    for path in (Path(__file__), commands_path, overlay_path):
        name = str(path.relative_to(ROOT))
        current[name] = pin(name)
    save(directory / "preflight/runtime-source-pins.json", dict(files=list(current.values())))
    save(directory / "preflight/generation.json", dict(
        source_generation=overlay["source_generation"], unplanned_drift=[],
        original_baseline_sha256=overlay["original_baseline_sha256"],
        approved_rounds=overlay["approved_rounds"],
    ))
    argv = list(commands[stage]["argv"])
    argv[0] = str(ROOT / argv[0])
    save(directory / "spec.json", dict(
        id="r439-" + stage, directory=str(directory), cwd=str(ROOT), argv=argv,
        env=env, nodes=[], ports=[], timeout_s=commands[stage]["timeout_s"], attempt=1,
        scope="R439_TEACHER_COLLECTION_ONLY_REVIEWED_SOURCE_OVERLAY",
    ))
    definition = importlib.util.spec_from_file_location(
        "r439_future_bounded", BASE / "round413-full-long-validation-20261103/bounded_stage.py"
    )
    supervisor = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(supervisor)
    supervisor.ROUND = directory
    supervisor.run(directory / "spec.json")


if __name__ == "__main__":
    run(sys.argv[1])
