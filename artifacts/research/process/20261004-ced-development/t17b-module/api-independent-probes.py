from pathlib import Path
from hashlib import sha256
import json, tempfile, shutil
from unittest.mock import patch
from pytest import MonkeyPatch
from tests.test_research_results_api import prepared_sources, browser, api
from cloud_edge_robot_arm.datasets.rgbd.models import content_digest

temporary=Path(tempfile.mkdtemp(prefix='t17-api-review-'))
class Factory:
    def mktemp(self,name):
        root=temporary/name
        root.mkdir()
        return root

root,protocol_hash=prepared_sources.__wrapped__(Factory())
with MonkeyPatch.context() as monkeypatch:
    client=browser(monkeypatch,root)
    url='/api/v1/research/runs/run-1/evidence'
    initial=client.get(url)
    assert initial.status_code==200
    value=initial.json()
    assert value['assigned_denominator']==4200 and len(value['failures'])==4200
    assert value['actual_research_status']=='NOT_RUN' and not value['formal_accepted'] and value['physical_success']==0
    assert client.get('/api/v1/research/runs/run-1/export').json()==value
    print('Complete 4200 failures / 600 paired groups; export equals evidence; actual NOT_RUN',flush=True)
    # Every source byte identity participates in the existing cached fingerprint.
    paths={'protocol':root/'run-1/protocol/protocol.json','assignments':root/'run-1/runs/assignments.json','records':root/'run-1/runs/records.jsonl','pools':root/'run-1/runs/pools.json','report':root/'run-1/analysis/report.json','metrics':root/'run-1/analysis/metrics.json','goals':root/'run-1/analysis/goal_verdicts.json'}
    for name,path in paths.items():
        original=path.read_bytes()
        path.write_bytes(b'null\n')
        try:
            response=client.get(url)
            assert response.status_code==409,(name,response.status_code)
            print('Cached '+name+' invalidation:409',flush=True)
        finally:path.write_bytes(original)
    # Config changes and missing sources cannot reuse the previous complete view.
    original_registration=client.app.state.research_runs_registry['run-1']
    client.app.state.research_runs_registry['run-1']=api().ResearchRunRegistration(runs_path='missing/runs',protocol_path='missing/protocol',analysis_path='missing/analysis')
    missing=client.get(url)
    assert missing.status_code==200 and missing.json()['assigned_denominator'] is None
    assert missing.json()['source_missing'] and missing.json()['actual_research_status']=='NOT_RUN'
    client.app.state.research_runs_registry['run-1']=original_registration
    assert client.get(url).json()==value
    print('Changed registration returns explicit missing source; no hidden cached completion',flush=True)
    # Fully rehashing omitted failed assignments is insufficient for coverage.
    manifest_path=paths['assignments']; records_path=paths['records']; report_path=paths['report']
    original_manifest=manifest_path.read_bytes(); original_records=records_path.read_bytes(); original_report=report_path.read_bytes()
    manifest=json.loads(original_manifest); manifest.pop('content_hash'); manifest['assignments'].pop()
    manifest['content_hash']=content_digest(manifest)
    manifest_path.write_text(json.dumps(manifest))
    records_path.write_bytes(b'\n'.join(original_records.splitlines()[:-1])+b'\n')
    report=json.loads(original_report)
    report['source_hashes']['assignments']=sha256(manifest_path.read_bytes()).hexdigest()
    report['source_hashes']['records']=sha256(records_path.read_bytes()).hexdigest()
    report_path.write_text(json.dumps(report))
    assert client.get(url).status_code==409
    print('Rehashed omission of original failed assignment:409',flush=True)
    manifest_path.write_bytes(original_manifest); records_path.write_bytes(original_records); report_path.write_bytes(original_report)
    # A producer's coherent hash list must not convert malformed null source into 500.
    manifest_path.write_text('null\n')
    report=json.loads(original_report); report['source_hashes']['assignments']=sha256(manifest_path.read_bytes()).hexdigest()
    report_path.write_text(json.dumps(report))
    try:
        response=client.get(url)
        print('Coherently rehashed null assignment manifest response:'+str(response.status_code),flush=True)
    except Exception as error:
        print('Coherently rehashed null assignment manifest UNCAUGHT:'+type(error).__name__+':'+str(error),flush=True)
    manifest_path.write_bytes(original_manifest); report_path.write_bytes(original_report)
print('Temporary independent fixture:',temporary,flush=True)
