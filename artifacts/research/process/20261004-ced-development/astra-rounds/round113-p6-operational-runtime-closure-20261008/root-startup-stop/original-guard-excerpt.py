# Observe only processes whose cwd is this project; do not print arbitrary command lines.
root=Path.cwd().resolve();active=[]
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
 try:
  if proc.joinpath('cwd').resolve()!=root:continue
  args=proc.joinpath('cmdline').read_bytes().split(b'\0');names={Path(a.decode(errors='replace')).name for a in args if a}
  tags=sorted(names & {'pytest','run_operational_prefix_v1.py','run_rgbd_pilot.py','run_native_calibration.py','collect_native_calibration.py'})
  if tags:active.append({'pid':int(proc.name),'recognized_tasks':tags})
 except (OSError,RuntimeError):continue
assert not active,active
