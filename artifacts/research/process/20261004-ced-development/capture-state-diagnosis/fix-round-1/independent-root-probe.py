"""Independent fake-only replay of the original three journal failure variants."""
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent.parent
ROOT=HERE.parents[4]
spec=importlib.util.spec_from_file_location("root_diagnosis_fakes", HERE/"test_cpu.py")
tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests)
module=tests.module
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
header=json.loads((HERE/"header.json").read_text());module.verify_inputs(header)
assert sha(HERE/"test_cpu.py")==header["cpu_test_sha256"]
assert not (HERE/"diagnostic-1").exists()
prior=HERE.parent/"t7b-continuous-visibility"
original=json.loads((prior/"attempt-1-file-hashes.json").read_text())
for row in original["files"]:assert sha(prior/row["file"])==row["sha256"]
results={}
with tempfile.TemporaryDirectory(prefix="root-diagnosis-lifecycle-") as root_tmp:
 for case in ("normal","begin_journal","end_journal","failed_journal_masks_camera"):
  directory=Path(root_tmp)/case;directory.mkdir()
  backend,reference=tests.fake_backend(),tests.fake_reference()
  renderer=tests.FakeRenderer();camera_error=ValueError("qualified original camera error")
  rows=[]
  def capture(data,**kwargs):
   if case=="failed_journal_masks_camera":raise camera_error
   renderer.update_scene(data,camera=0);renderer.render();renderer.render()
   return SimpleNamespace(latency_ms=0.),(),{},("equal","equal")
  def emit(event,**payload):
   if (case=="begin_journal" and event=="CAPTURE_BEGIN" or case=="end_journal" and event=="CAPTURE_END" or case=="failed_journal_masks_camera" and event=="CAPTURE_FAILED"):
    raise OSError("qualified "+event+" journal error")
   rows.append({"event":event,**payload})
  backend._camera=SimpleNamespace(_renderer=renderer,_capture=capture)
  journal=SimpleNamespace(ensure=lambda _:None,emit=emit)
  store=module.SnapshotStore(directory/"snapshots",reference)
  probe=module.CaptureProbe(backend,reference,store,journal,directory)
  caught=None
  try:probe.capture()
  except BaseException as error:caught=error
  if case=="normal":
   assert caught is None and (probe.calls,probe.completed,probe.failed)==(1,1,0)
  else:
   assert (probe.calls,probe.completed,probe.failed)==(1,0,1)
   if case=="failed_journal_masks_camera":
    assert caught is camera_error and "CAPTURE_FAILED" in caught.__notes__[0]
   else:assert isinstance(caught,OSError)
  assert probe.calls==probe.completed+probe.failed
  assert probe.camera_calls_started==(0 if case=="begin_journal" else 1)
  assert "update_scene" not in renderer.__dict__ and "render" not in renderer.__dict__
  results[case]={"allocated":probe.calls,"completed":probe.completed,"failed":probe.failed,"camera_calls_started":probe.camera_calls_started,"exception":type(caught).__name__ if caught else None,"original_camera_exception_preserved":caught is camera_error,"notes":getattr(caught,"__notes__",[]),"fake_renderer_delegations":len(renderer.calls)}
for row in original["files"]:assert sha(prior/row["file"])==row["sha256"]
module.verify_inputs(header)
result={"status":"PASS_SCOPED_NO_ACTUAL_CALLS","cases":results,"script_sha256":sha(HERE/"run_once.py"),"test_sha256":sha(HERE/"test_cpu.py"),"header_sha256":sha(HERE/"header.json"),"source_count":header["source_count"],"source_bytes":header["source_bytes"],"dependency_files":len(header["environment"]["files"]),"original21_preserved":True,"diagnostic_not_run":True}
out=HERE/"fix-round-1/independent-root-counterexamples.json"
with out.open("x") as stream:stream.write(json.dumps(result,indent=2)+"\n")
print(json.dumps(result))
