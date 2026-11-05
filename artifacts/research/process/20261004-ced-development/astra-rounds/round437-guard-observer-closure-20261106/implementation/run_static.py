"""Run each declared static command once with the original bounded supervisor."""

import importlib.util
import json
from pathlib import Path

from run_validation import BASE, ROOT, ROUND, pin, save


def run():
    green = ROUND / "validation/green"
    green_result = json.loads((green / "result.json").read_text())
    assert green_result["returncode"] == 0 and not green_result["source_drift"]
    assert green_result["reaped"] and not green_result["remaining_live"]
    plan = json.loads((BASE / "round435-t7b-guarded-execution-20261105/plan.json").read_text())
    template = json.loads((green / "spec.json").read_text())
    pins = json.loads((green / "preflight/runtime-source-pins.json").read_text())["files"]
    assert all(pin(row["path"]) == row for row in pins)
    own_path = str(Path(__file__).resolve().relative_to(ROOT))
    pins = pins + [pin(own_path)]
    parent = ROUND / "validation/static"
    parent.mkdir(parents=True, exist_ok=False)
    supervisor_path = BASE / "round413-full-long-validation-20261103/bounded_stage.py"
    module_spec = importlib.util.spec_from_file_location("r437_static", supervisor_path)
    supervisor = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(supervisor)
    results = []
    for name, command in zip(("ruff", "format", "mypy"), plan["verification"]["static_argv"], strict=True):
        directory = parent / name
        directory.mkdir(exist_ok=False)
        env = {key: value.replace(str(green), str(directory)) for key, value in template["env"].items()}
        env.update(MYPY_CACHE_DIR=str(directory / "mypy-cache"), RUFF_CACHE_DIR=str(directory / "ruff-cache"))
        for key in ("TMPDIR", "XDG_CACHE_HOME"):
            Path(env[key]).mkdir(parents=True, exist_ok=True)
        save(directory / "preflight/runtime-source-pins.json", {"files": pins})
        spec = dict(id=f"r437-static-{name}", directory=str(directory), cwd=str(ROOT),
                    argv=[str(ROOT / command[0]), *command[1:]], env=env, ports=[],
                    timeout_s=60, attempt=1, scope="R437_DECLARED_STATIC_ONLY")
        save(directory / "spec.json", spec)
        supervisor.ROUND = directory
        supervisor.run(directory / "spec.json")
        result = json.loads((directory / "result.json").read_text())
        results.append({"name": name, "returncode": result["returncode"], "state": result["state"],
                        "source_drift": result["source_drift"], "remaining_live": result["remaining_live"]})
        if result["returncode"] != 0 or result["source_drift"] or result["remaining_live"]:
            break
    save(parent / "results.json", results)


if __name__ == "__main__":
    run()
