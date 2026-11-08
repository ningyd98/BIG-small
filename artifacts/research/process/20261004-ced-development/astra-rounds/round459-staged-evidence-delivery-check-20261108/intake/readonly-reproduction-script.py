from pathlib import Path
import hashlib,json,subprocess,re
root=Path.cwd();base=Path('artifacts/research/process/20261004-ced-development/astra-rounds');out=base/'round459-staged-evidence-delivery-check-20261108';(out/'intake').mkdir(parents=True,exist_ok=False)
def git(*args):return subprocess.run(['git',*args],cwd=root,capture_output=True,check=False)
def index_tree():
 p=git('ls-files','--stage','-z');assert p.returncode==0
 algo=git('rev-parse','--show-object-format').stdout.strip().decode();assert algo=='sha1'
 tree={};count=0
 for line in p.stdout.split(b'\0'):
  if not line:continue
  header,name=line.split(b'\t',1);mode,oid,stage=header.split();assert stage==b'0'
  node=tree;parts=name.split(b'/')
  for part in parts[:-1]:node=node.setdefault(part,{})
  node[parts[-1]]=(mode,oid);count+=1
 def digest_tree(node):
  rows=[]
  for name,v in node.items():
   mode,oid=(b'40000',digest_tree(v)) if isinstance(v,dict) else v
   rows.append((name+(b'/' if isinstance(v,dict) else b''),mode+b' '+name+b'\0'+bytes.fromhex(oid.decode())))
  raw=b''.join(v for _,v in sorted(rows));return hashlib.sha1(b'tree '+str(len(raw)).encode()+b'\0'+raw).hexdigest().encode()
 return {'tree_sha':digest_tree(tree).decode(),'object_format':algo,'stage0_entries':count,'ls_files_stage_sha256':hashlib.sha256(p.stdout).hexdigest(),'method':'Read-only Git tree object hashing from git ls-files --stage -z; no git write-tree, no Git object/index mutation'}
before=index_tree();r=git('diff','--cached','--check');(out/'intake/full-staged-check.stdout.log').write_bytes(r.stdout);(out/'intake/full-staged-check.stderr.log').write_bytes(r.stderr);after=index_tree()
manifest_path=base/'round457-openai-sol-cloud-migration-20261108/implementation/delivery-manifest.json';manifest=json.loads(manifest_path.read_text());print(manifest['files'][0])
files=[];warnings={}
for line in r.stdout.decode().splitlines():
 m=re.match(r'^(.*?):(\d+): (trailing whitespace|new blank line at EOF|space before tab in indent)\.',line)
 if m:warnings[m[1]]=warnings.get(m[1],0)+1
for p in warnings:
 raw=Path(p).read_bytes();s=git('show',':'+p);assert s.returncode==0
 files.append({'path':p,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'staged_sha256':hashlib.sha256(s.stdout).hexdigest(),'matches_index':s.stdout==raw,'warning_count':warnings[p]})
check={'argv':['git','diff','--cached','--check'],'returncode':r.returncode,'stdout_sha256':hashlib.sha256(r.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(r.stderr).hexdigest(),'index_before':before,'index_after':after,'index_unchanged':before==after,'warning_files':files,'prior_failed_execution':'ROOT reports earlier same command child rc2 and enclosing assert rc1; no prior raw file supplied. This saved output is one authorized fresh read-only reproduction.'}
(out/'intake/full-staged-check.result.json').write_text(json.dumps(check,ensure_ascii=False,indent=2)+'\n')
changed=git('diff','--cached','--name-only','-z');assert changed.returncode==0
actual={p.decode() for p in changed.stdout.split(b'\0') if p};expected={x['path'] for x in manifest['files']}|{str(manifest_path)}
rows=[]
for row in manifest['files']:
 s=git('show',':'+row['path']);sha=hashlib.sha256(s.stdout).hexdigest();rows.append({'path':row['path'],'manifest_sha256':row['sha256'],'staged_sha256':sha,'matches':s.returncode==0 and sha==row['sha256'] and len(s.stdout)==row['bytes']})
ms=git('show',':'+str(manifest_path));rows.append({'path':str(manifest_path),'current_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),'staged_sha256':hashlib.sha256(ms.stdout).hexdigest(),'matches':ms.returncode==0 and ms.stdout==manifest_path.read_bytes()})
coverage={'expected_staged_count':len(expected),'actual_staged_count':len(actual),'missing':sorted(expected-actual),'extra':sorted(actual-expected),'files':rows,'all_bytes_match':all(x['matches'] for x in rows),'index_tree_sha':after['tree_sha']}
(out/'intake/staged-manifest-check.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'directory':str(out),'returncode':r.returncode,'warnings':warnings,'index_tree_sha':after['tree_sha'],'index_unchanged':before==after,'staged_count':len(actual),'manifest_matches':coverage['all_bytes_match'],'missing':coverage['missing'],'extra':coverage['extra']},ensure_ascii=False,indent=2))
