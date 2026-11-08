"""CPU evidence-format checks; no model construction or generation."""

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
R486 = HERE.parent / "round486-taichu-no-think-best-profile-20261108"
sys.path.insert(0, str(R486 / "implementation"))
from evidence_codec import normalize, write_evidence


def main():
    checks = []
    ordinary = {"a": [1, None, True, "hello"], "b": {"number": 1.25}}
    assert normalize(ordinary) == ordinary
    checks.append("ordinary JSON content unchanged")
    original = {"empty": set(), "a/b": {"~key": frozenset(["b", "a"])},
                "mixed": {1, "1", (2, 3)}}
    before = copy.deepcopy(original)
    events = []
    safe = normalize(original, events=events)
    assert original == before and isinstance(original["empty"], set)
    assert safe["empty"] == [] and safe["a/b"]["~key"] == ["a", "b"]
    assert {event["json_pointer"] for event in events} == {"/empty", "/a~1b/~0key", "/mixed"}
    assert safe == normalize(original)
    checks += ["empty and nonempty set/frozenset", "heterogeneous JSON-compatible set",
               "stable ordering", "JSON Pointer escaping", "input containers not mutated"]
    with tempfile.TemporaryDirectory(prefix="round487-codec-") as temporary:
        target = Path(temporary) / "evidence.json"
        write_evidence(target, original)
        assert json.loads(target.read_text()) == safe
        sidecar = json.loads(target.with_name(target.name + ".serialization.json").read_text())
        assert sidecar["representations"] == events
        checks.append("sidecar records actual original types and paths")
        unknown = Path(temporary) / "unknown.json"
        try:
            write_evidence(unknown, {"bad": object()})
        except TypeError:
            assert not unknown.exists()
        else:
            raise AssertionError("unknown object accepted")
        cycle = []
        cycle.append(cycle)
        for name, value in [("cycle", cycle), ("nonfinite", float("nan"))]:
            path = Path(temporary) / (name + ".json")
            try:
                write_evidence(path, value)
            except ValueError:
                assert not path.exists()
            else:
                raise AssertionError(name + " accepted")
        checks += ["unknown object rejected before file creation", "cycles rejected", "nonfinite rejected"]
    from transformers.utils.loading_report import LoadStateDictInfo
    import transformers.utils.loading_report as loading_report

    loading = LoadStateDictInfo(missing_keys=set(), unexpected_keys={"b", "a"},
        mismatched_keys={("weight", (1, 2), (2, 2))}, error_msgs=[], conversion_errors={}, skipped_pp_keys=set())
    info = loading.to_dict()
    normalized = normalize(info)
    assert normalized["missing_keys"] == [] and normalized["unexpected_keys"] == ["a", "b"]
    assert isinstance(info["unexpected_keys"], set)
    checks.append("actual Transformers LoadingInfo structure, synthetic keys, no model load")
    source = Path(loading_report.__file__)
    result = {"status": "PASS", "checks": checks, "cpu_only": True, "model_loads": 0,
              "generation_calls": 0, "loading_info_source": str(source),
              "loading_info_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    with (HERE / "codec-verification.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
