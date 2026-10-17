"""R268 ROOT selected-key reservation only; no diagnostic execution."""
from pathlib import Path
import base64,copy,hashlib,json,os,stat,sys,uuid
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round268-p6-t2-targeted-failure-evidence-20261017")
def pin(path,raw): return {"path":str(path),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
def checked(p):
 q=Path(p["path"]); info=q.lstat(); assert stat.S_ISREG(info.st_mode)
 raw=q.read_bytes(); assert len(raw)==p["bytes"] and hashlib.sha256(raw).hexdigest()==p["sha256"]
 return raw
def save(path,raw,mode=None):
 path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("xb") as h:
  assert h.write(raw)==len(raw); h.flush(); os.fsync(h.fileno())
 if mode is not None: os.chmod(path,stat.S_IMODE(mode))
 assert path.read_bytes()==raw
 return pin(path,raw)
def encoded(v): return (json.dumps(v,ensure_ascii=False,indent=2)+"\n").encode()
assert len(sys.argv)==2 and sys.argv[1] in ("wait_memory_failure","dual_progress")
name=sys.argv[1]
source_pin={"path":str(D/"source-gate.json"),"bytes":16900,"sha256":"e146dd8f805e238b45fde809ea7af373e495c94429862270620d51ed6b90d9b8"}
sg=json.loads(checked(source_pin))
p=json.loads(checked(sg["plan"]))
assert sg["round"]=="R268" and sg["status"]=="VERIFIED_SOURCE_ONLY"
for item in sg["fixed_inputs"]: checked(item)
for item in sg["sources"].values(): checked(item)
check_raw=checked(sg["input_check"]); c=json.loads(check_raw)
script_path=D/"script-gate.json"; script_raw=script_path.read_bytes(); script_gate=json.loads(script_raw)
assert script_gate["round"]=="R268" and script_gate["status"]=="VERIFIED_BY_ROOT"
assert script_gate["source_gate"]==source_pin and script_gate["plan"]==sg["plan"] and script_gate["sources"]==sg["sources"]
assert script_gate["commands"]==p["commands"] and script_gate["role_files"]==p["runner_contract"]["role_files"]
script_pin=pin(script_path,script_raw)
roles=p["runner_contract"]["role_files"]; before={}; values={}; rows=[]
for role in ("ROOT","AUTHOR"):
 path=Path(roles[role]); raw=path.read_bytes(); mode=path.lstat().st_mode
 assert stat.S_ISREG(mode)
 value=json.loads(raw)
 assert value["round"]=="R268" and value["role"]==role and value["plan"]==sg["plan"]
 assert set(value["commands"])==set(p["commands"])
 entry=value["commands"][name]
 assert entry["authorized"]==1 and entry["used"]==0 and entry["remaining"]==1
 assert entry["state"]=="HELD_PENDING_ROOT_SOURCE_INPUT_ARGV_GATE" and entry["command"]==p["commands"][name]
 before[role]=(path,raw,mode); values[role]=value
reservation_path=D/"root-reservations"/(name+".json")
assert not reservation_path.exists() and not reservation_path.is_symlink()
for role in ("ROOT","AUTHOR"):
 path,raw,mode=before[role]
 archive=save(D/"before/reservations"/name/(role+".json"),raw,mode)
 rows.append({"original":pin(path,raw),"archive":archive,"base64":base64.b64encode(raw).decode("ascii"),"mode":mode})
reservation_id="R268."+name+"."+str(uuid.uuid4())
continuation={"reservation_id":reservation_id,"plan":sg["plan"],"source_gate":source_pin,"script_gate":script_pin,"sources":sg["sources"],"command":p["commands"][name]}
next_root=copy.deepcopy(values["ROOT"]); selected=next_root["commands"][name]
selected.update(state="RESERVED_BY_ROOT",used=1,remaining=0,reservation_id=reservation_id)
selected.setdefault("continuation",{})["R268"]=continuation
raw_after=encoded(next_root)
root_path,root_raw,mode=before["ROOT"]
temporary=root_path.with_name(root_path.name+"."+name+".next")
save(temporary,raw_after,mode)
assert root_path.read_bytes()==root_raw and root_path.lstat().st_mode==mode
author_path,author_raw,author_mode=before["AUTHOR"]
assert author_path.read_bytes()==author_raw and author_path.lstat().st_mode==author_mode
os.replace(temporary,root_path)
assert root_path.read_bytes()==raw_after and root_path.lstat().st_mode==mode
reservation={"round":"R268","command_id":name,"reservation_id":reservation_id,"plan":sg["plan"],"source_gate":source_pin,"script_gate":script_pin,"sources":sg["sources"],"command":p["commands"][name],"exact_tool_arguments":c["exact_tool_arguments"][name],"role_before":rows,"root_role_after":pin(root_path,raw_after),"author_role_before":pin(author_path,author_raw),"context_manifest":sg["context_manifest"]}
reservation_pin=save(reservation_path,encoded(reservation))
print(json.dumps({"round":"R268","command_id":name,"reservation":reservation_pin,"root_role_after":reservation["root_role_after"],"author_role_before":reservation["author_role_before"],"exact_tool_arguments":reservation["exact_tool_arguments"],"runtime_executed":False},ensure_ascii=False))
