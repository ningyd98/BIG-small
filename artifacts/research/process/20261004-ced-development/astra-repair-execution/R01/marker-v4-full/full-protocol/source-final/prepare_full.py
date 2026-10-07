"""One exclusive full-horizon freeze; preparation never constructs a simulator."""

from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import math
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
DEV = ROOT / "artifacts/research/process/20261004-ced-development"
SPARSE = HERE.parent / "marker-v4-preparation"
OLD = DEV / "t7b-continuous-visibility-v3/fix-round-1/attempt-1"
PLAN = DEV / "astra-rounds/round57-marker-full/plan.json"
PLAN_SHA = "239eaf116f1a674be355cef8453bcdc97b3f48ce19c3b9206abcdc106cb7eeb6"
PROTOCOL = "research.custom-full-guarded-marker-v4.v1"
SCOPE = "EXCLUDED_SAME_COMPONENT_FULL_MARKER_V4_DEVELOPMENT"
ASSET_SHA = "045ce032032426ec6130348ee75e5f53b7db02699fc1f39558727edd63f67e0d"
CONTRACT_DIGEST = "16bfd83aa42ba257b2b3932335fdf8d1fdab423c513102a5fa9cbdee53450c99"
OWNED = ("prepare_full.py", "run_full_once.py", "verify_full.py", "test_cpu.py")
RESOURCE = dict(
    capture_wall_limit_s=3600,
    reader_wall_limit_s=1800,
    peak_rss_limit_bytes=4 * 1024**3,
    minimum_available_ram_bytes=6 * 1024**3,
    minimum_free_disk_bytes=16 * 1024**3,
    output_budget_bytes=4 * 1024**3,
    failure_free_disk_reserve_bytes=1024**3,
    max_frame_json_bytes=8 * 1024**2,
    max_journal_record_bytes=16 * 1024**2,
)
NONPROMOTION = dict(
    formal_accepted=False,
    native_admission="NOT_PROMOTED",
    source_authenticity="UNKNOWN",
    independent_calibration_group=False,
    continuous_motion="NOT_CERTIFIED",
    continuous_visibility="NOT_ESTABLISHED",
    future_stability="UNAVAILABLE",
    geometric_error_bound_m=None,
    angular_velocity_bound_rad_s=None,
    stability_status="UNKNOWN",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def hash_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def same(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(
        b, sort_keys=True, allow_nan=False
    )


def require(value, reason):
    if not value:
        raise ValueError(reason)


def finite(value):
    return type(value) in {int, float} and math.isfinite(value)


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def load_pinned(path, expected, name):
    path = Path(path).resolve(strict=True)
    require(hash_file(path) == expected, "pinned source differs: " + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    require(
        Path(module.__file__).resolve() == path and Path(module.__spec__.origin).resolve() == path,
        "loaded pinned module origin differs",
    )
    return module


def plan_data():
    require(hash_file(PLAN) == PLAN_SHA, "Astra plan changed")
    return json.loads(PLAN.read_text())


def decoder_environment():
    files, versions = {}, {"python_version": sys.version.split()[0]}
    for name, package in (
        ("cv2", "opencv-python-headless"),
        ("PIL", "Pillow"),
        ("pydantic", "pydantic"),
        ("pydantic_core", "pydantic_core"),
    ):
        module = importlib.import_module(name)
        path = Path(module.__file__).resolve(strict=True)
        require(Path(module.__spec__.origin).resolve() == path, "decoder module origin differs")
        files[name + "/entry"] = {"path": str(path), "sha256": hash_file(path)}
        versions[name + "_version"] = importlib.metadata.version(package)
    cv2 = importlib.import_module("cv2")
    binaries = list(Path(cv2.__file__).parent.glob("cv2*.so"))
    require(len(binaries) == 1, "unique OpenCV binary required")
    for key, path in (
        ("cv2/binary", binaries[0]),
        ("python/executable", Path(sys.executable).resolve()),
        ("PIL/_imaging", Path(importlib.import_module("PIL._imaging").__file__)),
        (
            "pydantic_core/binary",
            Path(importlib.import_module("pydantic_core._pydantic_core").__file__),
        ),
    ):
        files[key] = {"path": str(path.resolve()), "sha256": hash_file(path)}
    return {"files": files, **versions}


def make_full_header():
    template = json.loads((SPARSE / "fix-round-1/pilot-protocol/header.json").read_text())
    h = {
        k: copy.deepcopy(v)
        for k, v in template.items()
        if not k.startswith("sparse_")
        and not k.startswith("selected_")
        and k
        not in {
            "selection_manifest_sha256",
            "total_render_pass_estimate",
            "initial_pilot_header_sha256",
        }
    }
    h["scene"]["group_id"] = "dev-marker-v4-full-" + h["scene_hash"][:24]
    h["environment"].update({k: v for k, v in decoder_environment().items() if k != "files"})
    h["environment"]["files"].update(decoder_environment()["files"])
    report_path = HERE.parent / "report.json"
    report = json.loads(report_path.read_text())
    h["original_action_spans"] = [
        {k: r[k] for k in ("ordinal", "action", "start_step_exclusive", "end_step_inclusive")}
        for r in report["action_status_inventory"]
    ]
    h["original_action_spans_source"] = {
        "path": str(report_path.relative_to(ROOT)),
        "sha256": hash_file(report_path),
    }
    h.update(NONPROMOTION)
    h.update(
        protocol=PROTOCOL,
        scope=SCOPE,
        expected_physics_steps=4806,
        expected_physics_steps_is_admission_gate=True,
        expected_frame_count=4807,
        expected_callback_steps=list(range(4807)),
        attempt_limit=1,
        reader_decode_attempt_limit=1,
        capture_policy="STEP_ZERO_AND_EVERY_REAL_PHYSICS_END",
        range_policy="RETAIN_ALL_ACTUAL_CALLBACKS_REQUIRE_EXACT_ORIGINAL_HORIZON",
        index_schema="research.full-marker-v4-index.v1",
        readout_schema="research.full-marker-v4-readout.v1",
        guard_snapshot_contract_digest=CONTRACT_DIGEST,
        expected_commands=743,
        expected_dwells=2,
        resource_policy=copy.deepcopy(RESOURCE),
        time_domain="SimulationS_SAME_EPISODE_SAVED_SIM_TIME",
        full_capture_render_pass_budget=9614,
        full_source_freeze_round=57,
        astra_plan_sha256=PLAN_SHA,
        old_full_marker_denominator=4807,
        sparse_subgroup_denominator=201,
    )
    return h


def validate_full_header(header):
    expected = make_full_header()
    for key in (
        "protocol",
        "scope",
        "capture_policy",
        "range_policy",
        "index_schema",
        "readout_schema",
        "asset_sha256",
        "guard_core_sha256",
        "guard_binding_sha256",
        "guard_headers",
        "guard_snapshot_contract_digest",
        "raw_v3_status",
        "scene",
        "scene_hash",
        "config",
        "marker_registration",
        "marker_local_attachment_m",
        "environment",
        "resource_policy",
        "expected_callback_steps",
        "time_domain",
        "astra_plan_sha256",
        "original_action_spans",
        "original_action_spans_source",
    ):
        require(same(header.get(key), expected[key]), "frozen full header differs: " + key)
    for key, value in (
        ("expected_physics_steps", 4806),
        ("expected_frame_count", 4807),
        ("attempt_limit", 1),
        ("reader_decode_attempt_limit", 1),
        ("settle_steps", 120),
        ("planned_teacher_actions", 9),
        ("expected_commands", 743),
        ("expected_dwells", 2),
    ):
        require(
            type(header.get(key)) is int and header[key] == value,
            "exact integer full contract differs: " + key,
        )
    require(
        header.get("expected_physics_steps_is_admission_gate") is True,
        "exact horizon gate required",
    )
    require(
        finite(header.get("original_max_sample_gap_s"))
        and header["original_max_sample_gap_s"] == 0.005,
        "strict SimulationS gap contract required",
    )
    require(all(type(s) is int for s in header["expected_callback_steps"]), "bool step forbidden")
    for key, value in NONPROMOTION.items():
        require(same(header.get(key), value), "nonpromotion field changed: " + key)


def resource_measurement(path):
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            memory["available_ram_bytes"] = int(line.split()[1]) * 1024
    memory["free_disk_bytes"] = shutil.disk_usage(Path(path)).free
    return memory


def require_resources(path):
    measurement = resource_measurement(path)
    require(
        measurement["available_ram_bytes"] >= RESOURCE["minimum_available_ram_bytes"],
        "RAM resource precondition",
    )
    require(
        measurement["free_disk_bytes"] >= RESOURCE["minimum_free_disk_bytes"],
        "disk resource precondition",
    )
    return measurement


def input_inventory():
    result = {}
    for name, pin in plan_data()["input_pins"].items():
        path = ROOT / name
        require(
            path.stat().st_size == pin["bytes"] and hash_file(path) == pin["sha256"],
            "Astra input changed: " + name,
        )
        result[name] = pin
    return result


def necessary_sources():
    protocol = SPARSE / "fix-round-1/pilot-protocol"
    sources = json.loads((protocol / "execution-source-hashes.json").read_text())
    index = json.loads((protocol / "execution-archive-index.json").read_text())
    # Test files and the sparse execution entry point are not runtime dependencies.
    excluded = [n for n in sources if n.startswith("tests/") or n.endswith("run_sparse_once.py")]
    for n in excluded:
        del sources[n]
        del index[n]
    for n, expected in sources.items():
        require(
            hash_file(ROOT / n) == expected and hash_file(ROOT / index[n]["archive"]) == expected,
            "necessary live/archive source changed: " + n,
        )
    for path in (
        DEV / "t7b-continuous-visibility-v3/verify_offline.py",
        SPARSE / "fix-round-1/offline/verify_sparse.py",
    ):
        name = str(path.relative_to(ROOT))
        expected = plan_data()["input_pins"][name]["sha256"]
        require(hash_file(path) == expected, "pure verification helper changed")
        sources[name] = expected
        old = DEV / "t7b-continuous-visibility-v3/fix-round-1/execution-archive-index.json"
        inherited = json.loads(old.read_text())
        if name in inherited:
            index[name] = {
                **inherited[name],
                "archive": str((DEV / inherited[name]["archive"]).relative_to(ROOT)),
            }
    # Enumerate real transitive public imports; no model/runtime initialization.
    pins = plan_data()["input_pins"]
    for path in (
        DEV / "t7b-continuous-visibility-v3/run_once.py",
        DEV / "t7b-continuous-visibility-v3/verify_offline.py",
        SPARSE / "fix-round-1/offline/verify_sparse.py",
    ):
        load_pinned(
            path, pins[str(path.relative_to(ROOT))]["sha256"], "round57_dependency_" + path.stem
        )
    existing = {}
    for manifest in (
        protocol / "execution-archive-index.json",
        DEV / "t7b-continuous-visibility-v3/fix-round-1/execution-archive-index.json",
    ):
        for name, row in json.loads(manifest.read_text()).items():
            archive_path = Path(row["archive"])
            if not archive_path.is_absolute():
                archive_path = (
                    ROOT / archive_path if (ROOT / archive_path).exists() else DEV / archive_path
                )
            existing[(name, row["sha256"])] = {
                **row,
                "archive": str(archive_path.relative_to(ROOT)),
            }
    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith("cloud_edge_robot_arm") or not getattr(
            module, "__file__", None
        ):
            continue
        path = Path(module.__file__).resolve(strict=True)
        require(
            path.is_relative_to(ROOT / "src") and Path(module.__spec__.origin).resolve() == path,
            "transitive runtime origin outside pinned source root",
        )
        name, value = str(path.relative_to(ROOT)), hash_file(path)
        sources[name] = value
        if (name, value) in existing:
            index[name] = existing[(name, value)]
    return sources, index


def check_origins(sources):
    for name, expected in sources.items():
        if name.startswith("src/") and name.endswith(".py"):
            module_name = name[4:-3].replace("/", ".")
            if module_name.endswith(".__init__"):
                module_name = module_name[:-9]
            module = importlib.import_module(module_name)
            path = (ROOT / name).resolve(strict=True)
            require(
                Path(module.__file__).resolve() == path
                and Path(module.__spec__.origin).resolve() == path
                and hash_file(path) == expected,
                "loaded live source origin differs: " + module_name,
            )


def source_preflight(base, header, directory):
    validate_full_header(header)
    directory = Path(directory)
    for name, key in (
        ("execution-source-hashes.json", "source_manifest_sha256"),
        ("execution-archive-index.json", "source_archive_index_sha256"),
        ("input-inventory.json", "input_inventory_sha256"),
    ):
        require(hash_file(directory / name) == header[key], "frozen metadata differs: " + name)
    sources = json.loads((directory / "execution-source-hashes.json").read_text())
    index = json.loads((directory / "execution-archive-index.json").read_text())
    require(
        set(sources) == set(index) and len(sources) == header["source_count"],
        "full source inventory differs",
    )
    expected_sources, _ = necessary_sources()
    expected_sources.update({str((HERE / n).relative_to(ROOT)): hash_file(HERE / n) for n in OWNED})
    require(same(sources, expected_sources), "complete actual dependency inventory differs")
    for name, expected in sources.items():
        live, archive = ROOT / name, ROOT / index[name]["archive"]
        require(
            hash_file(live) == hash_file(archive) == expected == index[name]["sha256"]
            and live.stat().st_size == archive.stat().st_size == index[name]["bytes"],
            "live/archive pin differs: " + name,
        )
    for pin in header["environment"]["files"].values():
        require(hash_file(pin["path"]) == pin["sha256"], "environment bytes changed")
    input_inventory()
    check_origins(sources)
    state_guard = importlib.import_module("cloud_edge_robot_arm.research.mujoco_state_guard")
    if base is not None:
        require(
            Path(base.state_guard.__file__).resolve() == Path(state_guard.__file__).resolve(),
            "loaded guard differs",
        )
    contract = state_guard.MujocoStateContract(
        Path(header["guard_headers"]["mjxmacro.h"]).read_bytes(),
        Path(header["guard_headers"]["mjdata.h"]).read_bytes(),
        header["guard_binding_sha256"],
        header["environment"]["mujoco_version"],
    )
    require(contract.digest == CONTRACT_DIGEST, "snapshot contract digest changed")
    return contract


def freeze_full(directory):
    directory = Path(directory)
    if directory.exists():
        raise FileExistsError("one freeze only; existing directory retained")
    header = make_full_header()
    validate_full_header(header)
    measurement = require_resources(directory.parent)
    inputs = input_inventory()
    sources, index = necessary_sources()
    directory.mkdir()
    archive = directory / "source-final"
    archive.mkdir()
    for path in [*(HERE / n for n in OWNED), *(ROOT / n for n in sources if n not in index)]:
        name, data = str(path.relative_to(ROOT)), path.read_bytes()
        target = archive / (
            "--".join(path.relative_to(ROOT).parts)
            if name not in {str((HERE / n).relative_to(ROOT)) for n in OWNED}
            else path.name
        )
        with target.open("xb") as stream:
            stream.write(data)
        sources[name] = digest(data)
        index[name] = dict(
            archive=str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else str(target),
            sha256=digest(data),
            bytes=len(data),
        )
    write_new(directory / "execution-source-hashes.json", sources)
    write_new(directory / "execution-archive-index.json", index)
    write_new(directory / "input-inventory.json", inputs)
    teacher = json.loads((OLD / "teacher-evidence.json").read_text())
    header.update(
        source_manifest_sha256=hash_file(directory / "execution-source-hashes.json"),
        source_archive_index_sha256=hash_file(directory / "execution-archive-index.json"),
        input_inventory_sha256=hash_file(directory / "input-inventory.json"),
        source_count=len(sources),
        source_bytes=sum((ROOT / n).stat().st_size for n in sources),
        archive_root=str(ROOT),
        initial_resource_measurement=measurement,
        original_recipe_reference={
            "path": str((OLD / "teacher-evidence.json").relative_to(ROOT)),
            "sha256": hash_file(OLD / "teacher-evidence.json"),
            "actions": teacher["actions"],
            "unframed_actions": teacher["unframed_actions"],
        },
        freeze_command="PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python "
        + str((HERE / "run_full_once.py").relative_to(ROOT))
        + " --prepare --protocol-directory "
        + str(directory.relative_to(ROOT))
        if directory.is_relative_to(ROOT)
        else "CPU_TEMP_FIXTURE_FREEZE",
        preparation_model_constructions=0,
        preparation_render_calls=0,
        preparation_decoder_calls=0,
    )
    write_new(directory / "header.json", header)
    source_preflight(None, header, directory)
    return dict(
        status="PREPARED_SOFTWARE_ONLY",
        source_count=len(sources),
        expected_frame_count=4807,
        header_sha256=hash_file(directory / "header.json"),
        model_constructions=0,
        decoder_calls=0,
    )
