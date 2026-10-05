import os,subprocess,json
from pathlib import Path
root=Path.cwd();result=[]
modules=['cloud_edge_robot_arm.repositories.event_autonomy.memory','cloud_edge_robot_arm.repositories.event_autonomy.protocol','cloud_edge_robot_arm.repositories.event_autonomy.visual_owner','cloud_edge_robot_arm.repositories.event_autonomy.sqlite','cloud_edge_robot_arm.vision.owner_registration']
for module in modules:
 p=subprocess.run([str(root/'.venv/bin/python'),'-c',f'import {module}; print("COLD_IMPORT_OK {module}")'],env={**os.environ,'PYTHONPATH':'src','PYTHONDONTWRITEBYTECODE':'1'},text=True,capture_output=True)
 result.append({'module':module,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
(root/'artifacts/research/process/20261004-ced-development/t12-visual-owner-repository/cold-imports.log').write_text(json.dumps(result,indent=2)+'\n')
raise SystemExit(any(item['returncode'] for item in result))
