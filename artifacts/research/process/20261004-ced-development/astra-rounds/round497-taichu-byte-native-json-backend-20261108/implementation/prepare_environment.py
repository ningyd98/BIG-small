"""Install one pinned native decoder wheel; original runtime71 remains read-only."""
import hashlib,json,os,subprocess,sys,venv,zipfile
from pathlib import Path
import httpx
from packaging.utils import canonicalize_name
from cloud_edge_robot_arm.datasets.external.network import create_direct_transport
HERE=Path(__file__).resolve().parent.parent;ROOT=HERE.parents[5];CACHE=ROOT/'datasets/model-cache/zdtaichu5-9b-fp8-round473';OLD=HERE.parent/'round486-taichu-no-think-best-profile-20261108'
def save(name,value):
 with (HERE/name).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for row in json.loads((HERE/'plan.json').read_text())['input_sha256']:
 p=ROOT/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],p
metadata=json.loads((HERE/'diagnostic/package-readout.json').read_text());assert metadata['version']=='1.9.1' and metadata['requires_dist'] is None
row=metadata['wheels'][0];assert row['bytes']==3071973 and row['sha256']=='dfac6021d9c4c5ef16b3a1d336c05ca5e8208ff30dec29d1c63ebcafbee3a346'
original={canonicalize_name(k):v for k,v in json.loads((OLD/'fla-environment.json').read_text())['distributions'].items()};assert len(original)==71
protected={canonicalize_name(x['name']) for x in json.loads((OLD/'final-environment-base.json').read_text())['base68']}|{'flash-linear-attention','fla-core'};assert set(original)==protected|{'pip'} and len(protected)==70
env=os.environ.copy()
for k in ['PYTHONPATH','PYTHONHOME']:env.pop(k,None)
env['PYTHONNOUSERSITE']='1'
def snapshot(python):
 r=subprocess.run([str(python),str(HERE/'implementation/runtime_inventory.py')],cwd=CACHE,env=env,capture_output=True,text=True,check=True);return json.loads(r.stdout)
before=snapshot(CACHE/'runtime-fla-round486/bin/python');assert {r['name']:{k:r[k] for k in ['version','location']} for r in before['distributions']}==original
save('original-runtime-before.json',before)
policy={'mode':'direct','interface':'enp7s0','dns_servers':['223.5.5.5','223.6.6.6'],'allowed_hosts':['files.pythonhosted.org']}
save('wheel-manifest.json',{'wheel':row,'policy':policy,'max_download_bytes':3071973,'declared_dependencies':None})
wheels=CACHE/'wheels-round497';wheels.mkdir(exist_ok=False)
with httpx.Client(transport=create_direct_transport(policy),trust_env=False,timeout=60,follow_redirects=True) as client:
 response=client.get(row['url']);response.raise_for_status();assert len(response.content)==row['bytes']
 wheel=wheels/row['filename'];wheel.write_bytes(response.content);assert sha(wheel)==row['sha256']
with zipfile.ZipFile(wheel) as archive:
 names=archive.namelist();assert all(not n.startswith('/') and '..' not in Path(n).parts for n in names)
 assert all(n.split('/')[0] in ['llguidance','llguidance-1.9.1.dist-info'] for n in names),names
 sources={n:hashlib.sha256(archive.read(n)).hexdigest() for n in names if n.endswith(('.py','.pyi'))}
 save('library-static-review.json',{'wheel_sha256':row['sha256'],'files':names,'python_source_sha256':sources})
overlay=CACHE/'runtime-llguidance-round497';venv.EnvBuilder(with_pip=False).create(overlay);site=overlay/'lib/python3.12/site-packages';python=overlay/'bin/python'
(site/'readonly-original71.pth').write_text(str(CACHE/'runtime-fla-round486/lib/python3.12/site-packages')+'\n'+str(ROOT/'.venv-taichu-round473/runtime-b/lib/python3.12/site-packages')+'\n')
argv=[str(python),'-m','pip','install','--no-index','--no-deps','--target',str(site),'--disable-pip-version-check','--report',str(HERE/'install-report.json'),str(wheel)]
with (HERE/'install.stdout').open('xb') as o,(HERE/'install.stderr').open('xb') as e:subprocess.run(argv,cwd=CACHE,env=env,stdout=o,stderr=e,check=True)
r=subprocess.run([str(python),'-m','pip','check'],cwd=CACHE,env=env,capture_output=True,text=True);(HERE/'pip-check.stdout').write_text(r.stdout);(HERE/'pip-check.stderr').write_text(r.stderr);assert r.returncode==0
snapshot_after=snapshot(python);after={r['name']:r for r in snapshot_after['distributions']};before_rows={r['name']:r for r in before['distributions']}
assert len(after)==72 and set(after)-set(before_rows)=={'llguidance'}
assert all(after[k]==v for k,v in before_rows.items())
assert after['llguidance']['version']=='1.9.1' and after['llguidance']['location']==str(site)
assert all(snapshot_after['modules'][k]==v for k,v in before['modules'].items())
assert Path(snapshot_after['modules']['llguidance']['origin']).is_relative_to(site)
f=subprocess.run([str(python),'-m','pip','freeze','--all'],cwd=CACHE,env=env,capture_output=True,text=True,check=True);(HERE/'freeze.txt').write_text(f.stdout)
save('environment.json',{'status':'PASS','original_visible71_unchanged':True,'protected_model70_unchanged':True,'pip_preserved':True,'exact_addition':'llguidance==1.9.1','total_distributions':72,'python':str(python),'actual_runtime':snapshot_after,'install_argv':argv,'pip_check_rc':r.returncode,'LMFE_overlay_not_present':True,'model_loads':0,'generation_calls':0})
print('ENVIRONMENT_PASS original71+llguidance1.9.1=72',flush=True)
