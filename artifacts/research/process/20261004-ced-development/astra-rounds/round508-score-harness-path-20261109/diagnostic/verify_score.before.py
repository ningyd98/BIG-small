"""R506 test-only interception of old/new score computation; zero model calls."""
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

HERE = Path(__file__).resolve().parents[1]
R505 = HERE.parent / "round505-ordered-small-vlm-screen-20261109"
SOURCE = R505 / "implementation/score_candidate.py"
ROOT = R505.parents[5]
sys.path.insert(0, str(SOURCE.parent))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    captured = []
    class Done(Exception):
        pass
    def save(result, stream, **kwargs):
        captured.append(result)
        raise Done()
    module.json = SimpleNamespace(loads=json.loads, dump=save)
    original = Path.open
    with tempfile.TemporaryDirectory() as folder:
        def opened(path, *args, **kwargs):
            if path.name in ("score-01.json", "score-02.json"):
                return original(Path(folder) / path.name, *args, **kwargs)
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", opened):
            try:
                module.score("03-lens")
            except Done:
                pass
    assert len(captured) == 1
    return captured[0]


def normalize(value):
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items() if k != "scorer_sha256"}
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    if isinstance(value, np.bool_):
        result = bool(value)
        assert type(result) is bool and result == value
        return result
    if isinstance(value, np.integer):
        result = int(value)
        assert type(result) is int and result == value
        return result
    if isinstance(value, np.floating):
        result = float(value)
        assert type(result) is float and result == value
        return result
    return value


old = capture(HERE / "diagnostic/score_candidate.before.py", "before")
new = capture(SOURCE, "after")
assert normalize(old) == normalize(new)
out = R505 / "candidates/03-lens"
with (out / "score-02.stdout").open("xb") as stdout, (out / "score-02.stderr").open("xb") as stderr:
    process = subprocess.run([sys.executable, str(SOURCE), "03-lens"], cwd=ROOT, stdout=stdout, stderr=stderr, timeout=300)
assert process.returncode == 0
def strict(path):
    def invalid(value):
        raise ValueError(value)
    return json.loads(path.read_text(), parse_constant=invalid)
result = strict(out / "score-02.json")
assert len(result["rows"]) == result["completed_calls"] == 50
assert strict(out / "score-02.stdout") == {k: v for k, v in result.items() if k != "rows"}
assert normalize(result) == normalize(new)
assert result["scorer_sha256"] == sha(SOURCE)
raw = json.loads((HERE / "diagnostic/raw-before.json").read_text())
for row in raw:
    path = ROOT / row["path"]
    assert path.stat().st_size == row["bytes"] and sha(path) == row["sha256"]
for row in json.loads((HERE / "failure-inputs.json").read_text()):
    if row["path"].endswith("implementation/score_candidate.py"):
        continue
    path = ROOT / row["path"]
    assert path.stat().st_size == row["bytes"] and sha(path) == row["sha256"]
report = {"status": "PASS", "raw_files_unchanged": len(raw), "old_new_computation_semantically_equal": True,
          "permitted_difference": "scorer_sha256 only", "rows": 50, "returncode": process.returncode,
          "model_load_increment": 0, "generation_call_increment": 0,
          "score02_sha256": sha(out / "score-02.json"), "python": sys.executable}
with (HERE / "diagnostic/verification.json").open("x") as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False))
