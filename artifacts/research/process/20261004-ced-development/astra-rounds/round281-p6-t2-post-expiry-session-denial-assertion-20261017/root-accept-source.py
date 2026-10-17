from pathlib import Path
import base64,hashlib,json,stat
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round281-p6-t2-post-expiry-session-denial-assertion-20261017")
I=D/"implementation"
R276=D.parent/"round276-p6-t2-first-session-invalidation-capture-20261017"
checks=[]
def check(name,ok):checks.append({"check":name,"passed":bool(ok)})
def identity(q):return {k:q[k] for k in ("path","bytes","sha256")}
def pin(path,b=None):
 p=Path(path);b=p.read_bytes() if b is None else b
 return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def checked(q,physical=None):
 p=Path(physical or q["path"]);b=p.read_bytes()
 check("physical "+str(p),stat.S_ISREG(p.lstat().st_mode) and len(b)==q["bytes"] and hashlib.sha256(b).hexdigest()==q["sha256"])
 return b
def load(q):return json.loads(checked(q))
def full(q):
 b=base64.b64decode(q["base64"],validate=True)
 check("full before/after "+q["original"]["path"],checked(q["archive"])==b and pin(q["original"]["path"],b)==identity(q["original"]))
 return b
def once(b,old,new):
 check("unique exact scoped substitution",b.count(old)==1)
 return b.replace(old,new,1)
pp={"path":str(D/"plan.json"),"bytes":19723,"sha256":"389975e1fff90a33d53f955327e6480d59580f9359ddde9989eab075ccae5733"}
P=load(pp)
R=load({"path":str(I/"change-report.json"),"bytes":8353,"sha256":"1ad0bd66c577bfd5a0e9a14679cc4a94d72e3071478ec8b790c9b153de0071a8"})
N=load(R["native_receipt"]);M=load(P["full_before"]["manifest"]);before=full(M)
immediate=load(R["before"]["manifest"])
check("immediate and planning complete before",before==full(immediate)==checked(R["before"]["archive"]) and identity(M["original"])==identity(immediate["original"]) and M["mode"]==immediate["mode"]==R["before"]["mode"]==33204)
after=checked(R["after"])
check("current candidate full after exact identity",after==checked(R["candidate"])==checked(R["after_archive"]) and len(after)==255468 and hashlib.sha256(after).hexdigest()=="193f45147160f52ba53956df506ddbc602b81f2248990eea604366a39e63ef13" and Path(R["after"]["path"]).lstat().st_mode==R["after_mode"]==33204)
check("source-only actual no runtime",R["runtime_commands"]==R["test_commands"]==R["new_budget"]==0 and R["roles_modified"] is R["context_modified"] is R["T2_complete"] is False and N["runtime_executed"] is False)
start=209599;old_size=3534;new_size=4870
old=before[start:start+old_size];new=after[start:start+new_size]
check("exact scope boundaries",old.startswith(b"                def exercise(") and old.endswith(b"                    return operation_id\n") and before[:start]==after[:start] and before[start+old_size:]==after[start+new_size:])
check("earlier168003 prefix fixed",before[:168003]==after[:168003] and hashlib.sha256(after[:168003]).hexdigest()=="66b6c373123299b52f17a6946dd7a77a0d2962b31ce6391261a93f8b01f0612f")
expected=once(old,b"                    from cloud_edge_robot_arm.contracts import RobotState\n",b"                    from cloud_edge_robot_arm.contracts import RobotState\n                    from cloud_edge_robot_arm.simulation_runtime.operational_lease import OperationalLeaseError\n")
first=b'                        with pytest.raises((RuntimeError, ValueError),\n                                           match="expired|deadline|invalid|bound|live|domain|authority"):\n                            _b_t2_operation(runtime, events, transition)'
expected=once(expected,first,first.replace(b'"):\n',b'") as first_denial:\n'))
post=b'                    with pytest.raises((RuntimeError, ValueError),\n                                       match="expired|deadline|invalid|bound|live|domain|authority"):\n                        runtime.reserve_capture(RobotState(connected=True), initial=True)'
expected=once(expected,post,P["scope"]["exact_lease_branch"].encode())
field=b'                        "clock_identities": [asdict(raw.current_identity)\n                                             for _, raw, _ in observed.clocks],\n'
addition=b'                        "first_denial": {"type": type(first_denial.value).__name__,\n                                         "message": str(first_denial.value)},\n                        "subsequent_denial": {"type": type(subsequent_denial.value).__name__,\n                                              "message": str(subsequent_denial.value)},\n'
expected=once(expected,field,field+addition)
check("only four exactly approved scoped changes",new==expected and before[:start]+expected+before[start+old_size:]==after)
p274=load(next(q for q in P["inputs"] if q["path"].endswith("/round274-p6-t2-wait-fixture-clock-scope-20261017/plan.json")))
for q in p274["exact_source_change"]["changes"]:
 fragment=q["new"].encode();check("R274 exact prior edit preserved",before.count(fragment)==after.count(fragment)>=1)
