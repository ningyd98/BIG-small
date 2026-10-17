"""ROOT R285 finite bytes/text/hash gate; does not import or execute delivered sources."""
from pathlib import Path
import base64,hashlib,json,re,shlex,stat
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round285-p6-t2-new-test-generation-validation-continuation-20261017")
I=D/"implementation"
A=D.parent
checks=[]
def check(name,ok):checks.append({"check":name,"passed":bool(ok)})
def identity(q):return {k:q[k] for k in ("path","bytes","sha256")}
def pin(path,data=None):
 p=Path(path);b=p.read_bytes() if data is None else data
 return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def checked(q):
 p=Path(q["path"]);b=p.read_bytes()
 check("identity "+str(p),stat.S_ISREG(p.lstat().st_mode) and pin(p,b)==identity(q));return b
def load(q):return json.loads(checked(q))
def fixed(path,size,sha):return {"path":str(path),"bytes":size,"sha256":sha}
def full(row):
 b=base64.b64decode(row["base64"],validate=True)
 check("full physical/base64 "+row["original"]["path"],checked(row["archive"])==b and pin(row["original"]["path"],b)==identity(row["original"]));return b
def absent(path):
 p=Path(path);check("absence "+str(p),not p.exists() and not p.is_symlink())
def save(name,value):
 path=D/name
 with path.open("x",encoding="utf-8") as f:f.write(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+"\n")
 return pin(path)
def emit(value):
 text=json.dumps(value,ensure_ascii=False);assert len((text+"\n").encode())<=6000;print(text)
P=load(fixed(D/"plan.json",47877,"22983a42ecd12e188440b42a0491c059957e96998b546e769e3bd3ceaef0ffa0"))
O=load(fixed(D/"input-observation.json",97836,"3af0606bc3b09737f0c744ab7819a9fdfb94b32e7f516045ebd3a66218682508"))
S=load(fixed(D/"prerequisite-supplement.json",4166,"39b5cae7d0841f2c8901d7a30910018dd312840ecbdb96c4f064641b56db03b8"))
R=load(fixed(I/"change-report.json",12826,"64b483fe761d9eb8103bfc8d4c12b57e5d4689d749ea15f52c32236ae774ecaa"))
C=load(S["context_manifest"])
check("actual Astra33 and305",P["actual_model"]=="gpt-6-astra" and P["inputs"]==O["inputs"] and len(P["inputs"])==33 and O["check_count"]==len(O["checks"])==305 and all(q["passed"] for q in O["checks"]))
mapped={}
for row in C["changes"]:
 b=full(row["before"]);after=checked(row["after"])
 check("exact complete context generations and mode",checked(row["after_archive"])==after and row["after"]["path"]==row["before"]["original"]["path"] and all(Path(p).lstat().st_mode==row["mode"]==33204 for p in (row["after"]["path"],row["after_archive"]["path"],row["before"]["archive"]["path"])))
 mapped[row["after"]["path"]]=row
check("two context exact frozen original keys",len(mapped)==2 and [q["before"]["original"] for q in C["changes"]]==P["context_update"]["before_inputs"])
for q in P["inputs"]:
 if q["path"] in mapped:
  row=mapped[q["path"]];check("only typed context old identity",identity(q)==identity(row["before"]["original"]));checked({**identity(q),"path":row["before"]["archive"]["path"]})
 else:checked(q)
check("six supplement actual binding",S["input_count"]==len(S["inputs"])==6 and S["plan"]==pin(D/"plan.json") and S["observation"]==pin(D/"input-observation.json") and S["context_manifest"]==pin(D/"root-context-update.json"))
for q in S["inputs"]:checked(q)
M=load(P["before_manifest"])
check("three original source/test before records",len(M["records"])==3)
templates={}
for row in M["records"]:
 b=full(row);check("template current full bytes/modes",checked(row["original"])==b and Path(row["original"]["path"]).lstat().st_mode==Path(row["archive"]["path"]).lstat().st_mode==row["mode"]==33204)
 templates[Path(row["original"]["path"]).name]=b
