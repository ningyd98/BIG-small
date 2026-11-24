"""Issue, acquire and read back the eight preregistered marker-mount development episodes."""

from __future__ import annotations

import argparse
import fcntl
import os
import shutil
import sqlite3
import sys
import time
import traceback
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from scripts.graduation import dynamic_vision as runtime
from scripts.graduation import g1_mount_runtime_build as builder
from scripts.graduation import guarded_clock
from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write
from scripts.graduation.proposal_closed_loop import readback_reset
from scripts.graduation.proposal_translated_cases import TranslatedEpisode

from cloud_edge_robot_arm.research import native_calibration_collection as native
from cloud_edge_robot_arm.vision.marker_families import (
    PREPARE_ONLY_FAMILY,
    SIDE_PREPARE_ONLY_FAMILY,
    marker_family,
)
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration

PLAN_SHA = "62e4c93a03f37fcb1ebd20ac660c09837c225f2b9651960701725c742914bef7"
RELEASE = "g1-development-marker-mount-20261124"
# Independent native inventories from the exact baseline, before applying any runner change.
CATALOGS = {
    SIDE_PREPARE_ONLY_FAMILY: (
        "native.calibration.operational.v4",
        "configs/research/native_operational_calibration_side_y_plus_75mm_r593.yaml",
        "01f29ebf95837973d52c112d183e11a7abc361a750e42606f1811fad7c9ad04b",
    ),
    PREPARE_ONLY_FAMILY: (
        "native.calibration.operational.v3",
        "configs/research/native_operational_calibration_75mm_r579.yaml",
        "c45d34252843c8aa337bd11fc989ad0416b0634b50022b2b60ef1a4e81c24943",
    ),
}


def check_registration(family, geometry, asset, catalog):
    if family not in CATALOGS:
        raise ValueError("family unavailable to the native development registration")
    schema, _, original_sha = CATALOGS[family]
    registered = marker_family(family)
    if (
        geometry != runtime.geometry_registration(marker_family_id=family)
        or asset != registered.asset_sha256
        or geometry["asset_path"] != registered.asset_path
        or catalog.get(registered.asset_path) != asset
        or sha(ROOT / registered.asset_path) != asset
        or native.digest(catalog) != original_sha
    ):
        raise ValueError("family, scene, native catalog or registered attachment/camera mismatch")
    native.check_sources(catalog, marker_family_id=family, protocol_schema=schema)
    registration = NativeGeometryRegistration(geometry)
    registration.validate_asset(ROOT)
    if registration.marker_family_id != family:
        raise ValueError("native registration changed family")
    return registration


def command_readback(actions, audit, episode):
    batches = [v for v in audit if v.get("phase") == "actual_command_records"]
    returns = [v["receipt"] for v in audit if v.get("phase") == "actual_executor_return"]
    controllers = [v["receipt"] for v in audit if v.get("phase") == "controller"]
    rows = []
    next_seq = 1
    for index, action in enumerate(actions, 1):
        if not action.get("executor_entered"):
            continue
        if not batches:
            raise ValueError("missing dispatched command batch")
        batch = batches.pop(0)
        skill = action["skill"]
        start, end = action["dispatch_step"], action["backend_return_step"]
        commands = guarded_clock.command_evidence(batch["rows"], episode, start, end, next_seq)
        accepted = Counter(c["type"] for c in commands if c["accepted"])
        if (
            not action["dispatched"]
            or batch["skill"] != skill
            or batch["first_seq"] != next_seq
            or len(commands) != action["command_records"]
            or dict(accepted) != action["accepted_command_types"]
        ):
            raise ValueError("command sequence or receipt differs from executor")
        evidence = action.get("return_evidence")
        receipt = None
        if evidence is not None:
            if not returns:
                raise ValueError("missing original return receipt")
            receipt = returns.pop(0)
            if (
                (receipt["step_id"], receipt["skill"], receipt["attempt"])
                != (f"step-{index}", skill, 1)
                or receipt["success"] != evidence["success"]
                or (evidence["absolute_step"], evidence["elapsed_steps"]) != (end, end - start)
            ):
                raise ValueError("return receipt identity or physics boundary mismatch")
        if "controller_return_step" in action and (
            not controllers
            or controllers.pop(0) != receipt
            or action["controller_return_step"] != end
        ):
            raise ValueError("controller result differs from original executor return")
        rows.append(
            dict(
                skill=skill,
                dispatch_step=start,
                backend_return_step=end,
                command_seq_half_open=[next_seq, next_seq + len(commands)],
                accepted_command_types=dict(accepted),
                command_records=len(commands),
                verified_original_receipt=receipt is not None,
                receipt_success=receipt["success"] if receipt else None,
            )
        )
        next_seq += len(commands)
    if batches or returns or controllers:
        raise ValueError("extra command or receipt outside the registered actions")
    return rows


