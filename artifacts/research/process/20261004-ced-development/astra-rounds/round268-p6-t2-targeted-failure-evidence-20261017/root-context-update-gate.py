"""ROOT R268 factual context append, full before bytes and immediate CAS only."""
import base64,copy,hashlib,json,os,stat,time
from pathlib import Path
R=Path("/home/ningyd/文档/ChatGPT/BIGsmall")
B=R/"artifacts/research/process/20261004-ced-development"
D=B/"astra-rounds/round268-p6-t2-targeted-failure-evidence-20261017"
START=time.monotonic()
def pin(path,raw):return {"path":str(path),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
def read(path):
    path=Path(path);a=path.lstat()
    if not stat.S_ISREG(a.st_mode):raise ValueError("own regular metadata required")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        b=os.fstat(fd)
        with os.fdopen(fd,"rb",closefd=False) as stream:raw=stream.read()
        c=os.fstat(fd)
    finally:os.close(fd)
    e=path.lstat();sig=lambda v:(v.st_dev,v.st_ino,v.st_mode,v.st_size,v.st_mtime_ns,v.st_ctime_ns)
    if not all(sig(v)==sig(a) for v in (b,c,e)):raise ValueError("metadata changed while reading")
    return raw,a.st_mode
def checked(p):
    raw,mode=read(p["path"])
    if pin(p["path"],raw)!=p:raise ValueError("exact context input differs")
    return raw,mode
def encoded(v):return (json.dumps(v,ensure_ascii=False,indent=2)+"\n").encode()
def save(path,raw,mode=None):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("xb") as stream:
        if mode is not None:os.fchmod(stream.fileno(),stat.S_IMODE(mode))
        if stream.write(raw)!=len(raw):raise ValueError("partial metadata write")
        stream.flush();os.fsync(stream.fileno())
    if read(path)[0]!=raw:raise ValueError("before archive readback differs")
    return pin(path,raw)
PLAN_PIN={"path":str(D/"plan.json"),"bytes":34233,"sha256":"ea92b785c2058e7f373ef444dc22655a043b9235f963e80098b4c015b4448c52"}
OBS_PIN={"path":str(D/"input-observation.json"),"bytes":25321,"sha256":"b9bf488904254377daf32daa0ddaca61aafc5f24194c10605a1983e42a00c03e"}
P=json.loads(checked(PLAN_PIN)[0]);O=json.loads(checked(OBS_PIN)[0])
for p in O["inputs"]:checked(p)
assert len(O["inputs"])==45
pins={p["path"]:p for p in O["inputs"]}
def known(round_name,filename):
    return next(p for p in O["inputs"] if "/"+round_name+"/" in p["path"] and p["path"].endswith("/"+filename))
d258="round258-p6-t2-parent-green7-continuation-20261017"
d264="round264-p6-t2-parent-bridge-lifecycle-case-binding-20261017"
d266="round266-p6-t2-parent-green7-timeout-disposition-20261017"
d267="round267-p6-t2-planner-control-before-schema-disposition-20261017"
entries={
 "R258":{"status":"SPENT_UNEXPECTED_FAILURE","result":known(d258,"result.json"),"step":known(d258,"step-report.json"),
         "original_key":"R158.t2_green","used":1,"remaining":0,"child_exit":-15,"wrapper_exit":2,
         "timed_out":True,"runner_elapsed_seconds":600.7672149199934,"wait_failures":2,"JUnit":None,
         "T2_complete":False,"cause":"Exact wait raise site and dual timeout cause unresolved."},
 "R264":{"status":"SOURCE_CORRECTION_ACCEPTED_RUNTIME_GATE_ONLY","plan":known(d264,"plan.json"),
         "source_bytes":71517,"source_lines":1243,"source_sha256":"c157178f61ae3609356fa9441f9f953b116a4ebccbd8f324b172b6d2c0980cba",
         "boundary":"Lifecycle/case-binding source correction; parent GREEN7 later failed; not T2 acceptance."},
 "R267":{"status":"METADATA_DISPOSITION_ACCEPTED","plan":known(d267,"plan.json"),"step":known(d267,"step-report.json"),
         "original_failed_chunk":"7c28c8","replayed":False,"boundary":"Planning schema only; product failure remains."},
 "R266":{"status":"ORIGINAL_KEY_FAILURE_SETTLEMENT_ACCEPTED","plan":known(d266,"plan.json"),
         "step":known(d266,"step-report.json"),"ROOT_acceptance":known(d266,"root-failure-settlement-acceptance.json"),
         "settlement":known(d258,"root-parent-green7-failure-settlement.json"),"T2_complete":False,
         "preservation":"27 sources/211 protected;10 R258 DB original/archive pairs,2 present/28 absent sidecars; noSQL."},
 "R268":{"status":"SOURCE_PREPARATION_ONLY_DIAGNOSTICS_PENDING","plan":PLAN_PIN,"observation":OBS_PIN,
         "commands":{k:{"authorized":1,"used":0,"remaining":1,"state":"HELD_PENDING_ROOT_SOURCE_INPUT_ARGV_GATE"} for k in P["commands"]},
         "context_manifest_path":str(D/"root-context-update.json"),"runtime_released":False,
         "T2_complete":False,"T12_complete":False,"native_accepted":False,"formal_accepted":False,"Git_authorized":False}}
H=P["history_and_context"]
state_path,phase_path=Path(H["state_path"]),Path(H["phase_path"])
state_raw,state_mode=checked(pins[str(state_path)]);phase_raw,phase_mode=checked(pins[str(phase_path)])
state=json.loads(state_raw)
assert type(state["planning"]) is dict and all(k not in state["planning"] for k in entries)
new=copy.deepcopy(state);new["planning"].update(entries)
restored=copy.deepcopy(new)
for k in entries:del restored["planning"][k]
assert restored==state
phase_append=("\n\n## R258、R264、R266、R267 与 R268（2026-10-17）\n\n"
 "父 GREEN7 原槽已实际执行并记为 SPENT_UNEXPECTED_FAILURE，ROOT/author 均用1余0。实际 stdout 为 FF；两个等待后端有 DID NOT RAISE，后续整轮达到600秒边界，runner记录600.7672149199934秒，child -15、wrapper2，无JUnit。精确失败行号与第三dual节点停止位置仍未知；T2/T12/native/formal未通过。\n\n"
 "R264 已完成新运行脚本生命周期与真实案例归属的源码修正，ROOT 1496项源码/输入门通过；其含义限于源码准备，父测试失败完整保留。R267已处置规划器control_before字段读取错误，原7c28c8不重放。R266按完整before/base64/CAS结算原键失败，独立读回确认其他条目与mode不变；27源码、211保护文件及10个新数据库原件/归档保留，2个present与28个absent侧文件分别记录，无SQL。1059/1055/1059仅两份完成侧车分母，第三节点分配未知。\n\n"
 "R268已由实际gpt-6-astra冻结两个独立、各一次的取证计划：memory等待单节点与dual单节点，各600秒加15秒清理，pytest原生540秒单次线程栈。被动异常frame只保留真实tb_lineno及有限unwind后原生值；尚未运行、未修产品。下一步完成新源码/native/输入/argv门，逐槽预留取证，再据真实证据制定下一轮Astra修复计划。fresh12与Git0保持待放行。\n\n"
 "证据（完整path/bytes/SHA记录在对应JSON与本轮context manifest）：\n\n"+
 "\n".join("- "+str(v["path"])+"；"+str(v["bytes"])+" B；SHA256 "+v["sha256"]
 for v in (known(d258,"step-report.json"),known(d258,"root-parent-green7-failure-settlement.json"),
           known(d264,"plan.json"),known(d267,"step-report.json"),known(d266,"step-report.json"),PLAN_PIN))+"\n")
new_phase=phase_raw+phase_append.encode()
prepared=[(state_path,state_raw,encoded(new),state_mode),(phase_path,phase_raw,new_phase,phase_mode)]
base=D/"before/root-context-update";assert not base.exists() and not base.is_symlink()
assert not (D/"root-context-update.json").exists()
changes=[]
for path,before,after,mode in prepared:
    archive=save(base/path.name,before,mode)
    changes.append({"before":{"original":pin(path,before),"archive":archive,
                             "base64":base64.b64encode(before).decode()},"after":pin(path,after),"mode":mode})
for path,before,after,mode in prepared:
    if time.monotonic()-START>115:raise TimeoutError("original metadata bound")
    actual,current_mode=read(path);assert actual==before and current_mode==mode
    temporary=base/(path.name+".next");save(temporary,after,mode)
    actual,current_mode=read(path);assert actual==before and current_mode==mode
    os.replace(temporary,path)
    actual,current_mode=read(path);assert actual==after and current_mode==mode
manifest={"round":"R268","status":"FACTUAL_CONTEXT_UPDATED","plan":PLAN_PIN,"observation":OBS_PIN,
          "changes":changes,"all_other_state_values_preserved":True,"phase_previous_bytes_exact_prefix":True,
          "T2_complete":False,"T12_complete":False,"runtime_released":False,
          "old_role_mutations":False,"context_frozen_during_two_diagnostics":True}
receipt=save(D/"root-context-update.json",encoded(manifest))
print(json.dumps({"status":manifest["status"],"manifest":receipt,"after":[r["after"] for r in changes],
                  "all_other_state_values_preserved":True,"runtime_released":False},ensure_ascii=False))

