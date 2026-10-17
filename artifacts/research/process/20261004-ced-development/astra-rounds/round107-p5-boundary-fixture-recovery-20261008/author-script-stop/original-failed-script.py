from pathlib import Path
r=Path('artifacts/research/process/20261004-ced-development/astra-rounds/round107-p5-boundary-fixture-recovery-20261008/implementation')
script=r'''from pathlib import Path
import json, gzip
r=Path('artifacts/research/process/20261004-ced-development/astra-rounds/round107-p5-boundary-fixture-recovery-20261008')
i=r/'implementation'
replacements={}
def change(path,old,new):
 p=Path(path); s=p.read_text()
 if s.count(old)!=1: raise ValueError('exact replacement unavailable: '+path)
 p.write_text(s.replace(old,new,1)); replacements.setdefault(path,[]).append({'old':old,'new':new})
window='src/cloud_edge_robot_arm/vision/operational_windows.py'
change(window, '        if cls is not OperationalWindowOwner or worker not in _PENDING:\n', '        from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker\n\n        if cls is not OperationalWindowOwner or type(worker) is not SimulationWorker:\n            raise OperationalTimeError("unissued or already consumed startup capability")\n        if worker not in _PENDING:\n')
bootstrap='src/cloud_edge_robot_arm/repositories/event_autonomy/visual_bootstrap.py'
change(bootstrap,'        body = dict(_plain(raw))\n        if (\n            body.pop("schema_version", None) != "visual.bootstrap.definition.v1"','        normalized = _plain(raw)\n        body = dict(normalized)\n        if (\n            body.pop("schema_version", None) != "visual.bootstrap.definition.v1"')
change(bootstrap,'        if canonical(result.to_payload()) != canonical(raw):\n            raise ValueError("bootstrap definition changed during decoding")','        if canonical(result.to_payload()) != canonical(normalized):\n            raise ValueError("bootstrap definition changed during decoding")')
test='tests/test_operational_windows.py'
change(test,'import copy\nimport importlib\n','import copy\nimport gzip\nimport hashlib\nimport importlib\n')
change(test,'from contextvars import copy_context\n','from contextlib import contextmanager\nfrom contextvars import copy_context\n')
# Exactly the two positive condition fixtures; no other robot state changes.
s=Path(test).read_text(); old='observation, RobotState(connected=True), operational_reference=reference'; new='observation, RobotState(connected=True, stopped=True), operational_reference=reference'
if s.count(old)!=2: raise ValueError('two condition fixtures required')
Path(test).write_text(s.replace(old,new)); replacements.setdefault(test,[]).append({'old':old,'new':new,'count':2})
change(test,'        from cloud_edge_robot_arm.vision.worker_runtime import VisualWorkerRuntime\n\n        replay = VisualWorkerRuntime(', '        with pytest.raises(OperationalTimeError):\n            module.OperationalWindowOwner.from_worker({}, job_id=job.job_id)\n        from cloud_edge_robot_arm.vision.worker_runtime import VisualWorkerRuntime\n\n        replay = VisualWorkerRuntime(')
helper='''def marker_cpu_inputs():
    """Pinned historical pixels for CPU logic only; never new live/admission evidence."""
    from cloud_edge_robot_arm.contracts.models import TaskTarget
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    root = Path(__file__).resolve().parents[1]
    fixture = root / "tests/fixtures/p5_marker_source_v1"
    provenance = json.loads((fixture / "provenance.json").read_text())
    assert provenance["scope"] == "SOFTWARE_ONLY_DEVELOPMENT_DIAGNOSTIC_REUSE_NOT_NEW_ACTUAL"
    compressed = (fixture / "observation-full.json.gz").read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == (
        "21bf6d3787eca744af20c205469b8c56c51b46cd14e53068f12d7dbf1f251fca"
    )
    pixels = gzip.decompress(compressed)
    assert hashlib.sha256(pixels).hexdigest() == provenance["original_frame"]["sha256"]
    module = importlib.import_module("cloud_edge_robot_arm.vision.marker_association")
    observation = RGBDObservation.model_validate_json(pixels)
    registration = module.load_marker_registration(
        fixture / "registration.json",
        expected_registry_sha256="3e9cf0c1d44116cec83d913e003b53ec8157d09acf36164078825ae6c836c5bc",
        root=root,
    )
    assert registration.sources_valid()
    assert registration.admission_scope == "DEVELOPMENT_ONLY"
    context = module.marker_frame_context(
        observation,
        registration,
        task_id="diagnostic-task",
        task_target=TaskTarget(
            object_id="object", object_class="cube", target_region_id="target_region"
        ),
        instruction="pick the red cube and place it in the green target region",
        context_hash="1" * 64,
        role_bundle_hash="2" * 64,
        active_asset_sha256=registration.pose_marker.marked_asset_sha256,
        plan_version=1,
        command_seq=1,
    )
    return module, observation, registration, context


