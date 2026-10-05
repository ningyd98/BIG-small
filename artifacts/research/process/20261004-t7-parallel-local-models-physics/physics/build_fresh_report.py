"""Freeze truthful fresh holdout results; source and literal assignment checks first."""
from __future__ import annotations
import csv,gzip,hashlib,json
from collections import Counter
from pathlib import Path
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
root=Path(__file__).resolve().parent
prereg_path=root/'fresh-preregistered-assignments.json'
prereg_sha=hashlib.sha256(prereg_path.read_bytes()).hexdigest()
assert prereg_sha=='3446acfab1c3d35869a6ff0f00cabe8c34bedb1faceaeb7ee019b31248efe4a4'
prereg=json.loads(prereg_path.read_text())
reports={}; payloads={}; metadata_corrections=[]
for label,dirname,workspace,validation_name,development in [('baseline','fresh-baseline-teacher','workspace-baseline','fresh-baseline-validation.json','baseline-t5'),('h3','fresh-h3-teacher','workspace-h3','fresh-h3-validation.json','variant-h3-t5')]:
 manifest=json.loads((root/dirname/'manifest.json').read_text()); validation=json.loads((root/validation_name).read_text()); planned=prereg['versions'][workspace]
 assert validation['valid'] and validation['accepted'] and validation['published']==42
 assert manifest['config']==prereg['config'] and manifest['asset_sha256']==planned['asset_sha256']
 assert manifest['protocol_hash']==json.loads((root/development/'manifest.json').read_text())['protocol_hash'], 'Source/runtime changed during fresh validation'
 rows=[]
 for a,p in zip(manifest['assignments'],planned['assignments'],strict=True):
  assert all(a[k]==p[k] for k in ('index','case','scene_source','seed')), 'Preregistered literal assignment changed'
  assert a['scene']['scene_parameters']==p['scene']['scene_parameters'], 'Preregistered physical parameters changed'
  expected=SceneSpec.from_parameters(p['scene']['scene_parameters'],planned['asset_sha256'],p['seed'])
  assert a['scene']==expected.model_dump(mode='json') and a['group_id']==expected.group_id and a['scene_hash']==expected.scene_hash
  if any(a[k]!=p[k] for k in ('group_id','scene_hash','scene')):
   metadata_corrections.append({'workspace':workspace,'index':a['index'],'literal_parameters_unchanged':True,'old_asset_family_hash':p['scene']['asset_family_hash'],'frozen_expected_asset_sha256':planned['asset_sha256'],'old_group_id':p['group_id'],'deterministically_derived_group_id':expected.group_id,'old_scene_hash':p['scene_hash'],'deterministically_derived_scene_hash':expected.scene_hash})
  compressed=(root/dirname/a['episode_path']).read_bytes(); assert hashlib.sha256(compressed).hexdigest()==a['sha256']; rows.append(json.loads(gzip.decompress(compressed)))
 payloads[label]=rows
 reports[label]={'dataset':str(root/dirname),'manifest_sha256':hashlib.sha256((root/dirname/'manifest.json').read_bytes()).hexdigest(),'asset_sha256':manifest['asset_sha256'],'protocol_hash':manifest['protocol_hash'],'validation':validation,'random_normal_success':sum(p['status']=='SUCCESS' for p in rows[2:]),'random_normal_count':40,'random_status_counts':dict(Counter(p['status'] for p in rows[2:])),'first_action_failure_counts':dict(Counter(next((f['action']['action_type']+':'+str(f['action']['error_code']) for f in p['frames'] if not f['action']['success']),'NONE') for p in rows))}
