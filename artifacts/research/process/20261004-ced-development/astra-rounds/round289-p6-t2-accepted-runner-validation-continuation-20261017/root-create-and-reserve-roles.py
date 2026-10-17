from pathlib import Path
import base64
import copy
import hashlib
import json
import os
import shlex
import stat
import sys
import uuid
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017")
MODE=33204
KEYS=("wait_memory","wait_sqlite","dual_first_invalidation")
def require(ok,message):
 if not ok:raise RuntimeError(message)
def raw(path):
 p=Path(path)
 require(stat.S_ISREG(p.lstat().st_mode),"regular-file bytes required: "+str(p))
 return p.read_bytes()
def pin(path,data=None):
 p=Path(path);b=raw(p) if data is None else data
 return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def checked(q):
 b=raw(q["path"]);require(pin(q["path"],b)==q,"physical identity differs: "+q["path"]);return b
def load(path):return json.loads(raw(path))
def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode()
def write(path,b):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("xb") as f:f.write(b);f.flush();os.fsync(f.fileno())
 p.chmod(0o664);require(raw(p)==b,"exclusive readback differs")
 return pin(p,b)
def write_json(path,value):return write(path,encoded(value))
def absent(path):
 p=Path(path);require(not p.exists() and not p.is_symlink(),"exclusive path already exists: "+str(p))
def authorities():
 P=load(D/"plan.json");SG=load(D/"source-gate.json");JG=load(D/"script-gate.json");AG=load(D/"root-final-source-acceptance.json")
 require(P["round"]==SG["round"]==JG["round"]==AG["round"]=="R289","round differs")
 require(SG["status"]=="VERIFIED_SOURCE_ONLY" and JG["status"]=="VERIFIED_BY_ROOT" and AG["status"]=="FULL_SOURCE_NATIVE_INPUT_ARGV_ACCEPTED_NO_DISPATCH","source gates required")
 require(SG["plan"]==JG["plan"]==pin(D/"plan.json") and JG["source_gate"]==pin(D/"source-gate.json"),"plan/source gate identity differs")
 require(AG["source_gate"]==pin(D/"source-gate.json") and AG["script_gate"]==pin(D/"script-gate.json"),"final acceptance differs")
 require(JG["sources"]==SG["sources"] and JG["commands"]==P["commands"],"exact reviewed source/commands differ")
 roles={k:P["runner_contract"]["roles"][k] for k in ("ROOT","AUTHOR")}
 require(JG["role_files"]==roles and tuple(P["commands"])==KEYS,"three role command interface differs")
 for q in list(SG["sources"].values())+SG["fixed_inputs"]+[SG["input_check"],SG["native"],SG["context_manifest"]]:checked(q)
 return P,SG,JG,roles
def initialize(P,SG,JG,roles):
 for path in roles.values():absent(path)
 for command in P["commands"].values():absent(command["output_directory"])
 output=D/"root-role-initialization.json";absent(output)
 prepared={}
 for role,path in roles.items():
  value={"round":"R289","role":role,"plan":SG["plan"],"commands":{}}
  for key in KEYS:
   command=P["commands"][key]
   require((command["authorized"],command["used"],command["remaining"],command["state"])==(1,0,1,"HELD_PENDING_ROOT_SOURCE_INPUT_ARGV_GATE"),"new once budget differs")
   value["commands"][key]={"authorized":1,"used":0,"remaining":1,"state":"HELD_PENDING_ROOT_SOURCE_INPUT_ARGV_GATE","command":command}
  prepared[role]=encoded(value)
 manifest={"round":"R289","status":"NEW_ROLES_HELD_ZERO_USED","source_gate":pin(D/"source-gate.json"),"script_gate":pin(D/"script-gate.json"),"role_before":None,"role_after":[],"runtime":0}
 for role,path in roles.items():
  archive=write(D/"before/roles/initial"/(role+".json"),prepared[role])
  manifest["role_after"].append({"role":role,"original":pin(path,prepared[role]),"archive":archive,"mode":MODE,"base64":base64.b64encode(prepared[role]).decode("ascii")})
 for path in roles.values():absent(path)
 for role,path in roles.items():write(path,prepared[role])
 result=write_json(output,manifest)
 print(json.dumps({"status":"NEW_ROLES_HELD_ZERO_USED","manifest":result,"roles":{role:pin(path) for role,path in roles.items()}},ensure_ascii=False))