check("source-only actual report",R["round"]=="R285" and R["status"]=="SOURCE_READY_STOP_FOR_ROOT_FULL_SOURCE_NATIVE_INPUT_ARGV_GATE" and R["new_roles_created"]==R["runtime_commands_executed"]==R["test_static_import_AST_compile_SQL_Git_commands"]==0 and R["product_test_observer_context_roles_modified"] is False and R["runtime_evidence"] is None and R["actual_resources"] is None and R["T2_complete"] is False)
X=load(R["source_index"]);Q=load(R["scope_proof"]);N=load(R["native"])
for k in ("candidate_scope_proof","runner_diff","plugin_diff","candidate_native","candidate_final_native","read_actuals"):checked(R[k])
check("two exact source interfaces",len(R["sources"])==len(X["sources"])==2 and X["target_before"]==Q["target_before"]==[None,None])
sources={}
for item,row in zip(R["sources"],X["sources"]):
 b=checked(item["pin"])
 check("complete source candidate/target/physical/base64/mode",b==checked(item["candidate"])==checked(item["physical"])==checked(row["candidate"])==checked(row["physical"])==base64.b64decode(row["base64"],validate=True) and identity(row)==item["pin"] and len(b.splitlines())==row["source_lines"]==item["lines"] and Path(row["path"]).lstat().st_mode==item["mode"]==row["mode"]==33204)
 sources["runner" if Path(row["path"]).name=="run-evidence.py" else "plugin"]=item["pin"]
check("exact reviewed final generation",sources["runner"]["sha256"]=="8f64d12e73dfb009fa4db4853a50587b054cf97c6d76a4233e672479d5c1d54e" and sources["plugin"]["sha256"]=="1989b1f3a6027e6601392e8e73bbbc50654dcb3ef8a0e13f8a3c36cd125cb25b")
new=checked(sources["runner"]);plugin=checked(sources["plugin"]);old=templates["run-evidence.py"];oldplugin=templates["r276_session_evidence.py"]
parts={};position=0
for row in Q["runner_portions"]:
 b=new[row["byte_start"]:row["byte_start"]+row["bytes"]]
 check("contiguous whole source portion "+row["name"],row["byte_start"]==position and len(b)==row["bytes"] and hashlib.sha256(b).hexdigest()==row["sha256"] and b==b"".join(new.splitlines(keepends=True)[row["first_line"]-1:row["last_line"]]))
 parts[row["name"]]=b;position+=row["bytes"]
check("nine portions whole reviewed source",position==len(new) and len(parts)==9 and X["runner_portions"]==Q["runner_portions"])
markers=[b"def require(",b"def command_paths(",b"def authority(",b"def preconditions(",b"def save_before(",b"def junit_observation(",b"def session_observations(",b"def main("]
bounds=[0]+[old.index(q) for q in markers]+[len(old)]
names=["header","common_prefix","command_paths_and_DB_pairs","authority","preconditions","save_before","JUnit_and_cases","session_consumer_and_behavior_resources","main"]
oldparts={name:old[bounds[n]:bounds[n+1]] for n,name in enumerate(names)}
h=oldparts["header"]
replacements=[
 (b"R276",b"R285"),
 (b'round276-p6-t2-first-session-invalidation-capture-20261017',b'round285-p6-t2-new-test-generation-validation-continuation-20261017'),
 (b'PARENT = ROUNDS / "round268-p6-t2-targeted-failure-evidence-20261017"',b'PARENT = ROUNDS / "round276-p6-t2-first-session-invalidation-capture-20261017"'),
 (b'R274 = ROUNDS / "round274-p6-t2-wait-fixture-clock-scope-20261017"\n',b'R274 = ROUNDS / "round274-p6-t2-wait-fixture-clock-scope-20261017"\nR281 = ROUNDS / "round281-p6-t2-post-expiry-session-denial-assertion-20261017"\n'),
 (b"bf3f11ceb390c316021714feffb54775d47bd2dcd5dc6f0ae59f9f8169a1c2a8",b"22983a42ecd12e188440b42a0491c059957e96998b546e769e3bd3ceaef0ffa0"),
 (b"418b7a91a16ff867c811fbaabf6aa577a3782145b51c9a4e3b737d07c6322623",b"3af0606bc3b09737f0c744ab7819a9fdfb94b32e7f516045ebd3a66218682508"),
 (b"9e1011333681dd85f92d302d995a28c0b28cfc8ee9fac259954fe97f66733374",b"39b5cae7d0841f2c8901d7a30910018dd312840ecbdb96c4f064641b56db03b8"),
 (b"ebf1e58187dc14fb607f8b6506284fd64532cbef1b41931740c216eba50367bb",b"193f45147160f52ba53956df506ddbc602b81f2248990eea604366a39e63ef13")]
