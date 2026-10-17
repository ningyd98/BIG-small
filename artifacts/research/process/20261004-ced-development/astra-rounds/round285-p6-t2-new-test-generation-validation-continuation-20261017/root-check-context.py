from pathlib import Path
import base64,copy,hashlib,json
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round285-p6-t2-new-test-generation-validation-continuation-20261017")
def pin(path,b=None):
 p=Path(path);b=p.read_bytes() if b is None else b
 return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def checked(q,physical=None):
 p=Path(physical or q["path"]);b=p.read_bytes();assert len(b)==q["bytes"] and hashlib.sha256(b).hexdigest()==q["sha256"];return b
def save(path,value):
 p=Path(path);b=(json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode()
 with p.open("xb") as f:f.write(b)
 assert p.read_bytes()==b
 return pin(p,b)
cp={"path":str(D/"root-context-update.json"),"bytes":345924,"sha256":"49cd24cf25524767ccaf07963dcdf6a334f192f234c8c915d060bddefebb4a0e"}
C=json.loads(checked(cp));P=json.loads(checked(C["plan"]));rows=C["changes"]
assert len(rows)==2 and C["round"]=="R285" and C["T2_complete"] is False
before={};after={};mapped={}
for row in rows:
 q=row["before"];b=base64.b64decode(q["base64"],validate=True)
 assert b==checked(q["archive"])==checked(q["original"],q["archive"]["path"])
 a=checked(row["after"]);assert a==checked(row["after_archive"])
 assert all(Path(x).lstat().st_mode==row["mode"]==33204 for x in (q["archive"]["path"],row["after"]["path"],row["after_archive"]["path"]))
 before[row["label"]]=b;after[row["label"]]=a;mapped[q["original"]["path"]]=row
assert {q["before"]["original"]["path"] for q in rows}=={q["path"] for q in P["context_update"]["before_inputs"]}
old=json.loads(before["STATE"]);new=json.loads(after["STATE"]);restored=copy.deepcopy(new)
for name in P["context_update"]["allowed_state_keys"]:
 key=name.split(".",1)[1]
 if key in old["planning"]:restored["planning"][key]=old["planning"][key]
 else:restored["planning"].pop(key,None)
assert restored==old and after["PHASE"].startswith(before["PHASE"])
assert new["planning"]["R276"]["previous_planning_snapshot"]==old["planning"]["R276"]
assert new["planning"]["R281"]["status"]=="SOURCE_ACCEPTED_BEHAVIOR_UNVERIFIED"
assert new["planning"]["R285"]["roles_created"] is False and new["planning"]["R285"]["runtime"]==0
assert all(q["used"]==0 and q["remaining"]==1 for q in new["planning"]["R285"]["commands"].values())
for q in P["inputs"]:
 if q["path"] in mapped:
  assert q==mapped[q["path"]]["before"]["original"];checked(q,mapped[q["path"]]["before"]["archive"]["path"])
 else:checked(q)
report={"round":"R285","status":"INDEPENDENT_CONTEXT_BYTES_SCOPE_AND_GENERATIONS_ACCEPTED","context_manifest":cp,"context_after":[q["after"] for q in rows],"only_exact_planning_keys":True,"old_PHASE_prefix_exact":True,"full_before_base64_and_modes":True,"initial_inputs":33,"mapped_exact_context_generations":2,"runtime":0,"T2_complete":False}
rp=save(D/"root-independent-context-review.json",report)
inputs=[cp]+[q["after"] for q in rows]+[rp,P["source_generation"]["acceptance"],pin(D/"root-initial-plan-input-review.json")]
S={"round":"R285","status":"ACTUAL_CONTEXT_PREREQUISITES_FROZEN_BEFORE_SOURCE_FINALIZATION","plan":pin(D/"plan.json"),"observation":P["input_observation"],"context_manifest":cp,"inputs":inputs,"input_count":len(inputs),"source_generation":P["source_generation"],"runtime":0,"T2_complete":False}
sp=save(D/"prerequisite-supplement.json",S)
output=json.dumps({"status":report["status"],"review":rp,"supplement":sp,"supplement_inputs":len(inputs),"context_after":report["context_after"]},ensure_ascii=False)
assert len((output+"\n").encode())<=6000
print(output)