def prior_runs(P,SG,key):
 path=D/"root-prior-run-supplements"/(key+".json")
 value=load(path)
 expected=list(KEYS[:KEYS.index(key)])
 require(value["round"]=="R289" and value["command_id"]==key and value["plan"]==SG["plan"] and value["observation"]==SG["observation"],"exact selected prior supplement binding required")
 rows=value["prior_receipts"]
 require(type(rows) is list and len(rows)==len(expected)<=2 and [row["command_id"] for row in rows]==expected,"ordered finite prior receipts required")
 for position,row in enumerate(rows):
  accepted=json.loads(checked(row["acceptance"]))
  require(accepted["round"]=="R289" and accepted["command_id"]==expected[position] and accepted["status"]=="VERIFIED_COMPLETE_BEHAVIOR_CAPTURE","prior independent normal behavior acceptance required")
  for field in ("result","actual_tool_return","persistent_index"):
   require(row[field]==accepted[field],"prior acceptance pin join differs")
   checked(row[field])
  index=json.loads(checked(row["persistent_index"]))
  require(row["new_retained_databases"]==index["new_retained_databases"]==accepted["new_retained_databases"],"prior actual DB list differs")
  for pair in row["new_retained_databases"]:
   require(checked(pair["pin"])==checked(pair["archive"]),"prior retained DB bytes differ")
   require(type(pair["sidecars"]) is list and len(pair["sidecars"])==3,"prior three actual sidecar states required")
   for side in pair["sidecars"]:
    require(side["is_symlink"] is False,"prior sidecar symlink differs")
    if side["exists"]:require(checked(side["pin"])==checked(side["archive"]),"prior present sidecar bytes differ")
    else:
     require(side["pin"] is None,"prior absent sidecar pin must remain null")
     absent(side["path"])
  if position==len(rows)-1:
   release=accepted["next_command_release"]
   require(release["status"]=="NEXT_INDEPENDENT_COMMAND_ALLOWED" and release["next_key"]==key,"prior independent next-key decision required")
 return pin(path),value

