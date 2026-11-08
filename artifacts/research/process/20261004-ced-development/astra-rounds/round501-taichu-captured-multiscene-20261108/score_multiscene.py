"""Offline strict JSON / registered pixel masks; no v1-to-v2 rebind or arm actions."""
import hashlib,json,statistics,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[5];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT))
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.capture import CapturedFrame
from cloud_edge_robot_arm.vision.messages import model_to_observation_pixel
from cloud_edge_robot_arm.vision.planner import VisualDecision
from scripts.probe_rgbd_model import _pixel_hit

def main():
 run=json.loads((HERE/'run-stage-b.json').read_text());sources={r['case_id']:r for r in json.loads((HERE/'diagnostic/frozen-message-inputs.json').read_text())};results=[]
 for attempt in run['actual_requests']:
  raw=Path(attempt['raw_directory']);text=(raw/'raw-response.txt').read_text();assert hashlib.sha256(text.encode()).hexdigest()==attempt['raw_response_sha256'];case=sources[attempt['case_id']];capture=(ROOT/case['rgb_path']).parent
  row={**attempt,'kind':'positive' if attempt['case_id'].startswith('positive') else 'negative_absent','strict_json':False,'target_hit':False,'destination_hit':False,'target_scorable':False,'destination_scorable':False,'refusal':None,'confidence_zero':None,'action_suggestion_nonempty':None}
  try:decision=VisualDecision.model_validate_json(text,strict=True)
  except Exception as error:row['schema_error']=str(error)
  else:
   row.update(strict_json=True,decision=decision.model_dump(mode='json'),refusal=decision.target_pixel is None and decision.destination_pixel is None and not decision.skills,confidence_zero=decision.reported_confidence==0,action_suggestion_nonempty=bool(decision.skills))
   obs=RGBDObservation.model_validate_json((capture/'full-observation.json').read_text());offline=json.loads((capture/'observation.json').read_text());frame=CapturedFrame(observation=obs,instance_ids=tuple(x[0] for x in struct.iter_unpack('<i',(capture/'instance_geom_ids.i32').read_bytes())),instance_labels={int(k):v for k,v in offline['instance_labels'].items()},physics_state_hash=offline['physics_state_hash'],pass_state_hashes=tuple(offline['pass_state_hashes']))
   for kind,label in [('target','object_geom'),('destination','target_region_geom')]:
    value=getattr(decision,kind+'_pixel');pixel=None
    if value is not None and all(0<=v<=1000 for v in value):pixel=model_to_observation_pixel(value,obs,image_size=(320,240),coordinate_system='normalized_1000')
    hit,details=_pixel_hit(frame,pixel,label);row[kind+'_hit']=hit;row[kind+'_scorable']=pixel is not None;row[kind+'_offline_check']=details
  row['both_hits']=row['target_hit'] and row['destination_hit'];results.append(row)
 pos=[r for r in results if r['kind']=='positive'];neg=[r for r in results if r['kind']=='negative_absent']
 summary={'run_status':run['status'],'planned':16,'completed':len(results),'strict_json':sum(r['strict_json'] for r in results),'positive':{'planned':12,'completed':len(pos),'target_scorable':sum(r['target_scorable'] for r in pos),'destination_scorable':sum(r['destination_scorable'] for r in pos),'target_hits':sum(r['target_hit'] for r in pos),'destination_hits':sum(r['destination_hit'] for r in pos),'both_hits':sum(r['both_hits'] for r in pos)},'absent':{'planned':4,'completed':len(neg),'refusals':sum(r['refusal'] is True for r in neg),'nonempty_action_suggestions':sum(r['action_suggestion_nonempty'] is True for r in neg),'confidence_zero':sum(r['confidence_zero'] is True for r in neg)},'median_generation_s':statistics.median(r['generation_s'] for r in results) if results else None,'results':results,'new_model_loads':0,'actual_generations':run['generation_calls'],'source_profile':'mujoco_upright_box_v1','dataset':'PREVIOUSLY_SEEN_DEV','3D_error':'NOT_MEASURED','P90_3D_error':'NOT_MEASURED','physical_actions':0,'formal_acceptance':'NOT_PERFORMED'}
 with (HERE/'score-stage-b.json').open('x') as f:json.dump(summary,f,ensure_ascii=False,indent=2);f.write('\n')
 print(json.dumps({k:v for k,v in summary.items() if k!='results'},ensure_ascii=False))
if __name__=='__main__':main()