for a,b in replacements:check("unique header literal "+a.decode(),h.count(a)==1);h=h.replace(a,b,1)
check("only explicit header binding delta",h==parts["header"])
check("common prefix only new provenance literal",parts["common_prefix"]==oldparts["common_prefix"].replace(b"This genuine new R276 diagnostic run only; old bytes not recovered",b"This genuine new R285 diagnostic run only; old bytes not recovered",1))
for name in ("command_paths_and_DB_pairs","preconditions","save_before","JUnit_and_cases","session_consumer_and_behavior_resources","main"):
 expected=oldparts[name].replace(b"R276",b"R285").replace(b"r276",b"r285")
 check("only exact section namespace "+name,expected==parts[name])
check("complete manually reviewed typed authority source",hashlib.sha256(parts["authority"]).hexdigest()=="1a347441a68db41ec640a903175519d81350cb4209713620309e71cb562d69d5")
def function(raw,name):
 start=raw.index(name);end=raw.find(b"\ndef ",start+len(name));return raw[start:len(raw) if end<0 else end+1]
for name in (b"def _t2_pin(",b"def _t2_cleanup(",b"def diagnostic_resources(",b"def _t2_index("):check("unchanged original helper "+name.decode(),function(old,name)==function(new,name))
defs=lambda b:re.findall(rb"^def ([A-Za-z_][A-Za-z_0-9]*)\(",b,re.M)
check("all original unique top-level functions",defs(old)==defs(new) and len(defs(new))==len(set(defs(new))))
expected=oldplugin.replace(b"round276-p6-t2-first-session-invalidation-capture-20261017",D.name.encode()).replace(b"R276",b"R285").replace(b"r276",b"r285").replace(replacements[4][0],replacements[4][1]).replace(replacements[7][0],replacements[7][1])
check("whole plugin only allowed identity/plan/test bindings",plugin==expected and len(plugin.splitlines())==454)
def native_add(stage):
 check("honest native actual "+stage["stage"],stage["tool"]=="tools.apply_patch" and stage["actual_tool_return"]=={} and all(stage[k] is None for k in ("numeric_exit","independent_stdout","independent_stderr")))
 lines=stage["arguments"].splitlines();check("exact native frame",lines[0]=="*** Begin Patch" and lines[-1]=="*** End Patch")
 i=1;targets=[]
 while i<len(lines)-1:
  check("Add only",lines[i].startswith("*** Add File: "))
  target=lines[i][14:];i+=1;body=[]
  while i<len(lines)-1 and lines[i].startswith("+"):body.append(lines[i][1:]);i+=1
  b=("\n".join(body)+"\n").encode()
  check("native whole Add reconstruction "+target,Path(target).read_bytes()==b)
  targets.append(target)
 return targets
check("two single target native implementation stages",len(N["stages"])==2)
native_targets=[]
for stage,proof in zip(N["stages"],Q["native_argument_archive_one_LF_proofs"]):
 targets=native_add(stage);native_targets+=targets;arg=stage["arguments"].encode()
 check("target did not exist before Add",stage["target_before"] is None and len(targets)==1)
 check("exact actual parameter and one LF archive",stage["stage"]==proof["stage"] and len(arg)==proof["actual_argument_utf8_bytes"] and hashlib.sha256(arg).hexdigest()==proof["actual_argument_sha256"] and not arg.endswith(b"\n") and checked(proof["archive"])==arg+b"\n")