def project_imports(lock):
    """Snapshot loaded project module paths, also detecting a fallback to an installed checkout."""
    result = {}
    for name, module in sorted(sys.modules.items()):
        if name.split(".", 1)[0] not in {"scripts", "cloud_edge_robot_arm"} and name != "__main__":
            continue
        file = getattr(module, "__file__", None)
        if file is None:
            for part in getattr(module, "__path__", []):
                if not Path(part).resolve().is_relative_to(ROOT):
                    raise ValueError("project package imported from outside isolated runtime")
            continue
        path = Path(file).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("development module imported from outside isolated runtime")
        rel = path.relative_to(ROOT).as_posix()
        digest = sha(path)
        if digest != lock["runtime_files_sha256"].get(rel):
            raise ValueError("imported module absent from the build or changed")
        result[name] = {"file": rel, "sha256": digest}
    return result


def load_context(plan_file, raw):
    plan = pinned(plan_file, PLAN_SHA)
    if (
        plan["baseline"] != builder.BASE
        or sha(plan_file.with_suffix(".md")) != plan["plan_md_sha256"]
    ):
        raise ValueError("frozen trial plan changed")
    if ROOT != (raw.parent / "runtime-source").resolve() or Path.cwd().resolve() != ROOT:
        raise ValueError("execute from the independently built runtime-source")
    build_sha = sha(plan_file.with_name("runtime-build.public.json"))
    lock = builder.load_lock(ROOT, build_sha)
    return plan, lock, build_sha


def native_catalog(family):
    schema = CATALOGS[family][0]
    full = native.source_inventory(marker_family_id=family, protocol_schema=schema)
    if full != native.source_inventory(marker_family_id=family):
        raise ValueError("default and explicitly registered family generation differ")
    return full


def preflight(plan_file, raw):
    plan, lock, build_sha = load_context(plan_file, raw)
    families = {}
    for mount in plan["mounts"]:
        family = mount["family"]
        if not mount["expected_native_family_admissible"]:
            continue
        catalog = native_catalog(family)
        geometry = runtime.geometry_registration(marker_family_id=family)
        check_registration(family, geometry, mount["asset_sha256"], catalog)
        families[family] = dict(
            geometry=geometry,
            catalog_count=len(catalog),
            catalog_product_sha256=native.digest(catalog),
        )
    write(
        raw.parent / "runtime-preflight.json",
        dict(
            plan_sha256=PLAN_SHA,
            runtime_build_sha256=build_sha,
            interpreter=sys.executable,
            source_root=str(ROOT),
            argv=sys.argv,
            module_imports=project_imports(lock),
            native_families=families,
            physics_steps=0,
            resets=0,
            acquisitions=0,
            worker_jobs=0,
        ),
    )


def check_issue_inputs(plan, selection, old, old_batch):
    if selection.get("plan_sha256") != PLAN_SHA:
        raise ValueError("selection must identify the frozen G1 plan")
    if (
        old["case"]["visual_stages_in_order"] != plan["stage_order"]
        or old["intent_descriptor"]["stages"] != plan["stage_order"]
        or old["case"]["attempts"] != 1
        or plan["attempts_per_slot"] != 1
        or any(
            s["reset_fixture_center_m"] == t["reset_fixture_center_m"]
            for s in plan["slots"]
            for t in old_batch["cases"]
        )
    ):
        raise ValueError("preallocated action intentions, retries or independent placements differ")


