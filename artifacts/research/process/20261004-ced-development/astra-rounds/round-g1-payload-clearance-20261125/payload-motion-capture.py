"""Run the preregistered held-out mechanical trajectories with the frozen native rig."""
import importlib.util
import json
import sys
from pathlib import Path

here=Path(__file__).resolve().parent
ob=here.parent/'round-g1-skill-handoff-20261125'/'handoff-physics-native.py'
spec=importlib.util.spec_from_file_location('payload_native',ob)
native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
cfg=json.loads((here/'payload-motion-preregistration.json').read_bytes())
case=sys.argv[1]
if case not in cfg['prospective_validation']:
    cfg=json.loads((here/'payload-motion-preregistration-02.json').read_bytes())
if case not in cfg['prospective_validation']:
    cfg=json.loads((here/'payload-motion-preregistration-03.json').read_bytes())
if case not in cfg['prospective_validation']:raise ValueError('unregistered prospective start')
native.REG['fresh_poses'][case]=cfg['prospective_validation'][case]
native.REG['roles'][case]='new_whole_trajectory_validation'
native.acquire(Path.cwd(),case,Path(sys.argv[2])/case)
