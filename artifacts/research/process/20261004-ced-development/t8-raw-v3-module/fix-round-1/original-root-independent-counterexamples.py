"""Pure hand-built SOFTWARE_ONLY records; zero simulator construction or sampling."""
import json
from dataclasses import replace
from tests.test_raw_episode_v3 import api, fixture, hash_payload, renumber

m = api()
out = {}
def evaluate(name, env, records):
    v = m.validate_raw_episode_v3(env, records)
    out[name] = dict(status=v.status, reasons=list(v.reasons), counts=dict(v.counts), scope=v.scope, continuous_motion=v.continuous_motion)
    return v

e, r = fixture()
assert evaluate('qualified_baseline', e, r).status == 'COMPLETE'
# Add a TERMINAL link to the exact preserved BEFORE frame at step120,
# while the episode terminal snapshot and action return are step121.
before = r.joins[0]
terminal_before = replace(before, relation='TERMINAL')
evaluate('terminal_relation_points_to_pre_action_frame', e, renumber(replace(r, joins=(*r.joins, terminal_before))))
terminal_after = replace(r.joins[1], relation='TERMINAL')
evaluate('terminal_negative_control_current_terminal_frame', e, renumber(replace(r, joins=(*r.joins, terminal_after))))
# Carry estop=True consistently through every original state and previous hash.
# The ordinary accepted joint target still reports after_emergency_stop=False.
# This does not fabricate a runtime transition: it exposes disagreement among inputs.
def stopped(raw):
    return {**dict(raw), 'estop_engaged': True}
physics = []
previous = stopped(e.reset_state_payload)
for row in r.physics:
    changed = stopped(row.post_state_payload)
    physics.append(replace(row, previous_state_hash=hash_payload(previous), post_state_payload=changed))
    previous = changed
frames = tuple(replace(f, joined_physics_observation_hash=hash_payload(stopped(r.physics[next(i for i,p in enumerate(r.physics) if p.physics_step == next(iv.start_step for iv in r.intervals if iv.interval_id == f.interval_id))].post_state_payload))) for f in r.frames)
e2 = replace(e, reset_state_payload=stopped(e.reset_state_payload), terminal_state_payload=stopped(e.terminal_state_payload))
r2 = replace(r, physics=tuple(physics), frames=frames)
evaluate('accepted_ordinary_command_disagrees_with_recorded_estop', e2, r2)
correct_flag = replace(r2.commands[0], command_payload={**dict(r2.commands[0].command_payload), 'after_emergency_stop': True})
evaluate('estop_flag_negative_control', e2, replace(r2, commands=(correct_flag,)))
# Concrete stop command precedes ordinary command in the SAME physics step:
# physical state120 can legitimately predate the latch transition, so check
# command-order replay instead of requiring equality to an older state sample.
from datetime import timedelta
from tests.test_raw_episode_v3 import NOW
base_interval = next(iv for iv in r.intervals if iv.interval_id == 'command')
def pair(ns):
    return m.ClockPairV3('clock-1', e.clock_descriptor.digest(), ns+1, ns, NOW+timedelta(microseconds=ns//1000), ns+100)
def stop_command(seq, name, kind, t, extras):
    iv = replace(base_interval, interval_id=name, start=pair(t), end=pair(t+1000))
    payload = dict(type=kind, accepted=True, reason='', after_emergency_stop=False,
        sim_time_s=.5, episode_id='episode', physics_step=120, command_seq=seq, **extras)
    cmd = replace(r.commands[0], command_seq=seq, command_payload=payload, interval_id=name)
    return iv, cmd
hiv, hc = stop_command(1, 'hold-before-stop', 'hold_current_joints', 210020000,
    dict(target_positions_rad=[0]*7, applied_target_positions_rad=[0]*7))
siv, sc = stop_command(2, 'accepted-stop', 'emergency_stop', 210040000, {})
ordinary = replace(r.commands[0], command_seq=3, command_payload={**dict(r.commands[0].command_payload), 'command_seq':3})
last_physics = replace(r.physics[-1], post_state_payload=stopped(r.physics[-1].post_state_payload))
last_frame = replace(r.frames[-1], joined_physics_observation_hash=hash_payload(dict(last_physics.post_state_payload)))
e3 = replace(e, terminal_command_seq=3, terminal_state_payload=last_physics.post_state_payload)
r3 = renumber(replace(r, intervals=(*r.intervals, hiv, siv), commands=(hc, sc, ordinary),
    actions=(replace(r.actions[0], command_seq_end=4),), physics=(*r.physics[:-1],last_physics), frames=(r.frames[0],last_frame)))
evaluate('ordered_emergency_stop_then_accepted_ordinary_false_flag', e3, r3)
print(json.dumps(out, indent=2, sort_keys=True))
