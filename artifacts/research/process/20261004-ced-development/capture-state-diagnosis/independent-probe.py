"""CPU-only fake journal failure counterexamples and immutable-source checks."""

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PRIOR = HERE.parent / "t7b-continuous-visibility"
sha = lambda data: hashlib.sha256(data).hexdigest()
spec = importlib.util.spec_from_file_location("independent_diagnosis_fakes", HERE / "test_cpu.py")
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
module = tests.module
header = json.loads((HERE / "header.json").read_text())
module.verify_inputs(header)  # Metadata and source/dependency reads only.
manifest = json.loads((HERE / "execution-source-hashes.json").read_text())
archives = json.loads((HERE / "execution-archive-index.json").read_text())
assert len(manifest) == 33 and set(manifest) == set(archives)
assert sum((ROOT / name).stat().st_size for name in manifest) == 440906
assert all(sha((ROOT / name).read_bytes()) == sha((HERE.parent / archives[name]["archive"]).read_bytes()) == expected for name, expected in manifest.items())
assert sha((HERE / "test_cpu.py").read_bytes()) == header["cpu_test_sha256"]
original_sources = json.loads((PRIOR / "execution-source-hashes.json").read_text())
assert all(manifest[name] == expected for name, expected in original_sources.items())
original_files = {str(path.relative_to(PRIOR / "attempt-1")): sha(path.read_bytes())
                  for path in (PRIOR / "attempt-1").rglob("*") if path.is_file()}
assert not (HERE / "diagnostic-1").exists()
result = {
    "scope": "FAKE_ONLY_CPU_NO_MUJOCO_RENDERER_PHYSICS_MODEL_OR_DIAGNOSTIC_EXECUTION",
    "script_sha256": sha((HERE / "run_once.py").read_bytes()),
    "test_sha256": sha((HERE / "test_cpu.py").read_bytes()),
    "source_count": 33, "source_bytes": 440906, "live_archive_dependency_match": True,
    "dependency_pinned_files": len(header["environment"]["files"]),
    "original_32_sources_unchanged": True,
    "original_actual_file_hashes": original_files,
    "cases": {},
}
with tempfile.TemporaryDirectory(prefix="diagnosis-fake-review-") as temporary:
    for kind in ("normal", "begin_journal", "end_journal", "failed_journal_masks_camera"):
        directory = Path(temporary) / kind
        directory.mkdir()
        backend, reference = tests.fake_backend(), tests.fake_reference()
        renderer = tests.FakeRenderer()
        camera_error = ValueError("qualified original camera error")

        def capture(data, **kwargs):
            if kind == "failed_journal_masks_camera":
                raise camera_error
            renderer.update_scene(data, camera=0)
            renderer.render()
            renderer.render()
            return SimpleNamespace(latency_ms=0.0), (), {}, ("equal", "equal")

        backend._camera = SimpleNamespace(_renderer=renderer, _capture=capture)
        rows = []

        def emit(event, **payload):
            if (kind == "begin_journal" and event == "CAPTURE_BEGIN"
                or kind == "end_journal" and event == "CAPTURE_END"
                or kind == "failed_journal_masks_camera" and event == "CAPTURE_FAILED"):
                raise OSError("qualified " + event + " journal error")
            rows.append({"event": event, **payload})

        journal = SimpleNamespace(ensure=lambda _: None, emit=emit)
        store = module.SnapshotStore(directory / "snapshots", reference)
        probe = module.CaptureProbe(backend, reference, store, journal, directory)
        caught = None
        try:
            probe.capture()
        except Exception as error:
            caught = {"type": type(error).__name__, "reason": str(error),
                      "is_original_camera_exception": error is camera_error,
                      "context_is_original_camera_exception": error.__context__ is camera_error}
        result["cases"][kind] = {
            "capture_started": probe.calls, "capture_completed": probe.completed,
            "capture_failed": probe.failed,
            "started_equals_completed_plus_failed": probe.calls == probe.completed + probe.failed,
            "fake_renderer_delegations": len(renderer.calls), "exception": caught,
            "events": [row["event"] for row in rows],
        }
        if kind == "normal":
            assert caught is None and (probe.calls, probe.completed, probe.failed) == (1, 1, 0)
        elif kind == "begin_journal":
            assert caught["type"] == "OSError" and (probe.calls, probe.completed, probe.failed) == (1, 0, 0)
            assert renderer.calls == []
        elif kind == "end_journal":
            assert caught["type"] == "OSError" and (probe.calls, probe.completed, probe.failed) == (1, 1, 1)
        else:
            assert caught["type"] == "OSError" and not caught["is_original_camera_exception"]
            assert caught["context_is_original_camera_exception"]
assert all(sha((ROOT / name).read_bytes()) == expected for name, expected in manifest.items())
assert all(sha((PRIOR / "attempt-1" / name).read_bytes()) == expected for name, expected in original_files.items())
assert not (HERE / "diagnostic-1").exists()
(HERE / "independent-counterexamples.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"qualified": list(result["cases"]), "source33_dependency_match": True,
                  "original_sources_and_actual_unchanged": True, "no_actual_diagnostic": True}))