@contextmanager
def supervision_cpu_utc(monkeypatch, runtime, claim):
    """One software node's UTC basis; real SQL/source/lease and TTL gates still run."""
    stored = runtime.source.event_repository.get_visual_supervision(runtime.episode_id)
    payload = stored.to_payload()
    basis = datetime.now(UTC)
    assert basis >= datetime.fromisoformat(payload["claims"][claim.claim_id]["reserved_at"])
    assert all(basis >= datetime.fromisoformat(item["committed_at"]) for item in payload["history"])

    class CpuUtcDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return basis.replace(tzinfo=None) if tz is None else basis.astimezone(tz)

    with monkeypatch.context() as local:
        for name in (
            "cloud_edge_robot_arm.vision.worker_owner",
            "cloud_edge_robot_arm.vision.worker_runtime",
            "cloud_edge_robot_arm.repositories.event_autonomy.sqlite",
        ):
            local.setattr(importlib.import_module(name), "datetime", CpuUtcDateTime)
        yield basis


'''
change(test,'def frozen_json(value):\n',helper+'def frozen_json(value):\n')
s=Path(test).read_text(); start=s.index('            payload = observation.model_dump(mode="json")\n',s.index('        elif category == "supervision":')); end=s.index('        elif category == "grounding":',start)
old=s[start:end]; new='            with supervision_cpu_utc(monkeypatch, runtime, claim) as software_now:\n'+''.join('    '+line if line.strip() else line for line in old.splitlines(keepends=True)); new=new.replace('captured_at=datetime.now(UTC).isoformat(),','captured_at=software_now.isoformat(),',1)
change(test,old,new)
change(test,'            from tests.test_marker_association import inputs\n\n            marker, original, registration, context = inputs()','\n            marker, original, registration, context = marker_cpu_inputs()')
change(test,'            assert (\n                associate_marker_target(fresh, registration, context).status == "OBSERVED_CANDIDATE"\n            )','            positive = associate_marker_target(fresh, registration, context)\n            assert positive.status == "OBSERVED_CANDIDATE"\n            assert positive.admission_status == "NOT_ADMITTED"')
(i/'semantic-edit-spec.json').write_text(json.dumps(replacements,ensure_ascii=False,indent=2)+'\n')
for p in replacements:
 q=i/'semantic-after'/p; q.parent.mkdir(parents=True,exist_ok=True); q.write_bytes(Path(p).read_bytes())
spec=json.loads((r/'fixture-spec.json').read_text())
for path, payload in [(spec['fixture_paths'][1],spec['registration_payload']),(spec['fixture_paths'][2],spec['provenance_payload'])]:
 p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f: f.write(json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
original=Path(spec['provenance_payload']['original_frame']['path']).read_bytes()
with Path(spec['fixture_paths'][0]).open('xb') as f: f.write(gzip.compress(original,mtime=0))
runner=(r.parent/'round106-p5-domain-schema-completeness-20261008/implementation/run-command.py').read_text().replace('round106-p5-domain-schema-completeness-20261008','round107-p5-boundary-fixture-recovery-20261008')
(i/'run-command.py').write_text(runner)
(i/'progress.md').write_text('# R107 进度\n\nR108 metadata恢复exit0。三Python限定语义与三个固定spec夹具已写；七保护源未改。supervision仅原节点三模块datetime局部context，真实SQL/lease/source/UTC veto保留。尚未消费六验证预算；下一步唯一I整理与formatter。\n')
print('R107 semantic source/fixtures saved; budgets unused')
'''
(r/'apply-semantic.py').write_text(script)
