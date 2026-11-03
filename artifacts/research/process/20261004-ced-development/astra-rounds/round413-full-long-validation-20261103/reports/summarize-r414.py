"""Offline-only R413 outcome reconciliation; raw files are never rewritten."""
from collections import Counter, defaultdict
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROUND=Path(__file__).resolve().parents[1]
ROOT=Path('/home/ningyd/文档/ChatGPT/BIGsmall')
FINAL='--final' in sys.argv
OUT=ROUND/'reports' if FINAL else ROUND/'reports/live'/datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
OUT.mkdir(parents=True,exist_ok=True)

def save(name,value):
 with (OUT/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

def rel(path):return os.path.relpath(path,ROUND)

def read_json(path):
 try:return json.loads(path.read_text())
 except (OSError,json.JSONDecodeError):return None

def junit(path):
 if not path.exists():return {'exists':False,'cases':[],'error':None}
 try:
  root=ET.parse(path).getroot()
  rows=[]
  for case in root.iter('testcase'):
   state='FAILED' if case.find('failure') is not None else 'ERROR' if case.find('error') is not None else 'SKIPPED' if case.find('skipped') is not None else 'PASSED'
   rows.append({'classname':case.get('classname'),'name':case.get('name'),'status':state,
    'duration_s':float(case.get('time')) if case.get('time') is not None else None,
    'duration_available':case.get('time') is not None})
  return {'exists':True,'cases':rows,'error':None,'counts':dict(Counter(r['status'] for r in rows))}
 except (ET.ParseError,ValueError,OSError) as error:return {'exists':True,'cases':[],'error':str(error)}

specs=[read_json(p) for p in sorted((ROUND/'specs').glob('*.json'))]
specs=[s for s in specs if s]
stages=[];attempts=defaultdict(list);integrity=[]
for spec in specs:
 d=Path(spec['directory']);result=read_json(d/'result.json')
 raw=[];parse_errors=[]
 if (d/'pytest-events.jsonl').exists():
  for i,line in enumerate((d/'pytest-events.jsonl').read_text().splitlines(),1):
   try:raw.append(json.loads(line))
   except json.JSONDecodeError as error:parse_errors.append({'line':i,'error':str(error)})
 xml=junit(d/'junit.xml')
 status='PENDING' if not FINAL else 'NOT_RUN'
 if result:
  if result['state']=='FINISHED':
   if result.get('returncode')==0:status='PASSED'
   elif result.get('returncode') in [1,2,3,4,5]:status='FAILED'
   else:status='PROCESS_FAILED'
  else:status=result['state']
  if result.get('source_drift') or result.get('remaining_live') or result.get('errors'):
   status='INFRASTRUCTURE_ERROR'
 if not result and (d/'invocation.json').exists():status='INCOMPLETE' if FINAL else 'RUNNING'
 row={'id':spec['id'],'status':status,'expected_nodes':len(spec.get('nodes',[])),
  'timeout_s':spec['timeout_s'],'result':result,'result_path':rel(d/'result.json'),
  'junit':xml,'event_parse_errors':parse_errors,'parent_stage':spec.get('parent_stage')}
 stages.append(row)
 expected=set(spec.get('nodes',[]))
 for ev in raw:
  if ev.get('nodeid') and ev['nodeid'] not in expected:
   integrity.append({'stage_id':spec['id'],'issue':'UNASSIGNED_NODE_EVENT','nodeid':ev['nodeid']})
 collection=[ev for ev in raw if ev['event']=='collection_finished']
 if collection and set(collection[-1]['nodeids'])!=expected:
  integrity.append({'stage_id':spec['id'],'issue':'COLLECTION_ASSIGNMENT_MISMATCH'})
 if parse_errors:integrity.append({'stage_id':spec['id'],'issue':'EVENT_PARSE_ERRORS','details':parse_errors})
 for node in expected:
  evs=[ev for ev in raw if ev.get('nodeid')==node]
  starts=[ev for ev in evs if ev['event']=='started']
  reports=[ev for ev in evs if ev['event']=='report']
  # Assignment in an interrupted parent is not a second attempt when a tail later starts.
  attempts[node].append({'stage_id':spec['id'],'started_count':len(starts),'reports':reports,
   'stage_state':status,'source_ok':bool(result and not result.get('source_drift')),
   'launched':bool(result and result.get('launched')),'event_parse_error_count':len(parse_errors),'events_present':bool(raw),
   'cleanup_ok':bool(result and result.get('reaped') and not result.get('remaining_live') and not result.get('errors')),
   'junit_confirmed':any(c['classname']=='.'.join([node.split('::')[0][:-3].replace('/','.'),*node.split('::')[1:-1]]) and c['name']==node.split('::')[-1] for c in xml['cases']),
   'junit_statuses':[c['status'] for c in xml['cases'] if c['classname']=='.'.join([node.split('::')[0][:-3].replace('/','.'),*node.split('::')[1:-1]]) and c['name']==node.split('::')[-1]],
   'evidence':rel(d/'pytest-events.jsonl'),'result':rel(d/'result.json')})

ledger=[];failures=[]
collection=read_json(ROUND/'preflight/collection.json')['nodes']
excluded=set(read_json(ROUND/'assignment.json')['external_not_run'])
for item in collection:
 node=item['nodeid'];assigned=attempts[node]
 begun=[a for a in assigned if a['started_count']]
 starts=sum(a['started_count'] for a in assigned)
 status='NOT_RUN_EXTERNAL_DATA' if node in excluded else 'NOT_RUN' if FINAL else 'PENDING'
 if node not in excluded and not starts and any(a['event_parse_error_count'] or (a['launched'] and not a['events_present']) for a in assigned):status='INDETERMINATE_EVENTS'
 phases={};durations={};details=[]
 if starts>1:
  status='DUPLICATE_START_ERROR';integrity.append({'nodeid':node,'issue':'MORE_THAN_ONE_START','starts':starts})
 elif starts==1:
  active=begun[0]
  for report in active['reports']:
   when=report['when']
   if when in phases:integrity.append({'nodeid':node,'issue':'DUPLICATE_PHASE','phase':when})
   phases[when]=report['outcome'];durations[when]=report['duration_s']
   if report.get('longrepr'):details.append({'when':when,'outcome':report['outcome'],'longrepr':report['longrepr']})
  if phases.get('setup')=='failed' or phases.get('teardown')=='failed':status='ERROR'
  elif phases.get('call')=='failed':status='FAILED'
  elif phases.get('setup')=='skipped' or phases.get('call')=='skipped':status='SKIPPED'
  elif all(phases.get(x)=='passed' for x in ['setup','call','teardown']):status='PASSED'
  else:status='INCOMPLETE' if FINAL or active['stage_state']!='RUNNING' else 'RUNNING'
  if status=='PASSED' and (not active['source_ok'] or not active['cleanup_ok']):status='PASSED_PENDING_STAGE_INTEGRITY'
  if active['junit_confirmed'] and status in ['PASSED','FAILED','ERROR','SKIPPED'] and status not in active['junit_statuses']:
   integrity.append({'nodeid':node,'issue':'JUNIT_EVENT_OUTCOME_MISMATCH','events_status':status,'junit_statuses':active['junit_statuses']})
 row={'nodeid':node,'status':status,'markers':item['markers'],'started_count':starts,'phases':phases,
  'phase_durations_s':durations,'call_duration_s':durations.get('call'),
  'junit_confirmed':any(a['junit_confirmed'] for a in begun),'assignments':[
   {k:v for k,v in a.items() if k not in ['reports']} for a in assigned]}
 ledger.append(row)
 if details:failures.append({'nodeid':node,'status':status,'details':details,'stage_ids':[a['stage_id'] for a in begun]})
counts=dict(Counter(n['status'] for n in ledger))
assert len(ledger)==4753 and sum(counts.values())==4753
python_stages=[s for s in stages if s['expected_nodes']]
nonpython=[s for s in stages if not s['expected_nodes']]
summary={'schema':'r413.full-validation-summary.v1','generated_utc':datetime.now(UTC).isoformat(),'final':FINAL,
 'tested_commit':read_json(ROUND/'preflight/prepared.json')['source_commit'],
 'official_source_tree_hash':read_json(ROUND/'preflight/official-source-hash.json')['source_tree_hash'],
 'collected':4753,'software_assigned':4751,'external_data_not_run':2,
 'python_node_counts':counts,'python_started':sum(n['started_count']>0 for n in ledger),
 'junit_confirmed_python_nodes':sum(n['junit_confirmed'] for n in ledger),
 'python_stage_counts':dict(Counter(s['status'] for s in python_stages)),
 'other_stage_counts':dict(Counter(s['status'] for s in nonpython)),
 'integrity_issues':integrity,'formal_accepted':False,
 'full_software_workflow_pass':bool(FINAL and counts.get('PASSED',0)==4751 and not integrity and len(nonpython)==22 and all(s['status']=='PASSED' for s in nonpython))}
save('coverage-ledger.json',{'counts':counts,'nodes':ledger,'integrity_issues':integrity})
save('stage-summary.json',stages)
save('failures.json',failures)
save('summary.json',summary)
print(json.dumps(summary,ensure_ascii=False,indent=2))
print(str(OUT))
