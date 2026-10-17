from pathlib import Path
import hashlib,json,base64
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round279-p6-t2-source-read-display-framing-disposition-20261017");count=0
def pin(p):
 p=Path(p);b=p.read_bytes();return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def checked(q):
 global count
 b=Path(q["path"]).read_bytes();assert len(b)==q["bytes"] and hashlib.sha256(b).hexdigest()==q["sha256"];count+=1;return b
P=json.loads(checked({"path":str(D/"plan.json"),"bytes":14967,"sha256":"219c43fac9f9fae43b7c0438617c3edb25d927974227f6e371b7b70cef63ff0d"}))
O=json.loads(checked({"path":P["observation_path"],"bytes":10023,"sha256":"bf601492528991b5d88e37fbd06ccf334b15b94ab4da840f2aa746291bd5906d"}))
assert P["inputs"]==O["inputs"] and len(P["inputs"])==14 and P["actual_model"]==O["actual_model"]=="gpt-6-astra"
for q in P["inputs"]:checked(q)
F=json.loads(checked(P["problem"]["evidence"]))
assert F["actual_tool_return"]["chunk_id"]=="bb4b65" and F["actual_tool_return"]["exit_code"]==0 and F["actual_tool_return"]["original_token_count"]==53480
assert F["actual_tool_return"]["output"].startswith("Warning: truncated output")
assert "SyntaxError" in F["outer_V8_error"]["text"] and F["outer_V8_error"]["numeric_exit"] is None
assert F["facts"]["candidate_writes"]==F["facts"]["runner_native_calls"]==F["facts"]["control_writes"]==F["facts"]["product_or_test_runtime"]==0
M=json.loads(checked(next(x for x in P["inputs"] if x["path"].endswith("/draft-before-manifest.json"))))
for row in M["drafts"]:
 assert checked(row["original"])==checked(row["physical"])==base64.b64decode(row["base64"],validate=True)
 assert Path(row["original"]["path"]).lstat().st_mode==Path(row["physical"]["path"]).lstat().st_mode==row["mode"]==33204
ranges=P["physical_read_contract"]["allowed_source_ranges"];assert ranges==O["segments"] and len(ranges)==6
for q in ranges:
 full=checked(next(x for x in P["inputs"] if x["path"]==q["path"]))
 lines=full.splitlines(keepends=True);lo,hi=q["first_line_1based"],q["last_line_inclusive"]
 assert 1<=lo<=hi<=len(lines)
 block=b"".join(lines[lo-1:hi])
 assert hi-lo+1==q["source_lines"]<=600 and len(block)==q["utf8_bytes"]<=40000 and hashlib.sha256(block).hexdigest()==q["sha256"]
 block.decode("utf-8")
D277=D.parent/"round277-p6-t2-session-snapshot-worker-field-collision-20261017"
A=json.loads(checked(next(x for x in P["inputs"] if x["path"]==str(D277/"root-independent-source-acceptance.json"))))
assert checked(A["after"])==checked(A["physical_after"])
R278=json.loads(checked(next(x for x in P["inputs"] if x["path"].endswith("round278-p6-t2-runner-main-builder-boundary-disposition-20261017/plan.json"))))
assert not Path(R278["scope"]["target"]).exists()
r={"round":"R279","status":"ROOT_METADATA_TRANSPORT_DISPOSITION_ACCEPTED","identity_checks":count,"nested_read_exit":0,"outer_parse_failed":True,"four_physical_drafts_base64_modes":True,"six_ranges_exact":True,"current_plugin":A["after"],"runtime_released":0,"T2_complete":False}
out=D/"root-input-review.json";out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"status":r["status"],"identity_checks":count,"report":pin(out)},ensure_ascii=False))