def issue(plan_file, raw):
    plan, lock, build_sha = load_context(plan_file, raw)
    selection_file = plan_file.with_name("selection.public.json")
    selection_sha = sha(selection_file)
    selection = pinned(selection_file, selection_sha)
    mounts = {m["id"]: m for m in plan["mounts"]}
    selected = mounts[selection["selected_mount"]]
    if (
        selected["id"] == "original"
        or selected["family"] != selection["selected_family"]
        or selected["asset_sha256"] != selection["selected_asset_sha256"]
        or selection["screen_inputs_and_outputs_sealed_before_fresh_trials"] is not True
        or any(
            sha(plan_file.parent / name) != digest
            for name, digest in selection["public_results_sha256"].items()
        )
        or not selected["expected_native_family_admissible"]
    ):
        raise ValueError("selected mount differs from native admissible candidate")
    repository = next(p for p in plan_file.resolve().parents if (p / ".git").exists())
    previous = plan["private_source"] + "/translated/episodes/"
    old_row = previous + "t01-nominal/allocation.json"
    old_batch = pinned(
        repository / (previous + "allocation.json"),
        plan["input_sha256"][previous + "allocation.json"],
    )
    old = pinned(repository / old_row, plan["input_sha256"][old_row])
    check_registration(
        mounts["original"]["family"],
        old["geometry"],
        old["asset_sha256"],
        pinned(
            repository / (previous + old["catalog"]["private_filename"]),
            old["catalog"]["archived_json_sha256"],
        ),
    )
    if any(sha(repository / k) != h for k, h in old["sources_sha256"].items()):
        raise ValueError("historical case source template changed")
    check_issue_inputs(plan, selection, old, old_batch)
    if shutil.disk_usage(raw.parent).free < len(plan["slots"]) * 2**31:
        raise ValueError("insufficient disk for the eight original-size acquisition attempts")
    raw.mkdir()
    issued = datetime.now(UTC).isoformat()
    catalogues, geometries = {}, {}
    for mount in (mounts["original"], selected):
        family = mount["family"]
        full = native_catalog(family)
        schema, config, original_sha = CATALOGS[family]
        geometry = runtime.geometry_registration(marker_family_id=family)
        check_registration(family, geometry, mount["asset_sha256"], full)
        name = f"{mount['id']}-native-source-inventory.json"
        write(raw / name, full)
        catalogues[family] = dict(
            family=family,
            selection=schema,
            config=config,
            config_sha256=full[config],
            count=len(full),
            original_product_sha256=original_sha,
            archived_json_sha256=sha(raw / name),
            private_filename=name,
            product_compact_sorted_utf8_sha256=native.digest(full),
            development_default_separators_sorted_utf8_sha256=runtime.digest(full),
        )
        geometries[family] = geometry
    cases = []
    for slot, spec in enumerate(plan["slots"], 1):
        mount = mounts["original"] if spec["arm"] == "original" else selected
        family, scene = mount["family"], mount["asset_sha256"]
        cat = catalogues[family]
        row = dict(
            **spec,
            slot=slot,
            mount=mount["id"],
            family=family,
            asset_sha256=scene,
            asset_path=mount["asset_path"],
            original_catalog_sha256=cat["original_product_sha256"],
        )
        case = {
            **old["case"],
            **row,
            "visual_seed": row["seed"],
            "visual_id": RELEASE + "/" + row["id"],
            "release": RELEASE,
            "private_output": row["id"] + "/instance",
        }
        sources = dict(pinned(raw / cat["private_filename"], cat["archived_json_sha256"]))
        sources.update(
            {k: v for k, v in lock["runtime_files_sha256"].items() if k.startswith("scripts/")}
        )
        check_sources({"sources_sha256": sources})
        alloc = dict(
            schema="g1.development.marker-mount.case.v1",
            baseline=builder.BASE,
            scope="DEVELOPMENT_COMPONENT_ONLY",
            issued_at=issued,
            case=case,
            geometry=geometries[family],
            asset_sha256=scene,
            catalog=cat,
            sources_sha256=sources,
            source_root="runtime-source",
            component_catalog_sha256=cat["development_default_separators_sorted_utf8_sha256"],
            intent_descriptor=old["intent_descriptor"],
            selected_entry=old["selected_entry"],
            capture_grid=old["capture_grid"],
            plan_sha256=PLAN_SHA,
            plan_md_sha256=plan["plan_md_sha256"],
            selection_sha256=selection_sha,
            runtime_build_sha256=build_sha,
            historical_baseline_case_sha256=plan["input_sha256"][old_row],
        )
        path = raw / row["id"] / "allocation.json"
        path.parent.mkdir()
        write(path, alloc)
        cases.append(
            dict(
                **row, allocation_file=path.relative_to(raw).as_posix(), allocation_sha256=sha(path)
            )
        )
    manifest = dict(
        schema="g1.development.marker-mount.paired-allocation.v1",
        release=RELEASE,
        baseline=builder.BASE,
        issued_at=issued,
        plan_sha256=PLAN_SHA,
        plan_md_sha256=plan["plan_md_sha256"],
        selection_sha256=selection_sha,
        selected_mount=selected["id"],
        selected_family=selected["family"],
        runtime_build_sha256=build_sha,
        runtime_preflight_sha256=sha(raw.parent / "runtime-preflight.json"),
        native_catalogues=catalogues,
        geometries=geometries,
        cases=cases,
        attempts_per_slot=1,
        historical_baseline_case_sha256=plan["input_sha256"][old_row],
        formal_simulations=0,
        formal_claims=0,
        hardware_actions=0,
        task_model_calls=0,
    )
    write(raw / "allocation.json", manifest)
    write(plan_file.with_name("trial-allocation.public.json"), manifest)