check("only two intended implementation destinations",native_targets==[sources["runner"]["path"],sources["plugin"]["path"]])
CN=load(R["candidate_native"]);FN=load(R["candidate_final_native"])
for stage in CN["stages"]+[FN]:native_add(stage)
prep_pin=fixed(I/"source-preparation-actual-tool-returns.json",26707,"4663a7433d9a95c38ace21ccf560430adaa4c78c6d04d16de32a237dfa206403")
prep=load(prep_pin);reads=load(R["read_actuals"])
check("two preserved actual preparation steps and no runtime",len(prep["stages"])==2 and all(s["actual_tool_return"]["exit_code"]==0 and s["independent_stdout"] is s["independent_stderr"] is None for s in prep["stages"]) and prep["runtime_commands"]==prep["roles_created"]==prep["context_changed"]==0)
check("ten real bounded author reads",len(reads["reads"])==10 and all(s["actual_tool_return"]["exit_code"]==0 and not s["actual_tool_return"]["output"].startswith("Warning:") and len(s["actual_tool_return"]["output"].encode())<=40000 for s in reads["reads"]))
root_packet=load(fixed(D/"original-root-candidate-read-metadata-failure.json",113613,"b8f3ec76fa44bd9a6bffe92b2fc5051e49b34c5621e6d8b5cdf75d3160d3dd93"))
for row,(b,lo,hi) in zip(root_packet["reads"],[(new,1,450),(new,451,900),(new,901,1377),(plugin,1,454)]):
 actual=row["stored"]["actual"];block=b"".join(b.splitlines(keepends=True)[lo-1:hi])
 check("complete retained ROOT raw source read "+row["key"],actual["exit_code"]==0 and actual["output"].encode()==block and len(block)<=40000 and hi-lo+1<=600)
SX=load(P["authority_contract"]["container"]);prior=SX["authority_before"]
check("finite original27/211/68 authority",len(SX["sources"])==len(O["current_sources"])==27 and len(prior["protected"])==211 and len(prior["accepted_history_generations"])==68)
current={q["path"]:q for q in O["current_sources"]}
G=load(next(q for q in P["inputs"] if q["path"].endswith("/round281-p6-t2-post-expiry-session-denial-assertion-20261017/implementation/generation-manifest.json")))
BM=load(next(q for q in P["inputs"] if q["path"].endswith("/round281-p6-t2-post-expiry-session-denial-assertion-20261017/before/manifest.json")))
ebf=full(BM);now=checked(P["source_generation"]["current_test"])
check("full typed ebf1 to193f chain",checked(G["old"]["archive"])==ebf and identity(G["old"]["original"])==identity(BM["original"]) and checked(G["after"]["archive"])==now==base64.b64decode(G["after"]["base64"],validate=True) and identity(G["after"]["original"])==identity(P["source_generation"]["current_test"]))
ed=full(prior["test_generation"]["before"])
check("separate ed602 original",checked(prior["test_generation"]["after"])==ebf and ed!=ebf)
rp=next(q["pin"] for q in prior["input_records"] if q["pin"]["path"].endswith("/round274-p6-t2-wait-fixture-clock-scope-20261017/plan.json"))
R274=load(rp);expected=ed
for change in R274["exact_source_change"]["changes"]:
 oldtext=change["old"].encode();check("unique R274 edit",expected.count(oldtext)==1);expected=expected.replace(oldtext,change["new"].encode(),1)
check("exact five R274 transitions retained",len(R274["exact_source_change"]["changes"])==5 and expected==ebf)
for row in SX["sources"]:
 oldraw=checked(row["physical"]);actual=checked(current[row["path"]])
 check("full old physical/base64",oldraw==base64.b64decode(row["base64"],validate=True))
 check("exact current test or other26",oldraw==ebf and actual==now if row["path"]==P["source_generation"]["current_test"]["path"] else actual==oldraw)
 check("exact source mode",Path(row["path"]).lstat().st_mode==row["mode"]==current[row["path"]]["mode"])
for q in prior["protected"]:checked(q)
check("old35/90 bounds",len(prior["missing_registry35"])==35 and len(prior["old_absent_sidecars90"])==90)
for q in prior["missing_registry35"]:
 check("missing historical bytes remain unknown",q["current_bytes"] is q["current_sha256"] is q["hash_match"] is None);absent(q["original"]["path"])
