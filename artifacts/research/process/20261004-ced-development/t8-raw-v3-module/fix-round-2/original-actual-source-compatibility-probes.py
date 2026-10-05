"""Frozen software sources reproducing real backend/camera consistency rules."""
from dataclasses import replace
from datetime import timedelta
import json
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests.test_raw_episode_v3 import api,fixture

def view(envelope,records):
 v=api().validate_raw_episode_v3(envelope,records)
 return dict(status=v.status,reasons=list(v.reasons),counts=dict(v.counts),scope=v.scope)
envelope,records=fixture();out={'baseline':view(envelope,records)}
command=records.commands[0]
command=replace(command,command_payload={**dict(command.command_payload),'target_positions_rad':[1.0]*7,'applied_target_positions_rad':[1.0]*7})
last=records.physics[-1]
control={**dict(last.control_payload),'applied_joint_targets_rad':[1.0]*7,'control_rad':[0.1]*7}
clipped=replace(records,commands=(command,),physics=(*records.physics[:-1],replace(last,control_payload=control)))
out['real_backend_clipped_control']=view(envelope,clipped)
not_clipped=replace(clipped,physics=(*records.physics[:-1],replace(last,control_payload={**control,'control_rad':[1.0]*7})))
out['wrong_unclipped_formula_control']=view(envelope,not_clipped)
frame=records.frames[0];data=dict(frame.observation_payload);data['captured_at']=(RGBDObservation.model_validate(data).captured_at+timedelta(microseconds=10)).isoformat();data['checksum_sha256']='';obs=RGBDObservation.model_validate(data)
new_frame=replace(frame,observation_payload=obs.model_dump(mode='json'))
new_joins=tuple(replace(row,checksum_sha256=obs.checksum_sha256) if row.acquisition_id==frame.acquisition_id else row for row in records.joins)
bracket=replace(records,frames=(new_frame,*records.frames[1:]),joins=new_joins)
out['real_camera_time_inside_acquisition_bracket']=view(envelope,bracket)
print(json.dumps(out,indent=2))
