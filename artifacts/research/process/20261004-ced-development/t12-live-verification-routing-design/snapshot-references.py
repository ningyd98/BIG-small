import ast, hashlib, json, pathlib
root=pathlib.Path('/home/ningyd/文档/ChatGPT/BIGsmall')
base=root/'artifacts/research/process/20261004-ced-development/t12-visual-owner-repository/fix-round-1'
out=root/'artifacts/research/process/20261004-ced-development/t12-live-verification-routing-design'
refs=[
'repositories/event_autonomy/protocol.py','repositories/event_autonomy/memory.py','repositories/event_autonomy/sqlite.py','repositories/event_autonomy/visual_owner.py',
'edge/recovery/lifecycle.py','edge/recovery/verification_router.py','edge/recovery/retry_budget.py','vision/owner_registration.py','vision/action_evidence.py','vision/runtime_binding.py','vision/capture.py','vision/observations.py',
'edge/evidence/conditions.py','edge/evidence/models.py','edge/evidence/validator.py','edge/runtime/skill_executor.py','edge/safety/shield.py','contracts/models.py','auto_mode/runtime_events.py','cloud/replanning/apply_service.py','simulation/mujoco/backend.py','simulation/mujoco/skill_robot.py']
entries={f'src/cloud_edge_robot_arm/{p}':('OWNER_FIX1_ARCHIVE',base/'source'/f'src/cloud_edge_robot_arm/{p}') for p in refs}
for p in ['vision/execution.py','vision/evaluation.py','simulation_runtime/worker.py']:
 rel=f'src/cloud_edge_robot_arm/{p}'; entries[rel]=('QUIET_RUNTIME_SNAPSHOT',root/rel)
entries['artifacts/research/process/20261004-ced-development/t12-worker-owner-runtime/report.md']=('FROZEN_WORKER_OWNER_REPORT',root/'artifacts/research/process/20261004-ced-development/t12-worker-owner-runtime/report.md')
manifest={}; provenance={}
base_manifest=json.loads((base/'source-hashes.json').read_text())
for rel,(kind,src) in entries.items():
 data=src.read_bytes(); digest=hashlib.sha256(data).hexdigest()
 if kind=='OWNER_FIX1_ARCHIVE': assert base_manifest[rel]==digest,rel
 if rel.endswith('.py'): ast.parse(data.decode(),filename=rel)
 target=out/'source'/rel;target.parent.mkdir(parents=True,exist_ok=True);assert not target.exists();target.write_bytes(data)
 manifest[rel]=digest;provenance[rel]={'source':str(src),'kind':kind,'sha256':digest}
(out/'source-hashes.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
(out/'reference-provenance.json').write_text(json.dumps(provenance,indent=2,sort_keys=True)+'\n')
(out/'ownership.json').write_text(json.dumps(dict(owned_production_files=[],scope='DESIGN_ONLY',references=len(entries),not_runnable_transitive_release=True,actual_calls=0),indent=2)+'\n')
print(json.dumps(dict(references=len(entries),manifest_sha256=hashlib.sha256((out/'source-hashes.json').read_bytes()).hexdigest(),ast='PASS',production_edits=0),indent=2))
