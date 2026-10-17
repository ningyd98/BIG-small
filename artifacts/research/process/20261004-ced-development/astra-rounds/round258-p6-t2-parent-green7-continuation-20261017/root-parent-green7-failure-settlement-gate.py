"""ROOT original R158.t2_green failure bookkeeping only; no repair or acceptance."""
import base64,copy,hashlib,json,os,stat,time
from pathlib import Path
R=Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D=R/"artifacts/research/process/20261004-ced-development/astra-rounds/round258-p6-t2-parent-green7-continuation-20261017"
started=time.monotonic()
def raw(path):
    path=Path(path);a=path.lstat()
    if not stat.S_ISREG(a.st_mode):raise ValueError("own regular file required")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        b=os.fstat(fd)
        with os.fdopen(fd,"rb",closefd=False) as f:content=f.read()
        c=os.fstat(fd)
    finally:os.close(fd)
    e=path.lstat()
    signature=lambda x:(x.st_dev,x.st_ino,x.st_mode,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
    if not all(signature(x)==signature(a) for x in (b,c,e)):raise ValueError("unstable metadata")
    return content,a.st_mode
def pin(path,content):
    return {"path":str(path),"bytes":len(content),"sha256":hashlib.sha256(content).hexdigest()}
def checked(p):
    content,mode=raw(p["path"])
    if pin(p["path"],content)!=p:raise ValueError("exact metadata pin changed")
    return content,mode
def encode(v):return (json.dumps(v,ensure_ascii=False,indent=2)+"\n").encode()
def save(path,content,mode=None):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("xb") as f:
        if mode is not None:os.fchmod(f.fileno(),stat.S_IMODE(mode))
        if f.write(content)!=len(content):raise ValueError("partial metadata write")
        f.flush();os.fsync(f.fileno())
    if raw(path)[0]!=content:raise ValueError("metadata archive readback")
    return pin(path,content)
P_PIN={"path":str(D/"plan.json"),"bytes":152521,"sha256":"50970ee4e58d28f7732686ff11befd01f1d56a3657a200d97dba9b45ffa764e7"}
RES_PIN={"path":str(D/"root-parent-green7-reservation.json"),"bytes":485237,"sha256":"3800e2227569acada86497b632151e4de3f7bf476a218a523869ed6003f1d99e"}
RESULT_PIN={"path":str(D/"implementation/green/result.json"),"bytes":540348,"sha256":"51714d471403baaf8a2e7b8dc3f3963c8a66c3ab951ab9400066ac7ed0485b8f"}
TOOL_PIN={"path":str(D/"implementation/green/actual-tool-return.json"),"bytes":4323,"sha256":"4e2e5867bc1e153751f943c760b5ff0ba01905d5ab47bd6746bc93c81ab9dbe2"}
P=json.loads(checked(P_PIN)[0]);res=json.loads(checked(RES_PIN)[0])
outcome=json.loads(checked(RESULT_PIN)[0]);tool=json.loads(checked(TOOL_PIN)[0])
assert "SPENT_UNEXPECTED_FAILURE" in P["ROOT_gates"]["post_run"]
assert outcome["timed_out"] is True and outcome["child_exit"]==-15 and outcome["wrapper_exit"]==2
assert outcome["accepted_command_outcome"] is False and outcome["JUnit"] is None
assert outcome["reservation_id"]==res["reservation_id"] and tool["invocation"]==P["command"]["exact_tool_arguments"]
assert tool["final"]==tool["actual_tool_return"] and tool["final"]["exit_code"]==2
assert tool["initial"]["session_id"]==5384 and len(tool["polls"])==len(tool["poll_invocations"])==9
assert tool["polls"][-1]==tool["final"]
for args in tool["poll_invocations"]:
    assert args["session_id"]==5384 and args["yield_time_ms"]<=60000 and args.get("chars","")==""
assert not Path(P["command"]["output_paths"]["JUnit"]).exists()
archives={}
for row in res["role_before"]:
    content=checked(row["archive"])[0]
    assert content==base64.b64decode(row["base64"],validate=True) and pin(row["original"]["path"],content)==row["original"]
    archives[row["original"]["path"]]=content
root_path=Path(P["budget"]["ROOT_ledger"]);author_path=Path(P["budget"]["author_ledger"])
continuation={"reservation_id":res["reservation_id"],"plan":res["plan"],"runner":res["runner"],
              "source_gate":res["source_gate"],"script_gate":res["script_gate"],"command":P["command"]}
expected_root=json.loads(archives[str(root_path)])
expected_root["commands"]["t2_green"].update(state="RESERVED_BY_ROOT",used=1,remaining=0,reservation_id=res["reservation_id"])
expected_root["commands"]["t2_green"].setdefault("continuation",{})["R258"]=continuation
expected_root["active_task"]="T2"
root_raw,root_mode=checked(res["root_role_after"])
assert json.loads(root_raw)==expected_root
expected_author=json.loads(archives[str(author_path)])
expected_author["commands"]["t2_green"].update(state="RESERVED",used=1,remaining=0,reservation_id=res["reservation_id"])
expected_author["commands"]["t2_green"].setdefault("continuation",{})["R258"]=continuation
author_reserved=encode(expected_author)
expected_author["commands"]["t2_green"].update(state="SPENT",result_path=P["command"]["output_paths"]["result"])
author_spent=encode(expected_author)
current_author,author_mode=checked(outcome["author_spent"])
assert current_author==author_spent and outcome["author_reserved"]==pin(author_path,author_reserved)
assert stat.S_IMODE(author_mode)==outcome["known_author_generations"]["mode"]
before=save(D/"before/root-parent-green7-failure-settlement/root-command-ledger.json",root_raw,root_mode)
after=copy.deepcopy(expected_root)
after["commands"]["t2_green"].update(state="SPENT_UNEXPECTED_FAILURE",used=1,remaining=0,
    result_path=RESULT_PIN["path"],failure_result=RESULT_PIN,failure_tool_return=TOOL_PIN)
new_raw=encode(after)
assert time.monotonic()-started<115
current,mode=raw(root_path)
assert current==root_raw and mode==root_mode
temp=D/"before/root-parent-green7-failure-settlement/root-failure.next"
save(temp,new_raw,root_mode)
current,mode=raw(root_path)
assert current==root_raw and mode==root_mode
os.replace(temp,root_path)
current,mode=raw(root_path)
assert current==new_raw and mode==root_mode
record={"round":"R258","status":"SPENT_UNEXPECTED_FAILURE","original_key":"R158.t2_green",
        "root_before":{"original":res["root_role_after"],"archive":before,
                       "base64":base64.b64encode(root_raw).decode(),"mode":root_mode},
        "root_after":pin(root_path,current),"author_after":pin(author_path,current_author),
        "result":RESULT_PIN,"transport":TOOL_PIN,"used":1,"remaining":0,
        "all_other_original_entries_unchanged":True,"retry":False,"T2_complete":False,
        "JUnit_available":False,"actual_wait_attempts":2,"actual_wait_failures":2,
        "cleanup_fact_only":outcome["cleanup"],
        "boundary":"Failure bookkeeping only. No full resource/behavior acceptance; original raw unchanged. Actual Astra R266 cause plan pending."}
receipt=save(D/"root-parent-green7-failure-settlement.json",encode(record))
print(json.dumps({"status":record["status"],"receipt":receipt,"root_after":record["root_after"],
                  "author_after":record["author_after"],"T2_complete":False},ensure_ascii=False))

