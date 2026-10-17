from pathlib import Path
import os,json
needles=['run_operational_prefix_v1.py','collect_native_calibration.py','run_rgbd_pilot.py','probe_rgbd_roles.py','generate_rgbd_protocol_evidence.py','visible_marker','marker_observ'];live=[]
for p in Path('/proc').iterdir():
 if not p.name.isdecimal() or int(p.name)==os.getpid():continue
 try:
  args=(p/'cmdline').read_bytes().split(b'\0');matches=[n for n in needles if any(n.encode() in a and len(a)<1024 for a in args)]
  if matches:live.append({'pid':int(p.name),'scripts':matches})
 except (FileNotFoundError,PermissionError,ProcessLookupError):pass
print(json.dumps({'live_actual_matches':live}));assert not live