for q in prior["old_absent_sidecars90"]:absent(q["path"])
for name,count in (("R242_R248",12),("R251",18)):
 rows=prior["old_retained_groups"][name];check("old group count",len(rows)==count)
 for row in rows:
  checked(row["pin"]);check("three old sidecars",len(row["sidecars"])==3)
  for side in row["sidecars"]:check("old sidecar declared absent",side["exists"] is side["is_symlink"] is False and side["pin"] is None);absent(side["path"])
def pairs(rows,count):
 check("exact pair count",len(rows)==count);present=missing=0
 for row in rows:
  check("raw retained original/archive",checked(row["pin"])==checked(row["archive"]));check("three retained sidecars",len(row["sidecars"])==3)
  for side in row["sidecars"]:
   check("sidecar no symlink",side["is_symlink"] is False)
   if side["exists"]:check("present full sidecar pair",checked(side["pin"])==checked(side["archive"]));present+=1
   else:check("absent pin null",side["pin"] is None);absent(side["path"]);missing+=1
 return present,missing
check("R25810 exact2present28absent",pairs(prior["R258_retained_DB_pairs"],10)==(2,28))
known={name:[q["record"] for q in O["known_database_records"] if q["group"]==name] for name in ("wait_memory_failure","dual_progress","R276_wait_memory")}
oldresult=load(next(q for q in P["inputs"] if q["path"].endswith("/round276-p6-t2-first-session-invalidation-capture-20261017/implementation/wait_memory/result.json")))
for name,count in (("wait_memory_failure",4),("dual_progress",2),("R276_wait_memory",4)):
 status=pairs(known[name],count)
 check("exact known DB record join",known[name]==(oldresult["new_retained_databases"] if name=="R276_wait_memory" else prior["R268_retained_DB_pairs"][name]))
 if name=="R276_wait_memory":check("R27612 sidecars absent",status==(0,12))
settled=load(next(q for q in P["inputs"] if q["path"].endswith("/round276-p6-t2-first-session-invalidation-capture-20261017/root-wait-memory-independent-acceptance.json")))
rootold=full(settled["root_before"])
authorraw={name:base64.b64decode(oldresult["known_author_generations"][name]["base64"],validate=True) for name in ("before","reserved","spent")}
for row in SX["control_before"]:
 b=full(row);path=row["original"]["path"]
 if path==O["R276_role_pins"]["ROOT"]["path"]:check("historical ROOT exact actual settlement before",identity(row["original"])==identity(settled["root_before"]["original"]) and b==rootold)
 elif path==O["R276_role_pins"]["AUTHOR"]["path"]:check("historical AUTHOR exact actual before",b==authorraw["before"] and identity(row["original"])==identity(oldresult["known_author_generations"]["before"]["pin"]))
 else:check("other stable old control",checked(row["original"])==b)
for role in ("ROOT","AUTHOR"):
 raw=checked(O["R276_role_pins"][role]);value=json.loads(raw)
 check("old memory spent no refund",value["commands"]["wait_memory"]["used"]==1 and value["commands"]["wait_memory"]["remaining"]==0 and value["commands"]["wait_memory"]["state"].startswith("SPENT"))
 for name in ("wait_sqlite","dual_first_invalidation"):check("old unused roles still held",value["commands"][name]["used"]==0 and value["commands"][name]["remaining"]==1)
 if role=="AUTHOR":check("old current AUTHOR actual spent",raw==authorraw["spent"])
roles={k:P["runner_contract"]["roles"][k] for k in ("ROOT","AUTHOR")}
for path in roles.values():absent(path)
for name,command in P["commands"].items():
 absent(command["output_directory"])
 check("new exact once "+name,(command["authorized"],command["used"],command["remaining"],command["limits"]["attempts"],command["limits"]["retries"])==(1,0,1,1,0))
 check("exact env-i literal transport "+name,shlex.split(command["tool_arguments"]["cmd"])==["env","-i"]+[k+"="+v for k,v in command["launcher_env"].items()]+command["launcher_argv"] and command["tool_arguments"]=={"cmd":"env -i "+" ".join(shlex.quote(k+"="+v) for k,v in command["launcher_env"].items())+" "+" ".join(shlex.quote(v) for v in command["launcher_argv"]),"workdir":command["cwd"],"yield_time_ms":10000,"max_output_tokens":1800} and command["env_inheritance"] is False)
 check("fixed bounds "+name,[command["limits"][k] for k in ("child_seconds","cleanup_total_seconds","TERM_grace_seconds","outer_total_seconds","outer_KILL_after_seconds","faulthandler_seconds")]==[600,15,5,900,15,540])
