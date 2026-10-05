from dataclasses import replace
from tests.test_raw_episode_v3 import fixture,api,clock_interval,hash_payload,renumber
import json
e,r=fixture(); previous=dict(e.reset_state_payload); physics=[]
for p in r.physics:
 post={**dict(p.post_state_payload),'estop_engaged':p.physics_step>=120}
 physics.append(replace(p,previous_state_hash=hash_payload(previous),post_state_payload=post));previous=post
changed=[]
for i in r.intervals:
 if i.interval_id=='settle': i=clock_interval(i,i.interval_id,i.kind,0,120,0,210200000)
 elif i.interval_id=='control-120': i=clock_interval(i,i.interval_id,i.kind,119,119,210120000,210121000)
 elif i.interval_id=='step-120': i=clock_interval(i,i.interval_id,i.kind,119,120,210130000,210190000)
 changed.append(i)
by_step={p.physics_step:p.post_state_payload for p in physics}; indices={i.interval_id:i.start_step for i in r.intervals}
frames=tuple(replace(f,joined_physics_observation_hash=hash_payload(dict(by_step[indices[f.interval_id]]))) for f in r.frames)
v=api().validate_raw_episode_v3(replace(e,terminal_state_payload=previous),renumber(replace(r,intervals=tuple(changed),physics=tuple(physics),frames=frames)))
print(json.dumps({'status':v.status,'reasons':v.reasons,'command_step':120,'command_start_ns':210100000,'current_step120_sample_available_ns':210190100,'counts':dict(v.counts)}))
