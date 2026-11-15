from pathlib import Path
import sqlite3,json,hashlib
run=Path('/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall/artifacts/research/process/20261115-v4-marker-ambiguity/offline-regression/27-case-run-01')
batch=json.loads((run/'batch-result.json').read_bytes());assert len(batch['results'])==27
rows=[]
for item in batch['results']:
 name=item['case'];p=run/name/'runtime.db';before=hashlib.sha256(p.read_bytes()).hexdigest();c=sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
 try:
  tables={t:[dict(x) for x in c.execute('SELECT * FROM '+t+(' ORDER BY sequence' if t=='simulation_job_events' else ''))] for t in ['simulation_jobs','simulation_job_attempts','simulation_job_leases','simulation_job_events']}
 finally:c.close()
 after=hashlib.sha256(p.read_bytes()).hexdigest();assert before==after
 jobs=tables['simulation_jobs'];attempts=tables['simulation_job_attempts'];leases=tables['simulation_job_leases'];events=tables['simulation_job_events'];states=[x for x in events if x['next_status']]
 result=json.loads((run/name/'result.json').read_bytes())
 assert len(jobs)==len(attempts)==len(leases)==1
 assert jobs[0]['job_id']==attempts[0]['job_id']==leases[0]['job_id']==result['job_id']
 assert jobs[0]['status']=='SUCCEEDED' and attempts[0]['result']=='SUCCEEDED' and attempts[0]['attempt']==1
 assert leases[0]['released_at'] and leases[0]['heartbeat_at']
 assert all(x['job_id']==jobs[0]['job_id'] for x in events)
 assert states[-1]['next_status']=='SUCCEEDED' and states[-1]['event_type']=='job_completed'
 assert events[-1]['event_type']=='artifact_created' and events[-1]['next_status']==''
 rows.append({'case':name,'database_path':str(p),'database_sha256_before':before,'database_sha256_after':after,'database_bytes':p.stat().st_size,'result_path':str(run/name/'result.json'),'result_sha256':hashlib.sha256((run/name/'result.json').read_bytes()).hexdigest(),'jobs':[{'job_id':x['job_id'],'status':x['status'],'attempt':x['attempt'],'lease_id':x['lease_id']} for x in jobs],'attempts':attempts,'leases':leases,'events':events,'last_state_sequence':states[-1]['sequence'],'last_event_sequence':events[-1]['sequence']})
output=Path('/tmp/bigsmall-v4-execution/astra-readonly-27-db-status-01.json')
with output.open('x') as f:json.dump({'scope':'READ_ONLY_DB_STATUS_AND_EVENTS_ONLY_NOT_FULL_FINAL_ACCEPTANCE','uri_mode':'mode=ro&immutable=1','cases_verified':len(rows),'rows':rows},f,ensure_ascii=False,indent=2)
print(json.dumps({'cases_verified':len(rows),'all_job_status_succeeded':True,'all_attempt1_succeeded_lease_released':True,'all_last_state_job_completed_sequence':sorted({x['last_state_sequence'] for x in rows}),'all_last_event_artifact_created_sequence':sorted({x['last_event_sequence'] for x in rows}),'db_bytes_unchanged':True,'scope':'DB_STATUS_ONLY_NOT_FULL_27_EVIDENCE_ACCEPTANCE'},ensure_ascii=False))
