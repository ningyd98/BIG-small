from pathlib import Path
import base64,difflib,hashlib,json
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round277-p6-t2-session-snapshot-worker-field-collision-20261017"); I=D/"implementation"; count=0
def pin(p):
 p=Path(p); b=p.read_bytes(); return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def checked(row, physical=None):
 global count
 b=Path(physical or row["path"]).read_bytes()
 assert len(b)==row["bytes"] and hashlib.sha256(b).hexdigest()==row["sha256"]
 count+=1
 return b
P=json.loads(checked({"path":str(D/"plan.json"),"bytes":11777,"sha256":"6fff34587879ccede65c2856f5cdd3acf60ad782dfbe73da5ef83db13457e32f"}))
M=json.loads(checked(P["full_before"]["manifest"])); old=checked(M["archive"])
for row in P["inputs"]: checked(row,M["archive"]["path"] if row==M["original"] else None)
assert old==base64.b64decode(M["base64"],validate=True)
C=P["scope"]["exact_replacement"]; after=old.replace(C["old"].encode(),C["new"].encode(),1)
assert old.count(C["old"].encode())==1 and len(after)==20953 and hashlib.sha256(after).hexdigest()==C["expected_after_sha256"]
for path in (M["original"]["path"],str(I/"prepared-r276-session-evidence-source.txt"),str(I/"after-r276_session_evidence.py")):
 assert Path(path).read_bytes()==after and Path(path).lstat().st_mode==M["mode"]==33204
R=json.loads(checked({"path":str(I/"change-report.json"),"bytes":67790,"sha256":"1f6d9b6f732b394f018210b047ddd75ed575409b2888f33318b5f66d7f30eee5"}))
assert R["generation"]["before"]==M
G=R["generation"]["after"]
assert checked(G["original"])==checked(G["archive"])==base64.b64decode(G["base64"],validate=True)==after
N=json.loads(checked({"path":str(I/"actual-plugin-native-tool-return.json"),"bytes":7611,"sha256":"83d1b52a3847b4d7e8a0b00bdd16a354c371348bcb493792f7f448bcd47f19d6"}))
assert N["actual_tool_return"]=={} and all(N[k] is None for k in ("numeric_exit","independent_stdout","independent_stderr"))
diff="".join(difflib.unified_diff(old.decode().splitlines(keepends=True),after.decode().splitlines(keepends=True),fromfile=M["original"]["path"],tofile=str(I/"prepared-r276-session-evidence-source.txt")))
assert diff==(I/"limited.diff").read_text()
patch="*** Begin Patch\n*** Update File: "+M["original"]["path"]+"\n"+"".join("@@\n" if s.startswith("@@ ") else s for s in diff.splitlines(keepends=True)[2:])+"*** End Patch"
assert N["arguments"]==patch==(I/"plugin-correction.native.patch").read_text()
A=json.loads(checked(next(x for x in P["inputs"] if x["path"].endswith("/plugin-native-tool-returns.json"))))
native_stages=[]
for s in A["stages"]:
 lines=s["arguments"].splitlines()
 assert lines[0]=="*** Begin Patch" and lines[1].startswith("*** Add File: ") and lines[-1]=="*** End Patch"
 assert all(x.startswith("+") for x in lines[2:-1]) and s["actual_tool_return"]=={}
 native_path=lines[1][14:]
 body=("\n".join(x[1:] for x in lines[2:-1])+"\n").encode()
 physical=M["archive"]["path"] if native_path==M["original"]["path"] else native_path
 assert body==Path(physical).read_bytes()
 native_stages.append({"id":s["id"],"logical_path":native_path,"physical":pin(physical)})
assert len(native_stages)==3 and native_stages[-1]["physical"]["sha256"]==M["original"]["sha256"]
for k in ("candidate","current_plugin","after_archive","native_receipt","native_patch","limited_diff"): checked(R[k])
assert R["runtime_executed"] is False and R["roles_created_or_changed"] is False and R["STATE_PHASE_changed"] is False and R["new_budget"]==0 and R["T2_complete"] is False
result={"round":"R277","status":"ROOT_SOURCE_ACCEPTED_BEHAVIOR_UNVERIFIED","identity_checks":count,"native_Add_stages":native_stages,"native_Update_exact":True,"before":M["original"],"physical_before":M["archive"],"after":G["original"],"physical_after":G["archive"],"consumer":"Pending R278 runner: use worker_object_id int/null and preserve worker_id native primitive; no fallback.","runtime_released":0,"T2_complete":False}
out=D/"root-independent-source-acceptance.json"; out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"status":result["status"],"identity_checks":count,"acceptance":pin(out)},ensure_ascii=False))
