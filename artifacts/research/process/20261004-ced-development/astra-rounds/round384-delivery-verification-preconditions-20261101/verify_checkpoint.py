"""Execute only the two exact, bounded CPU checks in the R384 preconditions plan; original R383 failure remains immutable."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET


BASE = Path(__file__).resolve().parent
ROOT = Path.cwd().resolve()


def save(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main() -> None:
    correction = json.loads((BASE / "plan.json").read_text())
    original_base = BASE.with_name("round383-workspace-github-delivery-20261101")
    plan = json.loads((original_base / "plan.json").read_text())
    for row in correction["inputs"] + plan["inputs"]:
        path = Path(row["path"])
        if not path.is_absolute():
            path = ROOT / path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"], row["path"]
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == plan["head"]
    names = subprocess.check_output(["git", "ls-files", "-z", "--", "src", "tests"])
    sources = {str(ROOT / p.decode()) for p in names.split(b"\0") if p}
    sources.update(str((ROOT / row["path"]).resolve()) for row in plan["inputs"])
    assert all(Path(name).is_file() for name in sources)
    sources.update(str((ROOT / row["path"]).resolve()) for row in correction["inputs"])
    sources.update((str(BASE / "plan.json"), str(BASE / "plan.md"), str(Path(__file__).resolve())))
    stages = json.loads(json.dumps(correction["execution"]["stages"]).replace(str(original_base), str(BASE)))
    preparation = []
    for spec in stages:
        directory = Path(spec["directory"])
        assert directory.is_relative_to(BASE) and not directory.exists() and not directory.is_symlink()
        wanted = {Path(value) for value in spec["precreate_and_verify_directories"]}
        wanted.update(Path(spec["env"][key]) for key in correction["execution"]["output_directory_env_keys"])
        wanted.update(Path(spec["env"][key]).parent for key in correction["execution"]["output_file_env_keys"])
        assert directory in wanted
        for path in sorted(wanted, key=lambda path: len(path.parts)):
            assert path.is_absolute() and path.is_relative_to(directory)
            assert not any(part.is_symlink() for part in (path, *path.parents))
            path.mkdir(parents=True, exist_ok=True)
            assert path.is_dir() and not any(part.is_symlink() for part in (path, *path.parents))
        for name in spec["must_be_absent_before_launch"]:
            assert not (directory / name).exists() and not (directory / name).is_symlink()
        assert not list((directory / "persistent-basetemp").iterdir())
        assert spec["env"]["REAL_MOTION_DISPATCH_ENABLED"] == "false"
        assert "SIMULATION_RUNTIME_DB" not in spec["env"]
        preparation.append({"stage": spec["name"], "all_exist_non_symlink_inside_new_stage": True,
                            "directories": sorted(str(path) for path in wanted), "new_empty_basetemp": True})
    save(BASE / "preflight-directories.json", preparation)
    deadline = time.time() + correction["execution"]["budget_seconds"]
    driver = ROOT / plan["software_verification"]["driver"]
    save(BASE / "verification-clock.json", {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "round_end_epoch_s": deadline,
        "source_file_count": len(sources),
        "driver_sha256": hashlib.sha256(driver.read_bytes()).hexdigest(),
    })
    results = []
    for original in stages:
        spec = dict(original)
        directory = Path(spec["directory"])
        assert directory.is_dir() and not directory.is_symlink(), directory
        spec["round_end_epoch_s"] = deadline
        spec["source_paths"] = sorted(sources)
        spec["permission_profile"] = "danger-full-access; approval=never; network enabled; clean allowlisted child environment; real motion disabled"
        assert "SIMULATION_RUNTIME_DB" not in spec["env"]
        assert not any("API_KEY" in key or "TOKEN" in key for key in spec["env"])
        spec_path = directory / "spec.json"
        save(spec_path, spec)
        command = [str(ROOT / ".venv/bin/python"), str(driver), str(spec_path)]
        with (directory / "driver.stdout.log").open("xb") as out, (directory / "driver.stderr.log").open("xb") as err:
            completed = subprocess.run(command, cwd=ROOT, env=spec["env"], stdout=out, stderr=err, check=False)
        result = json.loads((directory / "result.json").read_text())
        prerequisite = json.loads((directory / "prerequisite.json").read_text())
        tree = ET.parse(directory / "junit.xml")
        cases = tree.findall(".//testcase")
        bad = [case for case in cases if any(case.find(kind) is not None for kind in ("failure", "error", "skipped"))]
        accepted = (
            completed.returncode == 0
            and result.get("state") == "FINISHED"
            and result.get("returncode") == 0
            and result.get("source_drift") == []
            and result.get("remaining_live") == []
            and result.get("errors") == []
            and result.get("reaped") is True
            and prerequisite.get("accepted_prerequisite") is True
            and len(cases) == spec["expected_pass"]
            and not bad
        )
        summary = {
            "stage": spec["name"], "accepted": accepted,
            "test_count": len(cases), "failed_error_skipped": len(bad),
            "prerequisite_accepted": prerequisite.get("accepted_prerequisite"),
            "driver_exit": completed.returncode, "result": result,
        }
        save(directory / "acceptance.json", summary)
        results.append(summary)
        print(json.dumps({key: value for key, value in summary.items() if key != "result"}), flush=True)
        if not accepted:
            save(BASE / "verification-failure.json", {"stage": spec["name"], "results": results})
            raise RuntimeError("R384 check failed; preserve evidence and request the next Astra plan")
    save(BASE / "verification-summary.json", {
        "schema": "bigsmall.r384.checkpoint-verification.v1", "accepted": True,
        "software_tests_passed": sum(row["test_count"] for row in results),
        "stages": results, "new_real_runs": 0, "formal_acceptance_claim": False,
        "full_suite_run": False, "product_or_test_edits": False,
    })
    with (BASE / "progress.md").open("a") as stream:
        stream.write("\n- Task 2: complete; exact 58 temporal and 9 fixture/diagnostic/smoke tests passed, prerequisites accepted, sources unchanged, owned processes reaped. No retries or new real runs.\n")


if __name__ == "__main__":
    main()
