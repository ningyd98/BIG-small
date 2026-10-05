from pathlib import Path
import subprocess, json
root=Path.cwd(); artifact=root/'artifacts/research/process/20261004-ced-development/t12-visual-owner-repository'
owned=json.loads((artifact/'ownership.json').read_text())['owned']
checks=[]
for name,start,end in [('memory.py','    def _visual_original_locked','    # ── generic idempotency helpers'),('sqlite.py','    def _visual_original_locked','    def close'),('protocol.py','    def initialize_visual_owner_if_absent','    # ── Events')]:
 p=root/'src/cloud_edge_robot_arm/repositories/event_autonomy'/name
 text=p.read_text();a=text.index(start);b=text.index(end,a)
 fragment=artifact/'format-scope'/name;fragment.parent.mkdir(exist_ok=True)
 fragment.write_text('class _ScopedFormat:\n'+text[a:b].rstrip()+'\n')
 result=subprocess.run([str(root/'.venv/bin/ruff'),'format','--check',str(fragment)],text=True,capture_output=True)
 checks.append({'file':str(p.relative_to(root)),'code':result.returncode,'output':result.stdout+result.stderr})
result=subprocess.run([str(root/'.venv/bin/ruff'),'format','--check',*owned[-2:]],text=True,capture_output=True)
checks.append({'files':owned[-2:],'code':result.returncode,'output':result.stdout+result.stderr})
(artifact/'format-scoped.log').write_text(json.dumps(checks,indent=2)+'\n')
raise SystemExit(any(c['code'] for c in checks))