def check_batch(plan_file, raw, h):
    plan, lock, build_sha = load_context(plan_file, raw)
    batch = pinned(raw / "allocation.json", h)
    if (
        sha(plan_file.with_name("trial-allocation.public.json")) != h
        or sha(plan_file.with_name("selection.public.json")) != batch["selection_sha256"]
        or batch["runtime_build_sha256"] != build_sha
        or batch["plan_sha256"] != PLAN_SHA
        or batch["release"] != RELEASE
        or batch["attempts_per_slot"] != 1
    ):
        raise ValueError("foreign allocation, selection or runtime")
    mounts = {m["id"]: m for m in plan["mounts"]}
    for slot, (spec, row) in enumerate(zip(plan["slots"], batch["cases"], strict=True), 1):
        mount = mounts["original" if spec["arm"] == "original" else batch["selected_mount"]]
        if (
            any(row[k] != v for k, v in spec.items())
            or row["slot"] != slot
            or (row["mount"], row["family"], row["asset_sha256"], row["asset_path"])
            != (mount["id"], mount["family"], mount["asset_sha256"], mount["asset_path"])
            or row["allocation_file"] != spec["id"] + "/allocation.json"
        ):
            raise ValueError("case identity, assignment order or scene differs from plan")
    return batch, lock


def load_case(raw, batch, row):
    a = pinned(raw / row["allocation_file"], row["allocation_sha256"])
    case = a["case"]
    for k in row.keys() - {"allocation_file", "allocation_sha256"}:
        if case[k] != row[k]:
            raise ValueError("private allocation identity differs from issued slot")
    family = row["family"]
    cat = batch["native_catalogues"][family]
    full = pinned(raw / cat["private_filename"], cat["archived_json_sha256"])
    if (
        case["visual_id"] != RELEASE + "/" + case["id"]
        or case["visual_seed"] != row["seed"]
        or a["selection_sha256"] != batch["selection_sha256"]
        or a["runtime_build_sha256"] != batch["runtime_build_sha256"]
        or a["catalog"] != cat
        or a["component_catalog_sha256"] != runtime.digest(full)
        or a["geometry"] != batch["geometries"][family]
        or a["asset_sha256"] != row["asset_sha256"]
        or a["intent_descriptor"]["stages"] != case["visual_stages_in_order"]
    ):
        raise ValueError(
            "registration, intent or private source generation differs from assigned case"
        )
    check_sources(a)
    check_registration(family, a["geometry"], a["asset_sha256"], full)
    return a, full


