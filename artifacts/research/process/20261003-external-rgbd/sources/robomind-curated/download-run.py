import datetime,json,sys
from pathlib import Path
from urllib.parse import urlencode
sys.path.insert(0, str(Path.cwd()/'src'))
from cloud_edge_robot_arm.datasets.external.transfer import download_plan,plan_budget
GIB=1024**3
art=Path('artifacts/research/process/20261003-external-rgbd/sources/robomind-curated')
rev='b6ccc32d861713fdf786b9f237a1bcfb51a1063b'
files=json.loads((art/f'example-tree-{rev}.json').read_text())['Data']['Files']
f=next(f for f in files if f['Path']=='example_data/pick_apple_into_drawer_h5 2.zip')
plan={'dataset_id':'robomind_curated','source':'modelscope','repo_id':'X-Humanoid/RoboMIND','revision':rev,'license':'apache-2.0','target_subset':'example_data/pick_apple_into_drawer_h5 2.zip','variant':'official_small_example','selection_scope':'1 task, 2 complete example trajectories; not original full target','data_root':'/home/ningyd/datasets/BIGsmall','budget_bytes':250*GIB,'dataset_budget_bytes':10*GIB,'minimum_free_bytes':50*GIB,'extraction_estimated_bytes':181000000,'estimation':'ESTIMATED','files':[{'path':f['Path'],'size':f['Size'],'sha256':f['Sha256'],'role':'complete_example_zip','url':'https://modelscope.cn/api/v1/datasets/X-Humanoid/RoboMIND/repo?'+urlencode({'Revision':rev,'FilePath':f['Path']})}],'network':{'mode':'direct','interface':'enp7s0','dns_servers':['223.5.5.5','223.6.6.6'],'allowed_hosts':['modelscope.cn','cdn-lfs-cn-1.modelscope.cn']},'access':{'anonymous':True,'terms_accepted':False,'private':False,'gated':False},'pinned_source_evidence':str(art/f'example-tree-{rev}.json'),'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
Path('configs/rgbd_sources/robomind_curated.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
(art/'pinned-source-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
(art/'download-plan-budget.json').write_text(json.dumps(plan_budget(plan),ensure_ascii=False,indent=2)+'\n')
print('Pinned source plan saved; download starting.',flush=True)
try:
 result=download_plan(plan,max_workers=1,retries=2)
except Exception as exc:
 result={'status':'FAILED','error_type':type(exc).__name__,'reason':str(exc)}
(art/'download-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False),flush=True)
