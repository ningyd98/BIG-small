"""Register and run the eight prospectively assigned, single-attempt G1 MuJoCo slots."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from scripts.graduation import g1_formal_runtime as build
from scripts.graduation.g1_formal_runtime import PLAN_SHA, RELEASE, SCOPE, require
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

OVERLAP_SHA = "f4b63cc8c7946a0adfd007370f1d946cf878c075a33d11d8f452122025b147ea"
REGISTRATION = "trial-allocation.public.json"
ACQUISITION = "trial-acquisition.public.json"


def identities(assignment):
    run_id = assignment.replace("/", ":")
    return dict(
        scene_id=assignment, run_id=run_id, task_id=run_id + ":task", plan_id=run_id + ":plan"
    )


def copy_once(source, destination):
    with destination.open("xb") as stream:
        stream.write(source.read_bytes())
        stream.flush()
        os.fsync(stream.fileno())


def checked_runtime(repo, plan, out):
    from scripts.graduation import g1_dual_probe, g1_dual_trials, g1_mount_trials

    require(ROOT == out / "runtime-source" == Path.cwd(), "use the frozen runtime")
    lock = build.verify_lock(out)
    require(
        all(sha(repo / k) == h for k, h in lock["external_entries_sha256"].items()),
        "workspace launcher or scorer differs from frozen source",
    )
    build.verify_inputs(repo, plan)
    parent, prior = build.parent_inputs(repo, plan)
    derived, _ = build.derived_build(repo, plan, parent, prior)
    require(derived == lock, "runtime differs from the permitted fourth-generation identity edits")
    previous = parent.parent
    old_batch = read(previous / "trials/allocation.json")
    acquisition = read(previous / "trials/acquisition.json")
    controls = previous / "probes/zero-step-probes.json"
    control = pinned(controls, old_batch["zero_step_probes_sha256"])
    require(
        control["eligible"] is True
        and control["runtime_build_sha256"] == plan["runtime_build_sha256"]
        and control["physics_steps"] == control["dispatched_actions"] == 0
        and g1_dual_probe.qualifies(control["results"])
        and all(sha(controls.parent / k) == h for k, h in control["private_seal_sha256"].items()),
        "fourth-generation qualification is incomplete",
    )
    dependencies = {}
    templates = {}
    for arm in ("original", "dual"):
        case = next(c for c in old_batch["cases"] if c["arm"] == arm)
        template = pinned(previous / "trials" / case["allocation_file"], case["allocation_sha256"])
        geom = build.checked_geometry(
            arm,
            template["geometry"],
            g1_dual_trials.runtime.geometry_registration(marker_family_id=case["family"]),
            lock,
        )
        template = {**template, "geometry": geom}
        require(
            geom["camera"] == plan["camera"]
            and template["intent_descriptor"]["stages"] == plan["stage_order"],
            "camera, marker or intentions differ from qualified template",
        )
        original = pinned(
            repo / plan["source_inventory_paths"][case["family"]],
            plan["native_catalogues"][case["family"]]["archived_json_sha256"],
        )
        full = {
            k: lock["runtime_files_sha256"][k] for k in sorted(set(original) | set(build.ADDITIONS))
        }
        templates[arm] = (case, template, full)
        observed = next(v for v in acquisition["cases"] if v["id"] == case["id"])
        imported = pinned(
            previous / "trials" / case["id"] / "instance/imports.json", observed["imports_sha256"]
        )
        require(
            sha(Path(sys.executable)) == imported["executable_sha256"]
            and sys.version_info[:2] == (3, 12),
            "wrong interpreter",
        )
        dependencies.update(imported["external_loaded_files_sha256"])
    require(
        all(sha(Path(k)) == h for k, h in dependencies.items()),
        "qualified external dependency changed",
    )
    require(callable(g1_dual_trials.runtime.cv2.aruco.ArucoDetector), "OpenCV ArUco unavailable")
    g1_mount_trials.project_imports(lock)
    return lock, templates, dependencies, sha(controls)


def ready_device(templates, required_bytes, out):
    from scripts.graduation import g1_dual_trials as dual

    require(os.environ.get("MUJOCO_GL") == "egl", "MuJoCo EGL required")
    require(shutil.disk_usage(out).free >= required_bytes, "insufficient private storage")
    mj = dual.runtime.mujoco
    context = mj.GLContext(16, 16)
    try:
        context.make_current()
    finally:
        context.free()
    compiled = {}
    for arm, (desc, template, _) in templates.items():
        geom = template["geometry"]
        model = mj.MjModel.from_xml_path(str(ROOT / geom["asset_path"]))
        assembly = dual.mass_properties(model)
        require(
            abs(assembly["mass_kg"] - desc["physical_object_mass_kg"]) <= 1e-12,
            "compiled assembly mass mismatch",
        )
        compiled[arm] = assembly
    return compiled


def issue(repo, plan_file, plan, out):
    from scripts.graduation import g1_dual_trials as dual

    lock, templates, dependencies, control_sha = checked_runtime(repo, plan, out)
    compiled = ready_device(templates, 8 * 2**31, out)
    overlap = pinned(plan_file.with_name("placement-overlap.public.json"), OVERLAP_SHA)
    require(
        overlap["eligible"] is True
        and overlap["plan_sha256"] == PLAN_SHA
        and overlap["release"] == RELEASE
        and overlap["distinct_placements"] == 4
        and overlap["slot_count"] == 8,
        "unverified placement independence",
    )
    require(
        not any((out / "claims").iterdir())
        and not plan_file.with_name(REGISTRATION).exists()
        and {p.name for p in out.iterdir()} <= {"claims", "egl.lock", "runtime-source"},
        "release already registered or output contains foreign data",
    )
    raw = out / "trials"
    raw.mkdir()
    write(raw / "external-dependencies.json", dependencies)
    build_sha = sha(ROOT / "runtime-build.json")
    issued = datetime.now(UTC).isoformat()
    catalogs, geometries, cases = {}, {}, []
    for arm, (desc, template, full) in templates.items():
        path = raw / (arm + "-formal-source-inventory.json")
        write(path, full)
        family = desc["family"]
        catalogs[family] = dict(
            family=family,
            count=len(full),
            private_filename=path.name,
            archived_json_sha256=sha(path),
            parent_catalog_sha256=plan["native_catalogues"][family]["archived_json_sha256"],
            product_compact_sorted_utf8_sha256=dual.native.digest(full),
            development_default_separators_sorted_utf8_sha256=dual.runtime.digest(full),
        )
        geometries[family] = template["geometry"]
    for spec in plan["slots"]:
        arm = spec["arm"]
        desc, template, full = templates[arm]
        require(
            all(
                spec[k] == desc[k]
                for k in ("asset_path", "asset_sha256", "family", "physical_object_mass_kg")
            ),
            "registered arm differs from qualified assembly",
        )
        row = {**spec, **identities(spec["visual_id"])}
        case = {
            **row,
            "release": RELEASE,
            "mount": arm,
            "claim_scope": SCOPE,
            "visual_seed": row["seed"],
            "private_output": row["id"] + "/instance",
            "visual_stages_in_order": plan["stage_order"],
            "settle": plan["clock"]["settle_physics_steps"],
            "physics_dt_s": plan["clock"]["physics_dt_s"],
            "max_skill_calls": 8,
            "hardware_actions": 0,
            "task_model_calls": 0,
        }
        catalog = catalogs[row["family"]]
        allocation = dict(
            schema="g1.formal-paired.case.v1",
            scope=SCOPE,
            baseline=plan["baseline"],
            issued_at=issued,
            case=case,
            geometry=template["geometry"],
            catalog=catalog,
            asset_sha256=row["asset_sha256"],
            sources_sha256=full,
            component_catalog_sha256=dual.runtime.digest(full),
            source_root="runtime-source",
            intent_descriptor={
                "type": "prospectively registered G1 skill intentions",
                "stages": plan["stage_order"],
                "model_calls": 0,
            },
            selected_entry=template["selected_entry"],
            capture_grid=template["capture_grid"],
            method_template_sha256=desc["allocation_sha256"],
            runtime_build_sha256=build_sha,
            plan_sha256=PLAN_SHA,
            scene_binding_plan_sha256=build.SCENE_PLAN_SHA,
            plan_md_sha256=plan["plan_md_sha256"],
            zero_step_probes_sha256=control_sha,
        )
        path = raw / row["id"] / "allocation.json"
        path.parent.mkdir()
        write(path, allocation)
        cases.append(
            {
                **row,
                "allocation_file": path.relative_to(raw).as_posix(),
                "allocation_sha256": sha(path),
            }
        )
    batch = dict(
        schema="g1.formal-paired.allocation.v1",
        scope=SCOPE,
        release=RELEASE,
        baseline=plan["baseline"],
        plan_sha256=PLAN_SHA,
        scene_binding_plan_sha256=build.SCENE_PLAN_SHA,
        plan_md_sha256=plan["plan_md_sha256"],
        issued_at=issued,
        attempts_per_slot=1,
        formal_output=plan["formal_output"],
        output_root_sha256=build.digest(os.fsencode(out)),
        authoritative_ledger="claims",
        cases=cases,
        native_catalogues=catalogs,
        geometries=geometries,
        compiled_assembly=compiled,
        placement_overlap_sha256=OVERLAP_SHA,
        runtime_build_sha256=build_sha,
        parent_runtime_build_sha256=plan["runtime_build_sha256"],
        zero_step_probes_sha256=control_sha,
        scoring_sources_sha256=lock["scoring_sources_sha256"],
        external_dependencies_sha256=sha(raw / "external-dependencies.json"),
        authorized_g1_assignments=8,
        hardware_actions=0,
        task_model_calls=0,
        v10_claims=0,
    )
    write(raw / "allocation.json", batch)
    copy_once(ROOT / "runtime-build.json", plan_file.with_name("runtime-build.public.json"))
    copy_once(raw / "allocation.json", plan_file.with_name(REGISTRATION))
    return sha(raw / "allocation.json")


def load_case(raw, batch, row):
    from scripts.graduation import g1_dual_trials as dual

    alloc = pinned(raw / row["allocation_file"], row["allocation_sha256"])
    case = alloc["case"]
    catalog = batch["native_catalogues"][row["family"]]
    full = pinned(raw / catalog["private_filename"], catalog["archived_json_sha256"])
    require(
        all(
            case[k] == v
            for k, v in row.items()
            if k not in {"allocation_file", "allocation_sha256"}
        )
        and case["visual_seed"] == row["seed"]
        and case["visual_id"] == RELEASE + "/" + row["id"]
        and alloc["schema"] == "g1.formal-paired.case.v1"
        and case["claim_scope"] == alloc["scope"] == SCOPE
        and case["release"] == RELEASE
        and alloc["plan_sha256"] == batch["plan_sha256"] == PLAN_SHA
        and alloc["scene_binding_plan_sha256"]
        == batch["scene_binding_plan_sha256"]
        == build.SCENE_PLAN_SHA
        and alloc["catalog"] == catalog
        and alloc["runtime_build_sha256"] == batch["runtime_build_sha256"]
        and alloc["geometry"] == batch["geometries"][row["family"]]
        and dual.runtime.geometry_registration(marker_family_id=row["family"]) == alloc["geometry"]
        and alloc["sources_sha256"] == full
        and alloc["component_catalog_sha256"] == dual.runtime.digest(full)
        and catalog["product_compact_sorted_utf8_sha256"] == dual.native.digest(full)
        and alloc["asset_sha256"] == row["asset_sha256"] == full[row["asset_path"]]
        and case["visual_stages_in_order"] == alloc["intent_descriptor"]["stages"],
        "foreign slot allocation",
    )
    dual.NativeGeometryRegistration(alloc["geometry"]).validate_asset(ROOT)
    return alloc, full


def check_batch(repo, plan_file, plan, out, h, *, dispatch=False):
    raw = out / "trials"
    batch = pinned(raw / "allocation.json", h)
    require(
        sha(plan_file.with_name(REGISTRATION)) == h
        and batch["release"] == RELEASE
        and batch["plan_sha256"] == PLAN_SHA
        and batch["scene_binding_plan_sha256"] == build.SCENE_PLAN_SHA
        and batch["baseline"] == plan["baseline"]
        and batch["scope"] == SCOPE
        and batch["attempts_per_slot"] == 1
        and batch["output_root_sha256"] == build.digest(os.fsencode(out))
        and batch["placement_overlap_sha256"]
        == sha(plan_file.with_name("placement-overlap.public.json"))
        == OVERLAP_SHA
        and batch["runtime_build_sha256"]
        == sha(plan_file.with_name("runtime-build.public.json"))
        == sha(ROOT / "runtime-build.json"),
        "unverified formal registration",
    )
    lock, templates, dependencies, control = checked_runtime(repo, plan, out)
    require(
        batch["scoring_sources_sha256"] == lock["scoring_sources_sha256"]
        and pinned(raw / "external-dependencies.json", batch["external_dependencies_sha256"])
        == dependencies
        and control == batch["zero_step_probes_sha256"],
        "registered source or device qualification changed",
    )
    for spec, row in zip(plan["slots"], batch["cases"], strict=True):
        expected = {
            **spec,
            **identities(spec["visual_id"]),
            "allocation_file": spec["id"] + "/allocation.json",
        }
        require(all(row[k] == v for k, v in expected.items()), "case crossed the registered order")
        if dispatch:
            alloc, full = load_case(raw, batch, row)
            desc, template, actual = templates[row["arm"]]
            require(
                full == actual
                and alloc["geometry"] == template["geometry"]
                and alloc["method_template_sha256"] == desc["allocation_sha256"]
                and alloc["selected_entry"] == template["selected_entry"]
                and alloc["capture_grid"] == template["capture_grid"],
                "formal method differs from qualification",
            )
    if dispatch:
        remaining = sum(not (out / "claims" / (r["id"] + ".json")).exists() for r in batch["cases"])
        require(
            batch["compiled_assembly"] == ready_device(templates, max(1, remaining) * 2**31, out),
            "mechanical assembly changed",
        )
    return batch, lock


def claim_fields(out, batch, row, h):
    return dict(
        schema="g1.formal-paired.claim.v1",
        release=batch["release"],
        id=row["id"],
        assignment=row["visual_id"],
        slot=row["slot"],
        attempt=1,
        protocol_sha256=PLAN_SHA,
        scene_binding_plan_sha256=build.SCENE_PLAN_SHA,
        allocation_sha256=row["allocation_sha256"],
        batch_sha256=h,
        output_root=str(out),
    )


def process_birth(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except FileNotFoundError:
        return None


def checked_claim(out, batch, row, h):
    ledger = out / "claims" / (row["id"] + ".json")
    claim = read(ledger)
    require(
        all(claim.get(k) == v for k, v in claim_fields(out, batch, row, h).items()),
        "foreign case, release or root in claim",
    )
    copy = out / "trials" / row["id"] / "claim.json"
    require(
        not ledger.is_symlink() and not copy.is_symlink() and sha(ledger) == sha(copy),
        "claim mirror differs",
    )
    return claim, sha(ledger)


def claim_slot(out, batch, row, h):
    directory = out / "trials" / row["id"]
    ledger = out / "claims" / (row["id"] + ".json")
    require(
        directory.resolve() == directory and ledger.parent.resolve() == ledger.parent,
        "redirected formal slot or authoritative ledger",
    )
    if ledger.exists() or (directory / "instance").exists() or (directory / "claim.json").exists():
        raise FileExistsError("formal claim or instance already exists: " + row["id"])
    for earlier in batch["cases"][: row["slot"] - 1]:
        instance = out / "trials" / earlier["id"] / "instance"
        require(
            (instance / "receipt.json").is_file() or (instance / "interrupted.json").is_file(),
            "earlier slot has no terminal or interruption receipt",
        )
        _, earlier_claim = checked_claim(out, batch, earlier, h)
        if (instance / "receipt.json").exists():
            receipt = read(instance / "receipt.json")
            require(
                receipt.get("id") == earlier["id"]
                and receipt.get("slot") == earlier["slot"]
                and receipt.get("batch_sha256") == h
                and receipt.get("allocation_sha256") == earlier["allocation_sha256"]
                and receipt.get("claim_sha256") == earlier_claim
                and not (instance / "interrupted.json").exists(),
                "earlier terminal belongs to a different assignment or claim",
            )
        else:
            interruption = read(instance / "interrupted.json")
            require(
                interruption.get("type") and "error" in interruption,
                "earlier interruption receipt is incomplete",
            )
    claim = dict(
        **claim_fields(out, batch, row, h),
        claimed_at=datetime.now(UTC).isoformat(),
        pid=os.getpid(),
        process_birth=process_birth(os.getpid()),
        boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
    )
    with ledger.open("x", encoding="utf-8") as stream:
        json.dump(claim, stream, sort_keys=True, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(ledger.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    copy_once(ledger, directory / "claim.json")
    return sha(ledger)


@contextmanager
def device_lock(out):
    require((out / "egl.lock").resolve() == out / "egl.lock", "redirected EGL lock")
    with (out / "egl.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def delivered(repo, plan_file, batch):
    supplement = plan_file.parent.parent / build.SCENE_ROUND / "plan.json"
    names = [
        plan_file,
        plan_file.with_suffix(".md"),
        plan_file.with_name(REGISTRATION),
        plan_file.with_name("runtime-build.public.json"),
        plan_file.with_name("placement-overlap.public.json"),
        supplement,
        supplement.with_suffix(".md"),
    ]
    for path in [*names, *(repo / k for k in build.ADDITIONS)]:
        relative = path.relative_to(repo).as_posix()
        expected = sha(path)
        for ref in ("HEAD", "@{upstream}"):
            require(
                build.digest(build.git(repo, "show", ref + ":" + relative)) == expected,
                "registration or entry not delivered: " + relative,
            )
    require(batch["plan_sha256"] == PLAN_SHA, "unregistered batch")


def capture(repo, plan_file, plan, out, h, case_id):
    from scripts.graduation import g1_dual_trials as dual

    batch, lock = check_batch(repo, plan_file, plan, out, h, dispatch=True)
    delivered(repo, plan_file, batch)
    (row,) = [r for r in batch["cases"] if r["id"] == case_id]
    with build.bind_scene(row["scene_id"]):
        dual.g1_mount_trials.capture(
            plan_file,
            out / "trials",
            h,
            case_id,
            context=lambda *args: (batch, lock),
            case_reader=load_case,
            episode_factory=dual.episode_with_registered_mass,
            before_start=lambda: claim_slot(out, batch, row, h),
        )


def recover(out, batch, row, h):
    path = out / "claims" / (row["id"] + ".json")
    original = read(path)
    require(
        all(original.get(k) == v for k, v in claim_fields(out, batch, row, h).items()),
        "foreign interruption claim",
    )
    require(
        original["boot_id"] != Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        or process_birth(original["pid"]) != original["process_birth"],
        "claimed process still running",
    )
    directory = out / "trials" / row["id"]
    if not (directory / "claim.json").exists():
        copy_once(path, directory / "claim.json")
    _, claim_sha = checked_claim(out, batch, row, h)
    directory = directory / "instance"
    directory.mkdir(exist_ok=True)
    require(not (directory / "receipt.json").exists(), "case already completed")
    write(
        directory / "interrupted.json",
        dict(
            type="ProcessExitedWithoutReceipt",
            claim_sha256=claim_sha,
            recorded_at=datetime.now(UTC).isoformat(),
            error="Claim owner exited without a terminal receipt",
        ),
    )


def formal_evidence(directory, row, result, h, claim):
    start = read(directory / "started.json")
    require(
        start["claim_sha256"] == result["claim_sha256"]
        and start["batch_sha256"] == h
        and start["allocation_sha256"] == row["allocation_sha256"]
        and start["case"] == row["id"]
        and start["slot"] == row["slot"]
        and start["attempt"] == 1
        and datetime.fromisoformat(claim["claimed_at"])
        <= datetime.fromisoformat(start["start_utc"])
        <= datetime.fromisoformat(result["worker"]["acquired_at"]),
        "invalid claim and reset chronology",
    )
    run, audit = read(directory / "run.json"), read(directory / "online-audit.json")
    expected = {k: row[k] for k in ("visual_id", "scene_id", "task_id", "plan_id")}
    require(
        run["formal_identity"] == expected
        and result["worker"]["run_id"] == row["run_id"]
        and read(directory / "offline-truth.json")["scene"]
        == read(directory / "pixel-index.json")["scene"]
        == result["physical_reset"]["scenario"]
        == row["scene_id"],
        "crossed worker, reset, frame or trajectory scene",
    )
    for v in audit:
        original = v.get("original")
        identity = original["identity"] if original else v.get("identity")
        if identity:
            require(
                all(identity[k] == row[k] for k in ("run_id", "task_id", "plan_id"))
                and identity["episode_id"] == result["physical_reset"]["episode_id"]
                and all(identity[k] == result["worker"][k] for k in ("job_id", "lease_id")),
                "original contract or grounding identity crossed slots",
            )
        if original:
            require(original["contract"]["task_id"] == row["task_id"], "wrong original task")


def audit_slot(out, batch, row, h):
    directory = out / "trials" / row["id"] / "instance"
    ledger = out / "claims" / (row["id"] + ".json")
    observed = dict(
        **row, acquired=False, evidence_status="MISSING", reason="registered slot has no claim"
    )
    try:
        if not ledger.exists():
            require(
                not directory.exists() and not (directory.parent / "claim.json").exists(),
                "unclaimed instance or mirror",
            )
            return observed
        claim, claim_sha = checked_claim(out, batch, row, h)
        observed["claim_sha256"] = claim_sha
        if not (directory / "receipt.json").is_file():
            interrupted = directory / "interrupted.json"
            if interrupted.is_file():
                observed.update(
                    evidence_status="INTERRUPTED",
                    reason="claim owner stopped before terminal receipt",
                    interrupted=read(interrupted),
                    interruption_sha256=sha(interrupted),
                )
            else:
                observed["reason"] = "claimed without terminal or interruption receipt"
            return observed
        from scripts.graduation import g1_dual_trials as dual

        alloc, _ = load_case(out / "trials", batch, row)
        result = dual.audit_one(directory, row, alloc, h)
        require(result["claim_sha256"] == claim_sha, "receipt has different claim")
        formal_evidence(directory, row, result, h, claim)
        observed.update(result, evidence_status="ACQUIRED")
        observed.pop("reason")
        return observed
    except (ValueError, OSError, KeyError, TypeError, IndexError) as exc:
        observed.update(evidence_status="CORRUPT", reason=f"{type(exc).__name__}: {exc}")
        return observed
    finally:
        if not observed["acquired"]:
            observed["present_file_sha256"] = {
                name: sha(directory / name)
                for name in (
                    "started.json",
                    "acquisition-seal.json",
                    "receipt.json",
                    "interrupted.json",
                    "development-worker.db",
                )
                if (directory / name).is_file()
            }


def audit_all(repo, plan_file, plan, out, h, finalize_partial=False):
    batch, _ = check_batch(repo, plan_file, plan, out, h)
    results = [audit_slot(out, batch, row, h) for row in batch["cases"]]
    acquired = [r for r in results if r["acquired"]]
    for values in (
        [r["physical_reset"]["episode_id"] for r in acquired],
        [r["worker"]["job_id"] for r in acquired],
        [r["worker"]["lease_id"] for r in acquired],
    ):
        require(len(set(values)) == len(acquired), "reused physical reset, worker or lease")
    require(
        all(
            a["worker"]["released_at"] < b["worker"]["acquired_at"]
            for a, b in zip(acquired, acquired[1:], strict=False)
        ),
        "overlapping worker leases",
    )
    count = len(list((out / "claims").glob("*.json")))
    report = dict(
        schema="g1.formal-paired.acquisition.v1",
        release=RELEASE,
        scope=SCOPE,
        plan_sha256=PLAN_SHA,
        scene_binding_plan_sha256=build.SCENE_PLAN_SHA,
        allocation_sha256=h,
        runtime_build_sha256=batch["runtime_build_sha256"],
        cases=results,
        formal_claims=count,
        assigned_slots=8,
        actual_episodes=len(acquired),
        distinct_resets=len(acquired),
        actual_dispatched=sum(len(r["action_commands"]) for r in acquired),
        hardware_actions=0,
        task_model_calls=0,
        v10_claims=0,
    )
    require(
        count == len(batch["cases"]) or finalize_partial,
        "partial audit requires --finalize-partial to seal outstanding assignments",
    )
    raw = out / "trials/acquisition.json"
    if raw.exists():
        require(read(raw) == report, "original acquisition audit differs")
    else:
        write(raw, report)
    public = plan_file.with_name(ACQUISITION)
    if public.exists():
        require(sha(raw) == sha(public), "public acquisition differs")
    else:
        copy_once(raw, public)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("prepare", "issue", "preflight", "capture", "recover", "audit")
    )
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--allocation-sha256")
    parser.add_argument("--case")
    parser.add_argument("--finalize-partial", action="store_true")
    a = parser.parse_args()
    plan_file, out = a.plan.resolve(), a.out.absolute()
    repo, plan = build.layout(plan_file, out)
    if a.command == "prepare":
        build.prepare(repo, plan, out)
        print(sha(out / "runtime-source/runtime-build.json"))
        return
    if a.command in {"capture", "recover", "audit"}:
        require(a.allocation_sha256, "supply the preregistered batch SHA256")
    if a.command in {"capture", "recover"}:
        require(a.case in {c["id"] for c in plan["slots"]}, "unknown formal assignment")
    expected = (
        sha(plan_file.with_name("runtime-build.public.json"))
        if plan_file.with_name(REGISTRATION).exists()
        else None
    )
    frozen = build.verify_lock(out, expected)
    if not expected:
        parent, prior = build.parent_inputs(repo, plan)
        derived, _ = build.derived_build(repo, plan, parent, prior)
        require(frozen == derived, "unregistered runtime differs from the verified preparation")
    args = [a.command, "--plan", str(plan_file), "--out", str(out)]
    if a.allocation_sha256:
        args.extend(["--allocation-sha256", a.allocation_sha256])
    if a.case:
        args.extend(["--case", a.case])
    if a.finalize_partial:
        args.append("--finalize-partial")
    build.enter_runtime(out, args)
    with device_lock(out):
        if a.command == "issue":
            print(issue(repo, plan_file, plan, out))
        elif a.command == "capture":
            capture(repo, plan_file, plan, out, a.allocation_sha256, a.case)
        elif a.command == "recover":
            batch, _ = check_batch(repo, plan_file, plan, out, a.allocation_sha256)
            row = next(r for r in batch["cases"] if r["id"] == a.case)
            recover(out, batch, row, a.allocation_sha256)
        elif a.command == "audit":
            report = audit_all(repo, plan_file, plan, out, a.allocation_sha256, a.finalize_partial)
            print(
                json.dumps(
                    {k: report[k] for k in ("assigned_slots", "formal_claims", "actual_episodes")}
                )
            )
        elif a.allocation_sha256:
            check_batch(repo, plan_file, plan, out, a.allocation_sha256, dispatch=True)
            print("8 preregistered assignments verified; no claim or reset issued")
        else:
            _, templates, _, _ = checked_runtime(repo, plan, out)
            ready_device(templates, 8 * 2**31, out)
            print("Verified frozen source, EGL and both assemblies with zero claims and resets")


if __name__ == "__main__":
    main()
