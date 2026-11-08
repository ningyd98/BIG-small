"""Install exactly two verified wheels into an isolated overlay, preserving original70."""
import hashlib,importlib.metadata as md,json,os,subprocess,sys,time,venv,zipfile
from pathlib import Path
import httpx
from packaging.requirements import Requirement
from cloud_edge_robot_arm.datasets.external.network import create_direct_transport
HERE=Path(__file__).resolve().parent.parent; ROOT=HERE.parents[5]
CACHE=ROOT/'datasets/model-cache/zdtaichu5-9b-fp8-round473'
OLD=HERE.parent/'round486-taichu-no-think-best-profile-20261108'
def save(name,value):
 with (HERE/name).open('x') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(name):return name.lower().replace('_','-')
plan=json.loads((HERE/'plan.json').read_text())
for item in plan['input_sha256']:
 p=ROOT/item['path'];assert p.stat().st_size==item['bytes'] and sha(p)==item['sha256'],p
metadata=json.loads((HERE/'diagnostic/package-readout.json').read_text())['packages']
original=json.loads((OLD/'fla-environment.json').read_text())['distributions']
assert len(original)==70
requirements=[]
for package in metadata:
 for expression in package['requires_dist'] or []:
  req=Requirement(expression)
  if req.marker and not req.marker.evaluate():continue
  if canonical(req.name)=='interegular':version='0.3.3'
  else:version=original[canonical(req.name)]['version']
  assert req.specifier.contains(version,prereleases=True),expression
  requirements.append({'requirement':expression,'satisfied_version':version})
rows=[{'name':p['name'],'version':p['version'],**p['wheels'][0]} for p in metadata]
assert sum(p['bytes'] for p in rows)==69053
policy={'mode':'direct','interface':'enp7s0','dns_servers':['223.5.5.5','223.6.6.6'],'allowed_hosts':['files.pythonhosted.org']}
save('wheel-manifest.json',{'wheels':rows,'policy':policy,'requirements':requirements,'max_download_bytes':131072})
wheels=CACHE/'wheels-round491';wheels.mkdir(exist_ok=False)
with httpx.Client(transport=create_direct_transport(policy),trust_env=False,timeout=60,follow_redirects=True) as client:
 for row in rows:
  response=client.get(row['url']);response.raise_for_status();assert len(response.content)==row['bytes']
  path=wheels/row['filename'];path.write_bytes(response.content);assert sha(path)==row['sha256']
  with zipfile.ZipFile(path) as archive:
   names=archive.namelist();assert all(not n.startswith('/') and '..' not in Path(n).parts for n in names)
   expected={'lm-format-enforcer':['lmformatenforcer','lm_format_enforcer-0.11.3.dist-info'],'interegular':['interegular','interegular-0.3.3.dist-info']}[row['name']]
   assert all(n.split('/')[0] in expected for n in names),names
   if row['name']=='lm-format-enforcer':
    source=archive.read('lmformatenforcer/integrations/transformers.py')
    save('library-static-review.json',{'wheel_sha256':row['sha256'],'files':names,'TF_adapter_source_sha256':hashlib.sha256(source).hexdigest(),'TF_adapter_imports_LogitsWarper':b'import LogitsWarper' in source or b'LogitsWarper,' in source,'backend_agnostic_API_source_sha256':hashlib.sha256(archive.read('lmformatenforcer/tokenenforcer.py')).hexdigest()})
overlay=CACHE/'runtime-json-round491';venv.EnvBuilder(with_pip=False).create(overlay)
site=overlay/'lib/python3.12/site-packages';old_fla=CACHE/'runtime-fla-round486/lib/python3.12/site-packages';old_base=ROOT/'.venv-taichu-round473/runtime-b/lib/python3.12/site-packages'
(site/'readonly-original70.pth').write_text(str(old_fla)+'\n'+str(old_base)+'\n')
env=os.environ.copy()
for key in ['PYTHONPATH','PYTHONHOME']:env.pop(key,None)
env['PYTHONNOUSERSITE']='1';python=overlay/'bin/python'
argv=[str(python),'-m','pip','install','--no-index','--no-deps','--target',str(site),'--disable-pip-version-check','--report',str(HERE/'install-report.json')]+[str(wheels/r['filename']) for r in rows]
with (HERE/'install.stdout').open('xb') as out,(HERE/'install.stderr').open('xb') as err:
 result=subprocess.run(argv,env=env,cwd=CACHE,stdout=out,stderr=err,check=True)
check=subprocess.run([str(python),'-m','pip','check'],env=env,cwd=CACHE,capture_output=True,text=True)
(HERE/'pip-check.stdout').write_text(check.stdout);(HERE/'pip-check.stderr').write_text(check.stderr);assert check.returncode==0,check.stdout
visible={canonical(d.metadata['Name']):{'version':d.version,'location':str(Path(d.locate_file('')).resolve())} for d in md.distributions(path=[str(site),str(old_fla),str(old_base)])}
for name,row in original.items():assert visible[canonical(name)]==row,(name,visible.get(canonical(name)),row)
assert len(visible)==72
save('environment.json',{'status':'PASS','python':str(python),'overlay':str(overlay),'original70_unchanged':True,'distributions':visible,'install_argv':argv,'pip_check_rc':check.returncode,'scope':'offline install/metadata only; no CUDA or model load','added_packages':['lm-format-enforcer==0.11.3','interegular==0.3.3']})
print('ENVIRONMENT_PASS original70 unchanged; exactly2 additions',flush=True)
