from pathlib import Path
import base64,hashlib,json,shlex,stat
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round285-p6-t2-new-test-generation-validation-continuation-20261017")
checks=[]
def check(name,ok):checks.append({"check":name,"passed":bool(ok)})
def pin(path):
 p=Path(path);b=p.read_bytes();return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def checked(q):
 p=Path(q["path"]);b=p.read_bytes();check("identity "+str(p),stat.S_ISREG(p.lstat().st_mode) and len(b)==q["bytes"] and hashlib.sha256(b).hexdigest()==q["sha256"]);return b
def load(q):return json.loads(checked(q))
def absent(path):
 p=Path(path);check("absence "+str(p),not p.exists() and not p.is_symlink())
P=load({"path":str(D/"plan.json"),"bytes":47877,"sha256":"22983a42ecd12e188440b42a0491c059957e96998b546e769e3bd3ceaef0ffa0"})
O=load(P["input_observation"])
check("frozen actual Astra33 inputs and305 observations",P["actual_model"]=="gpt-6-astra" and P["inputs"]==O["inputs"] and len(P["inputs"])==33 and O["check_count"]==len(O["checks"])==305 and all(q["passed"] for q in O["checks"]))
for q in P["inputs"]:checked(q)
M=load(P["before_manifest"])
check("three complete physical template/test records",len(M["records"])==3)
for row in M["records"]:
 b=base64.b64decode(row["base64"],validate=True)
 check("complete before original/archive/base64/mode",checked(row["original"])==checked(row["archive"])==b and Path(row["original"]["path"]).lstat().st_mode==Path(row["archive"]["path"]).lstat().st_mode==row["mode"]==33204)
SX=load(P["authority_contract"]["container"]);A=SX["authority_before"]
check("finite27/211/68",len(SX["sources"])==len(O["current_sources"])==27 and len(A["protected"])==211 and len(A["accepted_history_generations"])==68)
current={q["path"]:q for q in O["current_sources"]}
check("same27 explicit paths",set(current)=={q["path"] for q in SX["sources"]})
for row in SX["sources"]:
 b=checked(row["physical"]);check("old exact source physical/base64",b==base64.b64decode(row["base64"],validate=True))
 now=current[row["path"]];actual=checked(now)
 if row["path"]==P["source_generation"]["current_test"]["path"]:
  check("typed exact test generation ebf1 to193f",row["sha256"]=="ebf1e58187dc14fb607f8b6506284fd64532cbef1b41931740c216eba50367bb" and now["sha256"]=="193f45147160f52ba53956df506ddbc602b81f2248990eea604366a39e63ef13")
 else:check("other26 unchanged",actual==b and now["sha256"]==row["sha256"])
 check("current source mode",Path(row["path"]).lstat().st_mode==now["mode"]==row["mode"])
for q in A["protected"]:checked(q)
for q in A["missing_registry35"]:absent(q["original"]["path"])
for q in A["old_absent_sidecars90"]:absent(q["path"])
check("missing35/old90 bounds",len(A["missing_registry35"])==35 and len(A["old_absent_sidecars90"])==90)
for name,count in (("R242_R248",12),("R251",18)):
 rows=A["old_retained_groups"][name];check("old group count "+name,len(rows)==count)
 for row in rows:
  checked(row["pin"])
  for q in row["sidecars"]:check("old sidecar absent declaration",q["exists"] is False and q["is_symlink"] is False);absent(q["path"])
pairs=A["R258_retained_DB_pairs"];check("R258ten",len(pairs)==10)
all_pairs=pairs+[q["record"] for q in O["known_database_records"]]
check("new known R268six plusR276four",len(O["known_database_records"])==10)
for row in all_pairs:
 check("retained original/archive rawbytes",checked(row["pin"])==checked(row["archive"]))
 for q in row["sidecars"]:
  check("retained sidecar not symlink",q["is_symlink"] is False)
  if q["exists"]:check("retained present sidecar raw pair",checked(q["pin"])==checked(q["archive"]))
  else:check("retained absent sidecar pin null",q["pin"] is None);absent(q["path"])
for key in ("ROOT","AUTHOR"):absent(P["runner_contract"]["roles"][key])
for path in P["scope"]["new_sources"]:absent(path)
for name,command in P["commands"].items():
 absent(command["output_directory"])
 check("new independent once "+name,(command["authorized"],command["used"],command["remaining"])==(1,0,1) and command["limits"]["attempts"]==1 and command["limits"]["retries"]==0)
 check("literal env-i launcher "+name,shlex.split(command["tool_arguments"]["cmd"])==["env","-i"]+[k+"="+v for k,v in command["launcher_env"].items()]+command["launcher_argv"] and command["tool_arguments"]["workdir"]==command["cwd"] and command["env_inheritance"] is False)
 check("finite protected times "+name,command["limits"]["child_seconds"]==600 and command["limits"]["cleanup_total_seconds"]==15 and command["limits"]["outer_total_seconds"]==900 and command["limits"]["faulthandler_seconds"]==540)
check("three exact command identities",tuple(P["commands"])==("wait_memory","wait_sqlite","dual_first_invalidation"))
failed=[q for q in checks if not q["passed"]]
report={"round":"R285","status":"INITIAL_PLAN_INPUT_PREREQUISITES_ACCEPTED" if not failed else "FAILED_STOP_ASTRA","checks":checks,"failed":failed,"inputs":33,"current_sources":27,"protected":211,"history68_reaudited":False,"R268_R276_DB_count":10,"roles_created":False,"context_updated":False,"runtime":0,"T2_complete":False}
path=D/"root-initial-plan-input-review.json"
with path.open("x",encoding="utf-8") as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
output=json.dumps({"status":report["status"],"checks":len(checks),"failed":len(failed),"report":pin(path)},ensure_ascii=False)
assert len((output+"\n").encode())<=6000
print(output)
raise SystemExit(2 if failed else 0)
