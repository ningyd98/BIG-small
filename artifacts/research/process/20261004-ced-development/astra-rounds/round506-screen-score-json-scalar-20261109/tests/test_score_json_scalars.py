import ast
import importlib.util
import io
import json
import sys
from pathlib import Path
import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
SOURCE = HERE.parent / "round505-ordered-small-vlm-screen-20261109/implementation/score_candidate.py"
sys.path.insert(0, str(SOURCE.parent))
spec = importlib.util.spec_from_file_location("score_candidate_scalar_test", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
tree = ast.parse(SOURCE.read_text())
calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
         and isinstance(n.func.value, ast.Name) and n.func.value.id == "json" and n.func.attr in ("dump", "dumps")]


def output(path_kind, value):
    node = next(n for n in calls if n.func.attr == path_kind)
    stream = io.StringIO()
    scope = {**module.__dict__, "result": {"metrics": value}, "stream": stream}
    result = eval(compile(ast.Expression(node), str(SOURCE), "eval"), scope)
    encoded = stream.getvalue() if path_kind == "dump" else result
    return json.dumps(json.loads(encoded)["metrics"])


@pytest.mark.parametrize("kind", ["dump", "dumps"])
def test_nested_scalars_retain_types_and_values(kind):
    result = {"rows": [{"yes": np.bool_(True), "no": np.bool_(False), "signed": np.int64(-9007199254740993),
                         "unsigned": np.uint64(9007199254740995), "f32": np.float32(0.125), "f64": np.float64(0.375)}],
              "ordinary": (None, True, 7, 1.25)}
    decoded = json.loads(output(kind, result))
    expected = {"yes": True, "no": False, "signed": -9007199254740993, "unsigned": 9007199254740995,
                "f32": float(np.float32(0.125)), "f64": float(np.float64(0.375))}
    assert decoded["rows"][0] == expected
    assert {k: type(v) for k, v in decoded["rows"][0].items()} == {k: type(v) for k, v in expected.items()}
    assert decoded["ordinary"] == [None, True, 7, 1.25]


@pytest.mark.parametrize("kind", ["dump", "dumps"])
@pytest.mark.parametrize("cast", [float, np.float32, np.float64])
@pytest.mark.parametrize("number", ["nan", "inf", "-inf"])
def test_nonfinite_rejected(kind, cast, number):
    with pytest.raises(ValueError):
        output(kind, {"rows": [{"bad": cast(number)}]})


@pytest.mark.parametrize("kind", ["dump", "dumps"])
@pytest.mark.parametrize("value", [object(), np.array([1, 2]), complex(1, 2)])
def test_unknown_objects_rejected(kind, value):
    with pytest.raises(TypeError):
        output(kind, {"rows": [{"bad": value}]})


def test_output_is_exclusive_score02(tmp_path):
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.With) and "score-03.json" in ast.unparse(n.items[0].context_expr))
    assert ast.unparse(node.items[0].context_expr).endswith('.open(\'x\')')
    target = tmp_path / "score-03.json"
    target.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        eval(compile(ast.Expression(node.items[0].context_expr), str(SOURCE), "eval"), {"out": tmp_path})
    assert target.read_bytes() == b"original"