check("actual native honest nulls",N["actual_tool_return"]=={} and N["numeric_exit"] is N["independent_stdout"] is N["independent_stderr"] is None)
lines=N["arguments"].splitlines()
check("one native update exact target",lines[0]=="*** Begin Patch" and lines[1]=="*** Update File: "+R["after"]["path"] and lines[-1]=="*** End Patch")
units=[]
for line in lines[2:-1]:
 if line=="@@":units.append([])
 else:
  check("native unit exact prefix",bool(units) and bool(line) and line[0] in " +-")
  units[-1].append(line)
reconstructed=before
for unit in units:
 old_part=("\n".join(v[1:] for v in unit if v[0] in " -")+"\n").encode()
 new_part=("\n".join(v[1:] for v in unit if v[0] in " +")+"\n").encode()
 reconstructed=once(reconstructed,old_part,new_part)
check("four actual native hunks fully reconstruct",len(units)==4 and reconstructed==after)
archive=checked(R["native_patch"]);argument=N["arguments"].encode()
check("native parameter distinct exact one-LF archive representation",not argument.endswith(b"\n") and archive==argument+b"\n")
G=load(R["preservation"]["generation_manifest"])
check("full current after generation base64/mode",full(G["after"])==after and G["after"]["mode"]==33204 and identity(G["after"]["original"])==R["after"])
load(R["preservation"]["candidate_scope_proof"]);checked(R["limited_diff"])
prep=load({"path":str(I/"source-preparation-actual-tool-returns.json"),"bytes":80201,"sha256":"a7c3c436997515f4c6359e77276562a51df2f356ed966e74ae7cb8d578638f96"})
check("all metadata actuals succeeded no runtime",prep["runtime_commands"]==0 and all(q["actual_tool_return"]["exit_code"]==0 for q in prep["stages"]))
for q in P["inputs"]:
 if q["path"]==R["after"]["path"]:
  check("only precise ebf1 logical input maps to full before",identity(q)==identity(M["original"]));checked(q,M["archive"]["path"])
 else:checked(q)
ap={"path":str(R276/"root-wait-memory-independent-acceptance.json"),"bytes":120457,"sha256":"eb3e394b3922882dafe939510fbfb8f49fd9ef63ba6cf80b2a2ef32494ceada0"}
accepted=load(ap);full(accepted["root_before"])
check("old planned ROOT only exact historical archive",P["role_snapshots"]["ROOT"]==identity(accepted["root_before"]["original"]))
for key,q in R["preservation"]["roles_exact_current"].items():checked(q)
check("current roles equal actual accepted generations",R["preservation"]["roles_exact_current"]=={"ROOT":accepted["root_after"],"AUTHOR":accepted["author_after"]})
index=load(next(q for q in P["inputs"] if q["path"]==str(R276/"implementation/wait_memory/before/source-index.json")))
check("exact source27 and protected211 counts",len(index["sources"])==27 and len(index["authority_before"]["protected"])==211)
for row in index["sources"]:
 b=checked(row["physical"])
 check("full actual source before archive/base64",b==base64.b64decode(row["base64"],validate=True))
 if row["path"]==R["after"]["path"]:
  check("one exact oldtest to newtest generation",identity(row)==identity(M["original"]) and b==before and Path(row["path"]).read_bytes()==after)
 else:check("other26 actual current",checked(row)==b)
 check("actual current source mode",Path(row["path"]).lstat().st_mode==row["mode"])
for row in index["authority_before"]["protected"]:checked(row)
sg=load(next(q for q in P["inputs"] if q["path"]==str(R276/"source-gate.json")))
for q in sg["sources"].values():checked(q)
for q in sg["fixed_inputs"]:
 if q["path"]==R["after"]["path"]:
  check("R276 historical gate test resolves only full ebf1 before",identity(q)==identity(M["original"]));checked(q,M["archive"]["path"])
 else:checked(q)
failed=[q for q in checks if not q["passed"]]
report={"round":"R281","status":"SOURCE_ACCEPTED_BEHAVIOR_UNVERIFIED" if not failed else "FAILED_STOP_ASTRA","checks":checks,"failed":failed,"plan":pp,"before_manifest":P["full_before"]["manifest"],"immediate_before_manifest":R["before"]["manifest"],"after":R["after"],"physical_after":R["after_archive"],"native":R["native_receipt"],"native_actual_argument":{"container":R["native_receipt"],"member":"arguments","bytes":len(argument),"sha256":hashlib.sha256(argument).hexdigest()},"archive_representation":R["native_patch"],"generation_manifest":R["preservation"]["generation_manifest"],"source_preparation_actuals":pin(I/"source-preparation-actual-tool-returns.json"),"R283_accepted_settlement":ap,"roles_current":R["preservation"]["roles_exact_current"],"source_count":27,"protected_count":211,"runtime":0,"behavior_accepted":False,"T2_complete":False,"native_accepted":False,"formal_accepted":False}
path=D/"root-independent-source-acceptance.json"
with path.open("x",encoding="utf-8") as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
output=json.dumps({"status":report["status"],"checks":len(checks),"failed":len(failed),"acceptance":pin(path),"after":R["after"]},ensure_ascii=False)
assert len((output+"\n").encode())<=6000
print(output)
raise SystemExit(2 if failed else 0)
