from pathlib import Path
from hashlib import sha256
import difflib
import json
import shutil
import subprocess

ROOT=Path('/home/ningyd/文档/ChatGPT/BIGsmall')
DELIVERY=Path('/home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall')
WORK=Path('/tmp/bigsmall-system-architecture-20261011')
ROUND=ROOT/'artifacts/research/process/20261004-ced-development/astra-rounds/round-system-architecture-evidence-whitespace-20261011'
BRANCH='codex/research-20261007-p1-delivery'
OLD_HEAD='0bb613a6e927ae817e70abfc8b9ecaeb8f88d1c1'
EXCEPTION='artifacts/research/process/20261004-ced-development/astra-rounds/round-system-architecture-sharp-entry-20261011/implementation.diff'

def git(*args):
    return subprocess.check_output(['git',*args],cwd=DELIVERY)

def hash_bytes(data):
    return sha256(data).hexdigest()

def hash_file(p):
    return hash_bytes(p.read_bytes())

def index_paths():
    return {p.decode('utf-8') for p in git('diff','--cached','--name-only','-z').split(b'\0') if p}

def whitespace_check(p):
    result=subprocess.run(['git','diff','--cached','--check','--',p],cwd=DELIVERY,capture_output=True)
    assert result.returncode==0, {'path':p,'exit_code':result.returncode,'stdout':result.stdout.decode(),'stderr':result.stderr.decode()}

def verify_entries(entries):
    for entry in entries:
        p=entry['path']; expected=entry['sha256']
        assert hash_file(ROOT/p)==expected
        assert hash_file(DELIVERY/p)==expected
        assert hash_bytes(git('show',':'+p))==expected

plan=json.loads((ROUND/'plan.json').read_text(encoding='utf-8'))
for entry in plan['inputs']:
    assert hash_file(Path(entry['path']))==entry['sha256']
assert git('branch','--show-current').decode().strip()==BRANCH
assert git('rev-parse','HEAD').decode().strip()==OLD_HEAD
original=json.loads((WORK/'delivery-manifest.json').read_text(encoding='utf-8'))
original_paths={e['path'] for e in original}
assert len(original_paths)==25
assert index_paths()==original_paths
assert git('ls-files','--others','--exclude-standard','-z')==b''
assert git('diff','--name-only','-z')==b''
verify_entries(original)

old_script=ROOT/'artifacts/research/process/20261004-ced-development/astra-rounds/round-system-architecture-sharp-entry-20261011/build_diagram.frozen.mjs'
new_script=ROOT/'artifacts/research/process/20261004-ced-development/system-architecture-word-20261011/build_diagram.mjs'
reconstructed=''.join(difflib.unified_diff(old_script.read_text().splitlines(True),new_script.read_text().splitlines(True),fromfile='frozen',tofile='implemented')).encode('utf-8')
assert reconstructed==(ROOT/EXCEPTION).read_bytes()
assert hash_bytes(reconstructed)=='4124e3e01c47ddb720b3e2698b18b80673d825477326dc9c6c6cdc80989cebc1'
assert reconstructed.splitlines(True)[9]==b' \n'
known=subprocess.run(['git','-c','core.quotepath=false','diff','--cached','--check'],cwd=DELIVERY,capture_output=True)
assert known.returncode==2
assert known.stdout.decode()==EXCEPTION+':10: trailing whitespace.\n+ \n'
assert known.stderr==b''
for p in sorted(original_paths-{EXCEPTION}):
    whitespace_check(p)