cases=[]
for i,(b,h) in enumerate(zip(payloads['baseline'],payloads['h3'],strict=True)):
 assert b['scene']['scene_parameters']==h['scene']['scene_parameters'] and b['case']==h['case']
 entry={'index':i,'seed':prereg['versions']['workspace-baseline']['assignments'][i]['seed'],'case':b['case'],'source':b['scene_source'],'target_y_width_m':2*b['scene']['scene_parameters']['target']['half_size'][1],'results':{}}
 for name,p in [('baseline',b),('h3',h)]:entry['results'][name]={'status':p['status'],'reason':p['reason'],'outcome':p['outcome'],'first_failed_action':next(({'action':f['action']['action_type'],'error_code':f['action']['error_code'],'details':f['action']['details']} for f in p['frames'] if not f['action']['success']),None)}
 cases.append(entry)
discordance=dict(Counter(('B_SUCCESS' if p['results']['baseline']['status']=='SUCCESS' else 'B_FAIL')+'_'+('H3_SUCCESS' if p['results']['h3']['status']=='SUCCESS' else 'H3_FAIL') for p in cases[2:]))
report={'scope':'EXPLORATORY_FRESH_INDEPENDENT_OFFLINE_TEACHER_VALIDATION','formal_g1_promoted':False,'eligible_for_formal_g1':False,'not_online_vlm_closed_loop':True,'source_tuned_after_fresh_started':False,'api_calls':0,'model_calls':0,'preregistered_assignments_sha256':prereg_sha,'same_literal_parameters_seeds_and_case_order':True,'assigned_each':42,'random_normal_each':40,'fixed_controls_each':2,'random_seeds':prereg['random_seeds'],'criteria_unchanged':True,'versions':reports,'random_paired_discordance':discordance,'cases':cases,'preregistered_asset_identity_metadata_exact':not bool(metadata_corrections),'metadata_correction_count':len(metadata_corrections),'protocol_deviations':[{'type':'PREREGISTERED_DERIVED_ASSET_IDENTITY_METADATA_ERROR','affected_entries':40,'original_file_retained':True,'literal_physical_assignments_unchanged':True}],'metadata_correction_note':'Original preregistration incorrectly used baseline cwd asset hash inside sample_scene for 40 H3 random entries. Original file/hash retained. All original literal parameters, seeds, cases, order and top-level H3 asset SHA are exact; derived asset-bound identities are reconstructed deterministically from those frozen values and independently match execution.','limitations':'Same restricted upright-box reference-asset family and target ranges as T5; this validates physical teacher generalization across fresh seeds, not online localization, VLM planning, hardware or other scene families. New H3 asset remains rejected by the old online calibration guard.'}
(root/'fresh-preregistration-metadata-audit.json').write_text(json.dumps({'original_preregistration_sha256':prereg_sha,'original_file_retained_unchanged':True,'literal_parameters_cases_seeds_order_unchanged':True,'reason':'Preregistration helper called _assignments in baseline cwd; sample_scene independently read its model_path, ignoring caller asset_hash for random cases.','corrections':metadata_corrections},indent=2)+'\n')
(root/'fresh-paired-teacher-report.json').write_text(json.dumps(report,indent=2)+'\n')
with (root/'fresh-paired-teacher-cases.csv').open('w') as f:
 w=csv.writer(f); w.writerow(['index','seed','case','source','y_width_m','baseline_status','h3_status','baseline_reason','h3_reason','baseline_lift_m','h3_lift_m','baseline_hold_s','h3_hold_s'])
 for c in cases:w.writerow([c['index'],c['seed'],c['case'],c['source'],c['target_y_width_m'],c['results']['baseline']['status'],c['results']['h3']['status'],c['results']['baseline']['reason'],c['results']['h3']['reason'],c['results']['baseline']['outcome']['measured_lift_m'],c['results']['h3']['outcome']['measured_lift_m'],c['results']['baseline']['outcome']['hold_s'],c['results']['h3']['outcome']['hold_s']])
print(json.dumps({'baseline':reports['baseline']['validation']['status_counts'],'h3':reports['h3']['validation']['status_counts'],'random_paired_discordance':discordance},indent=2))