def worker_readback(directory, alloc, row, run):
    path = directory / "development-worker.db"
    wal = directory / "development-worker.db-wal"
    if wal.exists() and wal.stat().st_size:
        raise ValueError("worker database still has uncheckpointed activity")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        db.row_factory = sqlite3.Row
        (job,) = db.execute("SELECT * FROM simulation_jobs")
        (attempt,) = db.execute("SELECT * FROM simulation_job_attempts")
        (lease,) = db.execute("SELECT * FROM simulation_job_leases")
        events = list(
            db.execute(
                "SELECT job_id, previous_status, next_status "
                "FROM simulation_job_events ORDER BY sequence"
            )
        )
    summary = run["lease_summary"]
    final = "FAILED" if "stop" in run else "SUCCEEDED"
    status_order = ["CREATED", "QUEUED", "LEASED", "STARTING", "RUNNING", "FINALIZING", final]
    if (
        job["job_id"] != summary["job_id"]
        or job["run_id"] != summary["run_id"]
        or job["run_id"] != alloc["case"]["visual_id"].replace("/", ":")
        or (job["seed"], job["reproducibility_hash"]) != (row["seed"], row["allocation_sha256"])
        or (job["source_commit"], job["source_tree_hash"])
        != (builder.BASE, alloc["component_catalog_sha256"])
        or (job["backend"], job["control_mode"]) != ("MUJOCO", "DEVELOPMENT_COMPONENTS")
        or job["status"] != final
        or summary["final_job_status"] != final
        or not all(
            v == 1
            for v in (job["attempt"], job["max_attempts"], attempt["attempt"], summary["attempt"])
        )
        or (attempt["run_id"], attempt["job_id"], attempt["result"])
        != (job["run_id"], job["job_id"], final)
        or lease["job_id"] != job["job_id"]
        or lease["lease_id"] != job["lease_id"]
        or not (summary["worker"] == lease["worker_id"] == attempt["worker_id"])
        or not summary["lease_released"]
        or not lease["released_at"]
        or not (
            lease["acquired_at"]
            <= attempt["started_at"]
            <= attempt["ended_at"]
            <= lease["released_at"]
        )
        or any(event["job_id"] != job["job_id"] for event in events)
        or [e["next_status"] for e in events] != status_order
        or [e["previous_status"] for e in events] != ["", *status_order[:-1]]
    ):
        raise ValueError("worker, immutable SQLite lease, attempt, status or case identity differs")
    return dict(
        worker=summary["worker"],
        job_id=job["job_id"],
        lease_id=lease["lease_id"],
        run_id=job["run_id"],
        attempt=attempt["attempt"],
        final_status=final,
        status_sequence=status_order,
        acquired_at=lease["acquired_at"],
        released_at=lease["released_at"],
        started_at=attempt["started_at"],
        ended_at=attempt["ended_at"],
        sqlite_sha256=sha(path),
    )


def installed_modules():
    """Private byte catalogue for imported stdlib/extensions and installed dependencies."""
    files = {}
    for mod in tuple(sys.modules.values()):
        file = getattr(mod, "__file__", None)
        if not file:
            continue
        path = Path(file).resolve()
        if path.is_file() and not path.is_relative_to(ROOT):
            files[path] = None
    return {str(path): sha(path) for path in sorted(files)}


