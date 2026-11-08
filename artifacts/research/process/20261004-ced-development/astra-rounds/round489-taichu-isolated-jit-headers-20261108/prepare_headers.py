"""Fetch one pinned dev archive and extract without installing any package."""
import hashlib, io, json, os, subprocess, tarfile, time
from pathlib import Path, PurePosixPath
import httpx
from cloud_edge_robot_arm.datasets.external.network import create_direct_transport
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[5]
CACHE=ROOT/'datasets/model-cache/zdtaichu5-9b-fp8-round473'
DEST=CACHE/'headers-round489'; DEB=CACHE/'libpython3.12-dev-round489.deb'
POLICY={'mode':'direct','interface':'enp7s0','dns_servers':['223.5.5.5','223.6.6.6'],
        'allowed_hosts':['security.ubuntu.com','cn.archive.ubuntu.com']}
PACKAGE='pool/main/p/python3.12/libpython3.12-dev_3.12.3-1ubuntu0.17_amd64.deb'
SIZE=5683746; SHA='c123ddab7763e45199e21b4ac8545e705f20a0315b9ada4c236b52fb088c4e16'
def save(name,value):
 with (HERE/name).open('x') as f: json.dump(value,f,indent=2,ensure_ascii=False); f.write('\n')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
start=time.monotonic()
for item in json.loads((HERE/'plan.json').read_text())['input_sha256']:
 p=ROOT/item['path']; assert p.stat().st_size==item['bytes'] and sha(p)==item['sha256'],p
save('input-review.json',{'status':'PASS','count':len(json.loads((HERE/'plan.json').read_text())['input_sha256'])})
save('download-protocol.json',{'policy':POLICY,'package':PACKAGE,'expected_bytes':SIZE,'expected_sha256':SHA,
    'primary_url':'https://security.ubuntu.com/ubuntu/'+PACKAGE,'max_bytes':6*1024**2,'no_system_install':True})
attempts=[]; body=None
for host in POLICY['allowed_hosts']:
 url='https://'+host+'/ubuntu/'+PACKAGE
 try:
  with httpx.Client(transport=create_direct_transport(POLICY),trust_env=False,timeout=60,follow_redirects=True) as client:
   response=client.get(url); response.raise_for_status()
   assert len(response.content)==SIZE and hashlib.sha256(response.content).hexdigest()==SHA
   body=response.content
   attempts.append({'url':url,'status':response.status_code,'final_url':str(response.url),'sha256':SHA,'bytes':len(body)})
  break
 except Exception as e:
  attempts.append({'url':url,'error_type':type(e).__name__,'error':str(e)})
if body is None:
 save('header-preparation.json',{'status':'NEGATIVE_DOWNLOAD_GATE','attempts':attempts,'elapsed_s':time.monotonic()-start}); raise SystemExit(2)
with DEB.open('xb') as f: f.write(body)
metadata=subprocess.run(['dpkg-deb','--field',str(DEB),'Package','Version','Architecture'],capture_output=True,text=True,check=True)
(HERE/'deb-metadata.stdout').write_text(metadata.stdout)
assert all(x in metadata.stdout for x in ['libpython3.12-dev','3.12.3-1ubuntu0.17','amd64'])
tarbytes=subprocess.run(['dpkg-deb','--fsys-tarfile',str(DEB)],capture_output=True,check=True).stdout
with tarfile.open(fileobj=io.BytesIO(tarbytes)) as archive:
 members=archive.getmembers(); listing=[]
 for member in members:
  name=PurePosixPath(member.name)
  assert not name.is_absolute() and '..' not in name.parts,member.name
  if member.issym() or member.islnk():
   resolved=(DEST/str(name)).parent.joinpath(member.linkname).resolve()
   assert resolved.is_relative_to(DEST.resolve()) or resolved.is_relative_to(Path('/usr/lib')) or resolved.is_relative_to(Path('/lib')), (name,member.linkname)
  listing.append({'path':member.name,'size':member.size,'link':member.linkname,'type':member.type.decode()})
save('deb-archive-list.json',{'members':listing,'path_validation':'PASS'})
DEST.mkdir(exist_ok=False)
extract=subprocess.run(['dpkg-deb','--extract',str(DEB),str(DEST)],capture_output=True,text=True,check=True)
rows=[]
for p in sorted(DEST.rglob('*')):
 if p.is_symlink(): rows.append({'path':str(p.relative_to(DEST)),'link':os.readlink(p)})
 elif p.is_file(): rows.append({'path':str(p.relative_to(DEST)),'bytes':p.stat().st_size,'sha256':sha(p)})
include=DEST/'usr/include/python3.12'; multi=DEST/'usr/include/x86_64-linux-gnu/python3.12'
assert (include/'Python.h').is_file() and (multi/'pyconfig.h').is_file()
patch=(include/'patchlevel.h').read_text(); assert '#define PY_VERSION              "3.12.3"' in patch
save('header-manifest.json',{'root':str(DEST),'deb':str(DEB),'deb_sha256':SHA,'files':rows})
save('header-preparation.json',{'status':'PASS','attempts':attempts,'elapsed_s':time.monotonic()-start,
 'CPATH':':'.join(map(str,[include,multi,DEST/'usr/include'])),'package_extracted_only':True,
 'system_modified':False,'base68_modified':False,'python_version':'3.12.3','new_model_loads':0})
print('HEADER_PREPARATION_PASS',round(time.monotonic()-start,3),flush=True)
