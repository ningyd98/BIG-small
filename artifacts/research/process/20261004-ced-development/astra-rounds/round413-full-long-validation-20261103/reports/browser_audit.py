"""Offline browser identity/outcome comparison; missing results never pass."""
from collections import Counter,defaultdict
from datetime import UTC,datetime
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

R=Path(__file__).resolve().parents[1]
B=R.parent
old=json.loads((B/'round408-browser-workflow-retest-20261103/old-case-map.json').read_text())
allcases=[];suites=[];issues=[]
for name,expected in [('browser-default',40),('browser-research',3)]:
 d=R/'implementation'/name
 result=json.loads((d/'result.json').read_text()) if (d/'result.json').exists() else None
 cases=[]
 if (d/'junit.xml').exists():
  try:
   for case in ET.parse(d/'junit.xml').iter('testcase'):
    status='ERROR' if case.find('error') is not None else 'FAILED' if case.find('failure') is not None else 'SKIPPED' if case.find('skipped') is not None else 'PASSED'
    duration=None;raw=case.get('time')
    if raw is not None:
     try:
      duration=float(raw)
      if not math.isfinite(duration) or duration<0:raise ValueError('invalid duration')
     except ValueError:
      issues.append({'suite':name,'issue':'INVALID_DURATION','name':case.get('name'),'raw':raw});duration=None
    cases.append({'suite':name,'classname':case.get('classname'),'name':case.get('name'),'status':status,
     'duration_s':duration,'duration_available':duration is not None,'evidence':str((d/'junit.xml').relative_to(R))})
  except (ET.ParseError,OSError) as error:issues.append({'suite':name,'issue':'JUNIT_PARSE_ERROR','error':str(error)})
 if len(cases)!=expected:issues.append({'suite':name,'issue':'CASE_COUNT_MISMATCH','expected':expected,'actual':len(cases)})
 suites.append({'suite':name,'expected':expected,'actual':len(cases),'result':result})
 allcases.extend(cases)
index=defaultdict(list)
for case in allcases:index[(case['classname'],case['name'])].append(case)
comparison=[]
for before in old['old19']:
 matches=index[(before['classname'],before['name'])]
 comparison.append({**before,'current_state':matches[0]['status'] if len(matches)==1 else 'NOT_UNIQUELY_OBSERVED',
  'current_duration_s':matches[0]['duration_s'] if len(matches)==1 else None,'evidence':matches[0]['evidence'] if len(matches)==1 else None})
research=R/'implementation/browser-research/observed-summary.json'
observed=json.loads(research.read_text()) if research.exists() else None
research_boundary=bool(observed and observed.get('scope')=='SOFTWARE_ONLY' and observed.get('groups')==600 and observed.get('assigned')==4200 and observed.get('blocked')==4200 and observed.get('actual_research_status')=='NOT_RUN' and observed.get('formal_accepted') is False and observed.get('export_matches_page') is True)
if not research_boundary:issues.append({'issue':'RESEARCH_BOUNDARY_NOT_CONFIRMED','observed':observed})
counts=dict(Counter(c['status'] for c in allcases))
cleanup=bool(len(suites)==2 and all(s['result'] and s['result'].get('reaped') and not s['result'].get('source_drift') and not s['result'].get('remaining_live') and not s['result'].get('errors') and len(s['result'].get('ports_after',[]))==2 and all(p['available'] for p in s['result']['ports_after']) for s in suites))
output={'schema':'r413.browser-audit.v1','generated_utc':datetime.now(UTC).isoformat(),'counts':counts,'suites':suites,
 'all_cases':allcases,'old19':comparison,'old19_passed':sum(c['current_state']=='PASSED' for c in comparison),
 'expected_original_skip':old['original_skip'],'unexpected_skips':[c for c in allcases if c['status']=='SKIPPED' and c['name']!=old['original_skip']],
 'research':observed,'research_boundary_confirmed':research_boundary,'cleanup_confirmed':cleanup,'issues':issues,
 'formal_accepted':False,'scope':'Current source browser assertions and MuJoCo/EGL image simulation; no physical robot or actual research acceptance.'}
with (R/'reports/browser-audit.json').open('x') as f:json.dump(output,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'counts':counts,'old19_passed':output['old19_passed'],'issues':issues,'cleanup_confirmed':cleanup},ensure_ascii=False))