def captured_evidence(directory, row, alloc):
    reset = readback_reset(row, read(directory / "reset-observed.json"))
    if read(directory / "camera-setup.json") != []:
        raise ValueError("nominal camera changed after independent physical reset")
    seal = read(directory / "acquisition-seal.json")
    index = pinned(directory / "pixel-index.json", seal["index_sha256"])
    run = pinned(directory / "run.json", seal["run_sha256"])
    audit = pinned(directory / "online-audit.json", seal["audit_sha256"])
    if (
        index["episode"] != reset["episode_id"]
        or index["allocation_sha256"] != row["allocation_sha256"]
        or sha(directory / "offline-truth.json") != seal["truth_sha256"]
        or [a["skill"] for a in run["actions"]] != alloc["case"]["visual_stages_in_order"]
    ):
        raise ValueError("reset, trajectory, frames or intentions are from a different capture")
    records = read(directory / "backend-commands.json")
    terminal = index["frames"][-1]
    if terminal["label"] != "terminal" or index["frames"][0]["label"] != "reset":
        raise ValueError("missing terminal or reset frame")
    checked = guarded_clock.command_evidence(
        records, index["episode"], 0, terminal["physics_step"], 1
    )
    actions = command_readback(run["actions"], audit, index["episode"])
    batches = [v for v in audit if v.get("phase") == "actual_command_records"]
    for action, batch in zip(actions, batches, strict=True):
        left, right = action["command_seq_half_open"]
        if batch["rows"] != checked[left - 1 : right - 1]:
            raise ValueError("executor audit differs from independent full backend command log")
    end = actions[-1]["command_seq_half_open"][1] if actions else 1
    outside = checked[end - 1 :]
    expected_tail = ["hold_current_joints", "emergency_stop"] if "safe_stop" in run else []
    if [r["type"] for r in outside] != expected_tail or any(not r["accepted"] for r in outside):
        raise ValueError("unexpected backend command outside original action intervals")
    return dict(
        id=row["id"],
        slot=row["slot"],
        arm=row["arm"],
        family=row["family"],
        allocation_sha256=row["allocation_sha256"],
        physical_reset=reset,
        captured_frames=len(index["frames"]),
        actual_physics_steps=terminal["physics_step"],
        action_commands=actions,
        backend_command_count=len(checked),
        outside_actions=outside,
        worker=worker_readback(directory, alloc, row, run),
        stop=run.get("stop"),
        capture_sha256=sha(directory / "acquisition-seal.json"),
        reset_sha256=sha(directory / "reset-observed.json"),
        camera_setup_sha256=sha(directory / "camera-setup.json"),
        started_sha256=sha(directory / "started.json"),
        full_commands_sha256=sha(directory / "backend-commands.json"),
        imports_sha256=sha(directory / "imports.json"),
    )


def capture(plan_file, raw, h, case_id):
    if os.environ.get("MUJOCO_GL") != "egl":
        raise ValueError("registered EGL backend required")
    batch, lock = check_batch(plan_file, raw, h)
    (row,) = [r for r in batch["cases"] if r["id"] == case_id]
    for earlier in batch["cases"][: row["slot"] - 1]:
        previous = raw / earlier["id"] / "instance"
        if (
            not (previous / "receipt.json").exists()
            and not (previous / "interrupted.json").exists()
        ):
            raise ValueError("previous registered slot has no completed or interrupted attempt")
    alloc, catalog = load_case(raw, batch, row)
    imports = project_imports(lock)
    directory = raw / row["id"] / "instance"
    directory.mkdir()  # Atomic reservation of the only attempt, including interrupted instances.
    start = time.monotonic()
    write(
        directory / "started.json",
        dict(
            case=case_id,
            slot=row["slot"],
            argv=sys.orig_argv,
            batch_sha256=h,
            allocation_sha256=row["allocation_sha256"],
            attempt=1,
            source_root=str(ROOT),
            interpreter=sys.executable,
            environment_pythonpath=os.environ.get("PYTHONPATH"),
            egl_lock=str(raw.parent / "egl.lock"),
            start_utc=datetime.now(UTC).isoformat(),
        ),
    )
    try:
        episode = TranslatedEpisode(directory, alloc, row["allocation_sha256"], catalog)
        try:
            episode.run()
            write(directory / "backend-commands.json", episode.backend.command_records)
        finally:
            episode.backend.shutdown()
        after = project_imports(lock)
        if any(after[k] != v for k, v in imports.items()):
            raise ValueError("project module changed during the guarded episode")
        write(
            directory / "imports.json",
            dict(
                source_root=str(ROOT),
                interpreter=sys.executable,
                executable_sha256=sha(Path(sys.executable)),
                argv=sys.argv,
                project_before=imports,
                project_after=after,
                external_loaded_files_sha256=installed_modules(),
                versions=dict(
                    python=sys.version,
                    mujoco=runtime.mujoco.__version__,
                    opencv=runtime.cv2.__version__,
                    numpy=runtime.np.__version__,
                    pillow=runtime.PIL.__version__,
                ),
            ),
        )
        result = captured_evidence(directory, row, alloc)
        write(
            directory / "receipt.json",
            {
                **result,
                "batch_sha256": h,
                "wall_s": time.monotonic() - start,
                "finished_utc": datetime.now(UTC).isoformat(),
            },
        )
    except BaseException as exc:
        write(
            directory / "interrupted.json",
            dict(
                type=type(exc).__name__,
                error=str(exc),
                traceback=traceback.format_exc(),
                wall_s=time.monotonic() - start,
                sealed_acquisition_exists=(directory / "acquisition-seal.json").is_file(),
            ),
        )
        raise


