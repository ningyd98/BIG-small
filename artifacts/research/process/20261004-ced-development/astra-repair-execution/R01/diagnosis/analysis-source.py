from pathlib import Path
from collections import Counter
from dataclasses import asdict
from datetime import datetime,timezone
import json,gzip,hashlib,csv,time
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import CompletionCriteria,PhysicalSample,evaluate_evidence
b=Path('artifacts/research/process/20261004-ced-development')
a=b/'t7b-continuous-visibility-v3/fix-round-1/attempt-1'
r=b/'astra-repair-execution/R01'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def wj(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
rows=[json.loads(line) for line in (r/'offline/offline-markers.jsonl').open()]
assert len(rows)==4807 and [x['physics_step'] for x in rows]==list(range(4807))
assert Counter(x['decode_status'] for x in rows)=={'OBSERVED':4618,'UNKNOWN':189}
unknown=[x for x in rows if x['decode_status']=='UNKNOWN']
# Decode labels only; every OBSERVED marker still has UNKNOWN stability, kept separately.
assert all(x['marker']['stability_status']=='UNKNOWN' for x in rows)
spans=[]
with gzip.open(a/'nominal-journal.jsonl.gz','rt') as f:
 for line in f:
  d=json.loads(line)
  if d['event'] in ('ACTION_BEGIN','ACTION_END'):
   spans.append(d)
print('journal_action_row_example',json.dumps(spans[0])[:2000])
lookup={}
for x in spans:
 lookup[(x['action_ordinal'],x['event'])]=x
inventory=[]
for ordinal in range(1,10):
 begin=lookup[(ordinal,'ACTION_BEGIN')];end=lookup[(ordinal,'ACTION_END')]
 start=begin['start_step'];finish=end['end_step']
 selected=[x for x in rows if start<x['physics_step']<=finish]
 counts=Counter(x['decode_status'] for x in selected)
 inventory.append({'ordinal':ordinal,'action':begin.get('action_name',begin.get('action_type',begin.get('method'))),'start_step_exclusive':start,'end_step_inclusive':finish,'sampled_frames':len(selected),'observed':counts['OBSERVED'],'unknown':counts['UNKNOWN']})
runs=[]
for row in unknown:
 s=row['physics_step']
 if not runs or s!=runs[-1]['last_step']+1:runs.append({'first_step':s,'last_step':s,'frames':1,'first_sim_time_s':row['sim_time_s'],'last_sim_time_s':row['sim_time_s']})
 else:runs[-1].update(last_step=s,frames=runs[-1]['frames']+1,last_sim_time_s=row['sim_time_s'])
truth=json.loads((a/'teacher-evidence.json').read_text())
physical=[PhysicalSample(**{k:tuple(tuple(y) if isinstance(y,list) else y for y in v) if isinstance(v,list) else v for k,v in x.items()}) for x in truth['physical_samples']]
outcome=json.loads(json.dumps(asdict(evaluate_evidence(physical,CompletionCriteria('object','target_region'),evaluation_start_step=truth['evaluation_start_step']))))
assert outcome==truth['outcome'],(outcome,truth['outcome'])
terminal=json.loads((a/'terminal.json').read_text())
assert terminal['final_step']==4806 and len(terminal['commands'])==743
assert terminal['operation_observer_failures']==[]
files=[]
for p in sorted(a.rglob('*')):
 if p.is_file():files.append({'path':str(p.relative_to(a)),'bytes':p.stat().st_size,'sha256':sha(p)})
wj(r/'raw-inventory.json',{'schema_version':'ced.local-original-inventory.v1','root':str(a),'storage':'LOCAL_WORKSPACE_ORIGINALS_NOT_ALL_PUSHED_TO_GIT','file_count':len(files),'total_bytes':sum(x['bytes'] for x in files),'all_files':files})
report={'scope':'EXCLUDED_DEVELOPMENT_SINGLE_COMPONENT_FULL_STEP_COLLECTION_AND_OFFLINE_ANALYSIS','created_at_utc':datetime.now(timezone.utc).isoformat(),'capture_session':75370,'capture_exit_code':0,'offline_session':60356,'offline_exit_code':0,'raw_inventory':str(r/'raw-inventory.json'),'raw_inventory_sha256':sha(r/'raw-inventory.json'),'capture_summary_sha256':sha(a/'summary.json'),'reader_report':str(r/'offline/offline-verification.json'),'reader_report_sha256':sha(r/'offline/offline-verification.json'),'reader_integrity':'VERIFIED','steps':4806,'frames_allocated':4807,'frames_saved':4807,'frames_failed':0,'action_count':9,'commands':743,'max_sim_sample_gap_s':0.004166666700001542,'max_sim_gap_limit_s':0.005,'capture_wall_s':915.764513714,'decoder_status_counts':dict(Counter(x['decode_status'] for x in rows)),'all_stability_statuses':'UNKNOWN','unknown_reasons':dict(Counter(x['marker']['reason'] for x in unknown)),'unknown_runs':runs,'action_status_inventory':inventory,'full_original_recipe':'COMPLETE_ORIGINAL_120_9_2','independent_physical_recompute':{'source':str(Path('src/cloud_edge_robot_arm/simulation/mujoco/episode_evaluator.py')),'source_sha256':sha('src/cloud_edge_robot_arm/simulation/mujoco/episode_evaluator.py'),'matches_saved_outcome':True,'outcome':outcome,'mode':'OFFLINE_ORIGINAL_PHYSICAL_SAMPLES_ONLY_NO_BACKEND_CONSTRUCTION'},'diagnosis':{'raw_rgb_selected_images':str(r/'diagnosis/selected-image-pins.json'),'image_pins_sha256':sha(r/'diagnosis/selected-image-pins.json'),'visually_confirmed_partial_gripper_occlusion_at_step':900,'tag_min_size_initial_px':17,'pixel_aliasing_other_unknowns':'HYPOTHESIS_NOT_YET_PROVEN','new_asset_not_accepted':True},'formal_accepted':False,'native_admission':'NOT_PROMOTED','source_authenticity':'UNKNOWN','independent_calibration_group':False,'continuous_motion':'NOT_CERTIFIED','future_stability':'UNAVAILABLE','external_utc_uncertainty':'UNAVAILABLE','calibrated_geometry_error':'UNAVAILABLE','actual_new_calls_from_this_analysis':{'physics':0,'renderer':0,'provider':0,'hardware':0,'decoder':0},'next_action':'Review all retained negative spans; new isolated marker design preview without altering originals/decoder thresholds; R2 targeted pin repair; R3 RESET prefix'}
wj(r/'report.json',report)
with (r/'unknown-frame-inventory.csv').open('w',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=['physics_step','sim_time_s','observation_id','decode_status','reason'])
 writer.writeheader()
 for x in unknown:writer.writerow({'physics_step':x['physics_step'],'sim_time_s':x['sim_time_s'],'observation_id':x['observation_id'],'decode_status':x['decode_status'],'reason':x['marker']['reason']})
print(json.dumps({'status':'ANALYSIS_COMPLETE','raw_files':len(files),'raw_bytes':sum(x['bytes'] for x in files),'unknown_runs':len(runs),'action_inventory':inventory,'independent_physical_result':outcome['status']},ensure_ascii=False))