check("source-index finite authority joins",X["runtime"]==0 and len(X["input_records"])==33 and X["supplement_inputs"]==S["inputs"] and len(X["current_sources"])==27 and X["protected_count"]==211 and X["known_DB_records_count"]==10 and X["history_reaudited_as_current"] is False)
for name in ("source-gate.json","script-gate.json","root-final-source-acceptance.json","root-final-input-check.json"):absent(D/name)
failed=[q for q in checks if not q["passed"]]
report={"round":"R285","status":"ALL_FULL_SOURCE_NATIVE_INPUT_ARGV_CHECKS_PASSED" if not failed else "FAILED_STOP_ASTRA","checks":checks,"failed":failed,"checks_passed":len(checks)-len(failed),"current_sources":27,"protected":211,"history68_reaudited":False,"sources":sources,"runtime":0,"T2_complete":False}
inputpin=save("root-final-input-check.json",report)
if failed:emit({"status":"FAILED_STOP_ASTRA","failed":len(failed),"report":inputpin});raise SystemExit(2)
fixedinputs=[pin(D/"plan.json"),pin(D/"input-observation.json"),pin(D/"prerequisite-supplement.json"),pin(I/"change-report.json"),P["before_manifest"],S["context_manifest"],prep_pin,pin(__file__),pin(D/"root-final-gate-source-review.json"),pin(D/"root-role-helper-source-review.json"),pin(D/"root-create-and-reserve-roles.py"),inputpin,rp]
for q in P["inputs"]:fixedinputs.append(mapped[q["path"]]["after"] if q["path"] in mapped else identity(q))
fixedinputs+=S["inputs"]+[R[k] for k in ("source_index","scope_proof","candidate_scope_proof","runner_diff","plugin_diff","native","candidate_native","candidate_final_native","read_actuals")]
for row in M["records"]:fixedinputs.append(row["archive"])
for row in R["sources"]:fixedinputs+=[row["candidate"],row["physical"]]
D286=A/"round286-p6-t2-root-source-read-metadata-disposition-20261017"
fixedinputs+=[pin(D286/name) for name in ("plan.json","input-observation.json","root-disposition.json","step-report.md")]+[pin(D/"original-root-candidate-read-metadata-failure.json")]
unique={}
for q in fixedinputs:unique[(q["path"],q["bytes"],q["sha256"])]=identity(q)
for q in unique.values():checked(q)
SG={"round":"R285","status":"VERIFIED_SOURCE_ONLY","plan":pin(D/"plan.json"),"observation":pin(D/"input-observation.json"),"supplement":pin(D/"prerequisite-supplement.json"),"sources":sources,"input_check":inputpin,"native":R["native"],"context_manifest":S["context_manifest"],"fixed_inputs":list(unique.values()),"runtime_released":False,"T2_complete":False}
sgpin=save("source-gate.json",SG)
jgpin=save("script-gate.json",{"round":"R285","status":"VERIFIED_BY_ROOT","plan":SG["plan"],"source_gate":sgpin,"sources":sources,"commands":P["commands"],"role_files":roles,"reservation_directory":str(D/"root-reservations"),"runtime_released":False})
accept=save("root-final-source-acceptance.json",{"round":"R285","status":"FULL_SOURCE_NATIVE_INPUT_ARGV_ACCEPTED_NO_DISPATCH","checks_passed":len(checks),"source_gate":sgpin,"script_gate":jgpin,"input_check":inputpin,"native":R["native"],"sources":sources,"fixed_input_count":len(unique),"runtime":0,"T2_complete":False})
emit({"status":"FULL_SOURCE_NATIVE_INPUT_ARGV_ACCEPTED_NO_DISPATCH","checks":len(checks),"source_gate":sgpin,"script_gate":jgpin,"acceptance":accept,"fixed_inputs":len(unique)})