def audit_all(plan_file, raw, h):
    batch, _ = check_batch(plan_file, raw, h)
    results = []
    for row in batch["cases"]:
        alloc, _ = load_case(raw, batch, row)
        d = raw / row["id"] / "instance"
        result = captured_evidence(d, row, alloc)
        receipt = read(d / "receipt.json")
        if receipt["batch_sha256"] != h or any(receipt[k] != v for k, v in result.items()):
            raise ValueError("acquisition differs from independently reread receipt")
        results.append(
            dict(
                **result,
                receipt_sha256=sha(d / "receipt.json"),
                finished_utc=receipt["finished_utc"],
                wall_s=receipt["wall_s"],
            )
        )
    for ids in (
        [r["physical_reset"]["episode_id"] for r in results],
        [r["worker"]["job_id"] for r in results],
        [r["worker"]["lease_id"] for r in results],
    ):
        if len(set(ids)) != len(batch["cases"]):
            raise ValueError("reset, job or lease reused among preallocated cases")
    if any(
        curr["worker"]["acquired_at"] <= prev["worker"]["released_at"]
        for prev, curr in zip(results, results[1:], strict=False)
    ):
        raise ValueError("serial owner leases overlap or slots out of order")
    output = dict(
        schema="g1.development.marker-mount.acquisition.v1",
        allocation_sha256=h,
        runtime_build_sha256=batch["runtime_build_sha256"],
        selection_sha256=batch["selection_sha256"],
        cases=results,
        actual_episodes=len(results),
        distinct_resets=len(results),
        actual_dispatched=sum(len(r["action_commands"]) for r in results),
        formal_simulations=0,
        formal_claims=0,
        hardware_actions=0,
        task_model_calls=0,
        worker_label_scope="Both arms inherit the original worker, manifest and task display IDs.",
    )
    write(raw / "acquisition.json", output)
    write(plan_file.with_name("trial-acquisition.public.json"), output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "issue", "capture", "audit"):
        p = commands.add_parser(name)
        p.add_argument("plan", type=Path)
        p.add_argument("raw", type=Path, help="private trials directory")
        if name in ("capture", "audit"):
            p.add_argument("allocation_sha256")
        if name == "capture":
            p.add_argument("case")
    args = parser.parse_args()
    plan, raw = args.plan.resolve(), args.raw.resolve()
    if args.command == "capture":
        with (raw.parent / "egl.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            capture(plan, raw, args.allocation_sha256, args.case)
    elif args.command == "issue":
        issue(plan, raw)
    elif args.command == "preflight":
        preflight(plan, raw)
    else:
        audit_all(plan, raw, args.allocation_sha256)


if __name__ == "__main__":
    main()