def reserve(P,SG,JG,roles,key):
 require(key in KEYS,"one exact selected command required")
 directory=D/"root-reservations";target=directory/(key+".json");absent(target)
 command=P["commands"][key];absent(command["output_directory"])
 prior_pin,prior_value=prior_runs(P,SG,key)
 invocation=copy.deepcopy(command["tool_arguments"])
 expected_launcher=["env","-i"]+[name+"="+value for name,value in command["launcher_env"].items()]+["/usr/bin/timeout","--signal=TERM","--kill-after=15s","900s"]+command["runner_argv"]
 require(shlex.split(invocation["cmd"])==expected_launcher and invocation["workdir"]==command["cwd"] and invocation["yield_time_ms"]==10000 and invocation["max_output_tokens"]==1800,"literal frozen env-i runner transport required before reservation")
 require(all(Path(path).lstat().st_mode==MODE for path in roles.values()),"exact current role modes required")
 current={role:raw(path) for role,path in roles.items()}
 values={role:json.loads(b) for role,b in current.items()}
 for role,value in values.items():
  require(value["round"]=="R289" and value["role"]==role and value["plan"]==SG["plan"] and set(value["commands"])==set(KEYS),"exact current role identity required")
  selected=value["commands"][key]
  require((selected["authorized"],selected["used"],selected["remaining"],selected["state"])==(1,0,1,"HELD_PENDING_ROOT_SOURCE_INPUT_ARGV_GATE") and selected["command"]==command,"selected role must be unused HELD")
 for previous in KEYS[:KEYS.index(key)]:
  for value in values.values():require(value["commands"][previous]["state"].startswith("SPENT") and value["commands"][previous]["used"]==1 and value["commands"][previous]["remaining"]==0,"earlier command must be settled")
 if KEYS.index(key):
  previous=KEYS[KEYS.index(key)-1]
  release=values["ROOT"]["commands"][previous]["next_command_release"]
  require(release["status"]=="NEXT_INDEPENDENT_COMMAND_ALLOWED" and release["next_key"]==key,"ROOT independent applicability decision required")
  checked(release["independent_acceptance"])
  require(release["independent_acceptance"]==prior_value["prior_receipts"][-1]["acceptance"],"ledger and prior supplement release must join exact acceptance")
 reservation_id="R289."+key+"."+str(uuid.uuid4())
 continuation={"prior_runs_supplement":prior_pin,"reservation_id":reservation_id,"plan":SG["plan"],"source_gate":pin(D/"source-gate.json"),"script_gate":pin(D/"script-gate.json"),"sources":SG["sources"],"command":command}
 after=copy.deepcopy(values["ROOT"]);selected=after["commands"][key]
 selected.update(state="RESERVED_BY_ROOT",used=1,remaining=0,reservation_id=reservation_id)
 selected.setdefault("continuation",{})["R289"]=continuation
 after_raw=encoded(after)
 before=[]
 for role,path in roles.items():
  archive=write(directory/"before"/key/(role+".json"),current[role])
  before.append({"original":pin(path,current[role]),"archive":archive,"mode":MODE,"base64":base64.b64encode(current[role]).decode("ascii")})
 after_archive=write(directory/"prepared"/key/"ROOT.json",after_raw)
 require(invocation==command["tool_arguments"],"literal transport must equal frozen plan before reservation")
 reservation={"prior_runs_supplement":prior_pin,"round":"R289","command_id":key,"reservation_id":reservation_id,"command":command,"sources":SG["sources"],"plan":SG["plan"],"source_gate":continuation["source_gate"],"script_gate":continuation["script_gate"],"context_manifest":SG["context_manifest"],"role_before":before,"root_role_after":pin(roles["ROOT"],after_raw),"author_role_before":pin(roles["AUTHOR"],current["AUTHOR"]),"root_after_archive":after_archive,"exact_tool_arguments":invocation}
 reservation_pin=write_json(target,reservation)
 # Check full bytes and modes immediately before selected ROOT mutation.
 for role,path in roles.items():require(Path(path).lstat().st_mode==MODE and raw(path)==current[role],"role CAS conflict")
 fd=os.open(roles["ROOT"],os.O_RDWR|os.O_NOFOLLOW)
 with os.fdopen(fd,"r+b") as f:
  require(os.fstat(f.fileno()).st_mode==MODE and f.read()==current["ROOT"],"ROOT descriptor CAS conflict")
  require(Path(roles["AUTHOR"]).lstat().st_mode==MODE and raw(roles["AUTHOR"])==current["AUTHOR"],"AUTHOR immediate CAS conflict")
  f.seek(0);f.write(after_raw);f.truncate();f.flush();os.fsync(f.fileno())
 require(raw(roles["ROOT"])==after_raw and raw(roles["AUTHOR"])==current["AUTHOR"],"reserved roles readback differs")
 require(load(target)==reservation,"reservation readback differs")
 print(json.dumps({"status":"SELECTED_ROOT_RESERVED_NO_DISPATCH","command_id":key,"reservation":reservation_pin,"root_role_after":pin(roles["ROOT"]),"author_role_before":reservation["author_role_before"],"exact_tool_arguments":invocation},ensure_ascii=False))
require(len(sys.argv) in (2,3) and sys.argv[1] in ("initialize","reserve"),"explicit finite mode required")
P,SG,JG,roles=authorities()
if sys.argv[1]=="initialize":
 require(len(sys.argv)==2,"initialize has no selected key")
 initialize(P,SG,JG,roles)
else:
 require(len(sys.argv)==3,"reserve needs exact selected key")
 reserve(P,SG,JG,roles,sys.argv[2])

