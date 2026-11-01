"""Execute only the two exact, bounded CPU checks in the immutable R383 plan."""

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
    plan = json.loads((BASE / "plan.json").read_text())
    for row in plan["inputs"]:
        path = Path(row["path"])
        if not path.is_absolute():
            path = ROOT / path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"], row["path"]
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == plan["head"]
    names = subprocess.check_output(["git", "ls-files", "-z", "--", "src", "tests"])
    sources = {str(ROOT / p.decode()) for p in names.split(b"\0") if p}
    sources.update(str((ROOT / row["path"]).resolve()) for row in plan["inputs"])
    assert all(Path(name).is_file() for name in sources)
    stages = plan["software_verification"]["stages"]
    deadline = time.time() + plan["software_verification"]["total_new_wall_seconds"]
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
        assert not directory.exists(), directory
        directory.mkdir(parents=True)
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
            and prerequisite.get("accepted") is True
            and len(cases) == spec["expected_pass"]
            and not bad
        )
        summary = {
            "stage": spec["name"], "accepted": accepted,
            "test_count": len(cases), "failed_error_skipped": len(bad),
            "prerequisite_accepted": prerequisite.get("accepted"),
            "driver_exit": completed.returncode, "result": result,
        }
        save(directory / "acceptance.json", summary)
        results.append(summary)
        print(json.dumps({key: value for key, value in summary.items() if key != "result"}), flush=True)
        if not accepted:
            save(BASE / "verification-failure.json", {"stage": spec["name"], "results": results})
            raise RuntimeError("R383 check failed; preserve evidence and request the next Astra plan")
    save(BASE / "verification-summary.json", {
        "schema": "bigsmall.r383.checkpoint-verification.v1", "accepted": True,
        "software_tests_passed": sum(row["test_count"] for row in results),
        "stages": results, "new_real_runs": 0, "formal_acceptance_claim": False,
        "full_suite_run": False, "product_or_test_edits": False,
    })
    with (BASE / "progress.md").open("a") as stream:
        stream.write("\n- Task 2: complete; exact 58 temporal and 9 fixture/diagnostic/smoke tests passed, prerequisites accepted, sources unchanged, owned processes reaped. No retries or new real runs.\n")


if __name__ == "__main__":
    main()
