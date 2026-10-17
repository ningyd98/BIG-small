from pathlib import Path
import base64,hashlib,json,stat
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round281-p6-t2-post-expiry-session-denial-assertion-20261017")
R276=D.parent/"round276-p6-t2-first-session-invalidation-capture-20261017"
checks=[]
def check(name,ok):
 checks.append({"check":name,"passed":bool(ok)})
def pin(path):
 p=Path(path);b=p.read_bytes();return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def checked(q):
 b=Path(q["path"]).read_bytes()
 check("identity "+q["path"],stat.S_ISREG(Path(q["path"]).lstat().st_mode) and pin(q["path"])=={k:q[k] for k in ("path","bytes","sha256")})
 return b
def full(q):
 b=base64.b64decode(q["base64"],validate=True)
 check("full physical before",checked(q["archive"])==b and len(b)==q["original"]["bytes"] and hashlib.sha256(b).hexdigest()==q["original"]["sha256"])
 return b
pp={"path":str(D/"plan.json"),"bytes":19723,"sha256":"389975e1fff90a33d53f955327e6480d59580f9359ddde9989eab075ccae5733"}
op={"path":str(D/"input-observation.json"),"bytes":22475,"sha256":"9a3b73d109d6402cf4eaee37d4b1f279c05aba9b9fa853c0203b67632ec4e05f"}
P=json.loads(checked(pp));O=json.loads(checked(op))
check("frozen actual Astra input list",P["round"]=="R281" and P["actual_model"]=="gpt-6-astra" and P["inputs"]==O["inputs"])
for q in P["inputs"]:checked(q)
M=json.loads(checked(P["full_before"]["manifest"]));test=full(M)
check("current full test before/base64/mode",test==checked(P["full_before"]["archive"])==Path(P["scope"]["target"]).read_bytes() and Path(P["scope"]["target"]).lstat().st_mode==Path(M["archive"]["path"]).lstat().st_mode==M["mode"]==33204)
ap={"path":str(R276/"root-wait-memory-independent-acceptance.json"),"bytes":120457,"sha256":"eb3e394b3922882dafe939510fbfb8f49fd9ef63ba6cf80b2a2ef32494ceada0"}
accepted=json.loads(checked(ap));root_before=full(accepted["root_before"])
check("precise planned historical ROOT resolves only full before",P["role_snapshots"]["ROOT"]==accepted["root_before"]["original"])
root=json.loads(checked(accepted["root_after"]));author=json.loads(checked(accepted["author_after"]))
check("exact unchanged planned AUTHOR",P["role_snapshots"]["AUTHOR"]==accepted["author_after"])
check("original failure settled on both roles only",root["commands"]["wait_memory"]["state"]=="SPENT_UNEXPECTED_FAILURE" and author["commands"]["wait_memory"]["state"]=="SPENT" and all(v["commands"]["wait_memory"]["used"]==1 and v["commands"]["wait_memory"]["remaining"]==0 for v in (root,author)))
check("other identities remain unused held",all(v["commands"][k]["state"]=="HELD_PENDING_ROOT_SOURCE_INPUT_ARGV_GATE" and v["commands"][k]["used"]==0 and v["commands"][k]["remaining"]==1 for v in (root,author) for k in ("wait_sqlite","dual_first_invalidation")))
check("ROOT actual integrity accepted only",accepted["status"]=="INDEPENDENT_FAILED_WAIT_CAPTURE_ACCEPTED_SPENT" and accepted["behavior_accepted"] is False and accepted["checks_passed"]==479 and all(q["passed"] for q in accepted["checks"]))
index=json.loads(checked(next(q for q in P["inputs"] if q["path"]==str(R276/"implementation/wait_memory/before/source-index.json"))))
check("finite actual current source authority",len(index["sources"])==27 and len(index["authority_before"]["protected"])==211)
for row in index["sources"]:
 b=checked(row)
 check("current full source/base64/archive/mode",b==checked(row["physical"])==base64.b64decode(row["base64"],validate=True) and Path(row["path"]).lstat().st_mode==row["mode"])
for row in index["authority_before"]["protected"]:checked(row)
sg=json.loads(checked(next(q for q in P["inputs"] if q["path"]==str(R276/"source-gate.json"))))
for row in sg["sources"].values():checked(row)
failed=[q for q in checks if not q["passed"]]
report={"round":"R281","status":"ROOT_SOURCE_ONLY_RELEASE_PREREQUISITES_PASSED" if not failed else "FAILED_STOP_ASTRA","checks":checks,"failed":failed,"inputs":len(P["inputs"]),"full_before":P["full_before"],"R283_acceptance":ap,"historical_ROOT_exact_before":accepted["root_before"],"current_ROOT":accepted["root_after"],"current_AUTHOR":accepted["author_after"],"sources":27,"protected":211,"runtime":0,"T2_complete":False}
path=D/"root-initial-source-input-review.json"
with path.open("x",encoding="utf-8") as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
output=json.dumps({"status":report["status"],"checks":len(checks),"failed":len(failed),"report":pin(path)},ensure_ascii=False)
assert len((output+"\n").encode())<=6000
print(output)
raise SystemExit(2 if failed else 0)
