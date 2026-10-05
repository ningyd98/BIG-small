"""Read only preserved physical evidence and freeze a paired development summary."""
from __future__ import annotations
import csv,gzip,hashlib,json
from collections import Counter
from pathlib import Path
root=Path(__file__).resolve().parent
versions=('baseline-t5','variant-h1-t5','variant-h1-h2-t5','variant-h3-t5')
reports={}; payloads={}
for name in versions:
 manifest=json.loads((root/name/'manifest.json').read_text())
 validation_path=root/({'baseline-t5':'baseline-validation.json','variant-h1-t5':'variant-h1-validation.json','variant-h1-h2-t5':'variant-h1-h2-validation.json','variant-h3-t5':'variant-h3-validation.json'}[name])
 validation=json.loads(validation_path.read_text())
 rows=[]
 for a in manifest['assignments']:
  p=json.loads(gzip.decompress((root/name/a['episode_path']).read_bytes()))
  rows.append(p)
  assert hashlib.sha256((root/name/a['episode_path']).read_bytes()).hexdigest()==a['sha256']
 payloads[name]=rows
 reports[name]={'manifest_path':str((root/name/'manifest.json').resolve()),'manifest_sha256':hashlib.sha256((root/name/'manifest.json').read_bytes()).hexdigest(),'asset_sha256':manifest['asset_sha256'],'protocol_hash':manifest['protocol_hash'],'source_sha256':manifest['protocol']['source_sha256'],'validation':validation,'criteria':manifest['protocol']['criteria'],'first_action_failure_counts':dict(Counter(next((f['action']['action_type']+':'+str(f['action']['error_code']) for f in p['frames'] if not f['action']['success']),'NONE') for p in rows))}
base=json.loads((root/'baseline-t5/manifest.json').read_text())
criteria=reports['baseline-t5']['criteria']
case_rows=[]
for i in range(20):
 a=base['assignments'][i]
 row={'index':i,'case':a['case'],'seed':a['seed'],'scene_parameters_sha256':hashlib.sha256(json.dumps(a['scene']['scene_parameters'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),'target_y_width_m':2*a['scene']['scene_parameters']['target']['half_size'][1],'mass_kg':a['scene']['scene_parameters']['target']['mass_kg'],'same_parameters_seed_case_all_versions':True,'results':{}}
 for name in versions:
  p=payloads[name][i]; m=json.loads((root/name/'manifest.json').read_text()); v=m['assignments'][i]
  assert (v['index'],v['case'],v['seed'],v['scene_source'],v['scene']['scene_parameters'])==(a['index'],a['case'],a['seed'],a['scene_source'],a['scene']['scene_parameters'])
  assert reports[name]['criteria']==criteria
  row['results'][name]={'status':p['status'],'failure_reason':p['reason'],'outcome':p['outcome'],'first_failed_action':next(({'action':f['action']['action_type'],'error_code':f['action']['error_code']} for f in p['frames'] if not f['action']['success']),None),'episode_sha256':v['sha256']}
 case_rows.append(row)
report={'scope':'OFFLINE_GROUND_TRUTH_TEACHER_DEVELOPMENT_CASES_ONLY','holdout_used':False,'online_vlm_experiment':False,'cases':20,'same_parameters_seed_case_all_versions':True,'unchanged_physical_criteria':True,'note':'Asset-bound group_id and scene_hash necessarily change with new robot SHA; literal scene parameters, seeds, case allocation and control targets are exactly paired. H1/H2 are diagnostic rejected hypotheses, H3 is a review candidate only.','versions':reports,'paired_cases':case_rows}
(root/'paired-development-report.json').write_text(json.dumps(report,indent=2)+'\n')
with (root/'paired-development-cases.csv').open('w') as f:
 writer=csv.writer(f); writer.writerow(['index','case','seed','y_width_m','mass_kg',*[name+'_status' for name in versions],*[name+'_lift_m' for name in versions],*[name+'_hold_s' for name in versions]])
 for row in case_rows: writer.writerow([row['index'],row['case'],row['seed'],row['target_y_width_m'],row['mass_kg'],*[row['results'][name]['status'] for name in versions],*[row['results'][name]['outcome']['measured_lift_m'] for name in versions],*[row['results'][name]['outcome']['hold_s'] for name in versions]])
print(json.dumps({name:reports[name]['validation']['status_counts'] for name in versions},indent=2))
