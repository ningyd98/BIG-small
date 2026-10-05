import hashlib,json,sys,tempfile
from pathlib import Path
from tests.test_research_risk_replay import numeric_fixture, parameters, registered_replay
from cloud_edge_robot_arm.research.risk_replay import RiskArtifactAuditor,replay_diagnostic_candidates,risk_replay_environment
from cloud_edge_robot_arm.research.risk_sources import _plain
ROOT=Path('/home/ningyd/文档/ChatGPT/BIGsmall')
OUT=ROOT/'artifacts/research/process/20261004-ced-development/t9-risk-replay-module'
manifest=json.loads((OUT/'source-hashes.json').read_text())
allocations,rows=numeric_fixture()
first=replay_diagnostic_candidates(allocations,rows,[parameters(7), parameters(11)])
second=replay_diagnostic_candidates(allocations,rows,[parameters(7), parameters(11)])
assert first==second
(OUT/'software-only-numeric-replay.json').write_text(json.dumps(_plain(first),indent=2,sort_keys=True)+'\n')
with tempfile.TemporaryDirectory(prefix='replay-diagnostic-source-') as temp:
    registration,source,_,_,_=registered_replay(Path(temp))
    actual=RiskArtifactAuditor({'replay':registration},{'source':source}).audit('replay')
    assert actual.status==actual.actual_source_status=='UNKNOWN'
    assert actual.diagnostic_status=='UNAVAILABLE' and actual.comparison_status=='UNKNOWN'
    result={key:_plain(getattr(actual,key)) for key in actual.__dataclass_fields__}
    (OUT/'software-only-registered-replay.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
loaded={}
for name,module in tuple(sys.modules.items()):
    path=getattr(module,'__file__',None)
    if not path or not (name.startswith('cloud_edge_robot_arm') or name.startswith('tests.')):continue
    original=Path(path).absolute()
    relative=original.relative_to(Path.cwd()).as_posix()
    assert relative in manifest,(name,relative)
    digest=hashlib.sha256(original.read_bytes()).hexdigest()
    assert manifest[relative]==digest,(name,relative)
    loaded[relative]=digest
(OUT/'loaded-production-test-source-hashes.json').write_text(json.dumps(dict(sorted(loaded.items())),indent=2)+'\n')
(OUT/'environment.json').write_text(json.dumps(_plain(risk_replay_environment()),indent=2)+'\n')
print(json.dumps({'source_scope':'SOFTWARE_ONLY','numeric_repeat_equal':True,'numeric_observation_count':len(rows),'candidate_count':len(first['candidate_results']),'diagnostic_winner_hash':first['diagnostic_winner_hash'],'registered_actual_source_status':actual.actual_source_status,'registered_diagnostic_status':actual.diagnostic_status,'registered_comparison_status':actual.comparison_status,'registered_counts':dict(actual.counts),'loaded_production_test_paths':len(loaded)},indent=2))