assert not (ROUND/'original-delivery-manifest.json').exists()
shutil.copy2(WORK/'delivery-manifest.json',ROUND/'original-delivery-manifest.json')
verification={'expected_branch':BRANCH,'expected_head':OLD_HEAD,'initial_index_exact_25_files':True,'all_index_delivery_source_sha_match':True,'no_extra_untracked_or_unstaged_paths':True,'known_global_whitespace_check':{'exit_code':2,'output':known.stdout.decode()},'exception_exact_path':EXCEPTION,'exception_sha256':hash_bytes(reconstructed),'exception_line_10_hex':'200a','exception_diff_deterministically_reconstructed':True,'other_24_paths_whitespace_exit_code':0,'artwork_word_bytes_preserved':True,'global_whitespace_setting_changed':False,'gitattributes_changed':False}
(ROUND/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(ROUND/'step-report.md').write_text('''# 归档 diff 检查步骤报告

按本轮Astra计划复核branch、HEAD、25个index路径与全部来源/工作树/index SHA，均与冻结manifest一致，无额外或未暂存路径。已完整保存原始Git退出2和唯一诊断。

旧轮implementation.diff由冻结脚本与实施脚本通过同一difflib参数重建，完整SHA一致，第10行精确为200a，即标准unified diff空白上下文行。原证据字节不修改，只对此精确文件实行独立验证例外；其他24路径逐项cached whitespace检查退出0。全量cached检查仍有已知退出2，不声称全局通过。

本轮仅新增明确的计划、冻结manifest、续接脚本和验证/阶段报告；后续针对所有新增文件逐项检查，并核对最终index并集与全部SHA后提交现有分支。实际提交、推送和三方SHA结果由post-delivery-verification.json后验回执记录，不声称该回执包含于本次提交。

图与Word字节不变，不重新渲染，不执行真实系统或正式研究试验。
''',encoding='utf-8')
(ROUND/'stage-supplement.md').write_text('''# 系统架构图交付阶段补充

[架构图与Word阶段总结](../../system-architecture-word-20261011/summary.md)记录图导出及全部四页视觉验证。归档提交时出现标准unified diff上下文空行的whitespace诊断，原证据与原25个文件保留。

本轮按[Astra计划](plan.md)限定续接：对精确diff独立重建并核对SHA，对其他文件逐项检查；使用显式增量清单及index SHA核对，避免重复复制或混入脏文件。详细原始失败、输入、冻结脚本和验证均在本目录。

图导出和Word排版已通过；交付流程的最终commit/push结果见主工作区本目录post-delivery-verification.json后验回执，该回执在推送后创建且未包含于本次提交。真实系统运行未执行，正式研究验收未执行，未提供完整远端复现包。
''',encoding='utf-8')
names=['raw-git-check.json','deliver_git.frozen.py','inputs.json','plan.md','plan.json','original-delivery-manifest.json','resume_delivery.py','verification.json','step-report.md','stage-supplement.md']
assert {p.name for p in ROUND.iterdir() if p.is_file()}==set(names)
increments=[{'path':str((ROUND/name).relative_to(ROOT)),'sha256':hash_file(ROUND/name)} for name in names]
(ROUND/'incremental-manifest.json').write_text(json.dumps(increments,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
increments.append({'path':str((ROUND/'incremental-manifest.json').relative_to(ROOT)),'sha256':hash_file(ROUND/'incremental-manifest.json')})
for entry in increments:
    target=DELIVERY/entry['path']
    assert not target.exists()
for entry in increments:
    source=ROOT/entry['path']; target=DELIVERY/entry['path']
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target)
    assert hash_file(target)==entry['sha256']
git('add','--',*[e['path'] for e in increments])
all_entries=original+increments
paths=[e['path'] for e in all_entries]
assert index_paths()==set(paths)
verify_entries(all_entries)
assert git('diff','--name-only','-z')==b''
assert git('ls-files','--others','--exclude-standard','-z')==b''
for p in sorted(set(paths)-{EXCEPTION}):
    whitespace_check(p)

print(git('commit','-m','docs(research): add system architecture diagram to opening report').decode())
committed={p.decode('utf-8') for p in git('diff-tree','--no-commit-id','--name-only','-r','-z','HEAD').split(b'\0') if p}
assert committed==set(paths)
for entry in all_entries:
    assert hash_bytes(git('show','HEAD:'+entry['path']))==entry['sha256']
print(git('push','origin',BRANCH).decode())
local=git('rev-parse','HEAD').decode().strip()
upstream=git('rev-parse','@{upstream}').decode().strip()
remote=git('ls-remote','origin','refs/heads/'+BRANCH).decode().split()[0]
assert local==upstream==remote
assert git('status','--porcelain')==b''
receipt={'branch':BRANCH,'local_sha':local,'upstream_sha':upstream,'live_remote_sha':remote,'all_equal':True,'clean_delivery_worktree':True,'committed_path_count':len(paths),'commit_all_file_sha_verified':True,'original_25_files_preserved':True,'normal_file_whitespace_checks_passed':True,'known_diff_exception_verified_separately':EXCEPTION,'post_receipt_is_not_in_this_commit':True}
(WORK/'push-verification.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(ROUND/'post-delivery-verification.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt,ensure_ascii=False,indent=2))
