from pathlib import Path
import json,hashlib,base64
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round278-p6-t2-runner-main-builder-boundary-disposition-20261017"); count=0
def pin(p):
 p=Path(p);b=p.read_bytes();return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def checked(row):
 global count
 b=Path(row["path"]).read_bytes();assert len(b)==row["bytes"] and hashlib.sha256(b).hexdigest()==row["sha256"];count+=1;return b
P=json.loads(checked({"path":str(D/"plan.json"),"bytes":14832,"sha256":"ac7025a0b3059dc49f0c27c9b9a5d66ce03f0a3ec339573ef62db8d57998cd37"}))
O=json.loads(checked(P["input_observation"]))
assert P["actual_model"]==O["actual_model"]=="gpt-6-astra" and P["inputs"]==O["inputs"] and len(P["inputs"])==15
for row in P["inputs"]: checked(row)
M=json.loads(checked(P["full_draft_before"]))
assert len(M["drafts"])==4 and M["missing_partial_main"] is None and M["final_runner_before"] is None
for row in M["drafts"]:
 assert checked(row["original"])==checked(row["physical"])==base64.b64decode(row["base64"],validate=True)
 assert Path(row["original"]["path"]).lstat().st_mode==Path(row["physical"]["path"]).lstat().st_mode==row["mode"]==33204
main=(D/"author-drafts/original-template-main.txt").read_text()
template=checked(M["template_runner"]).decode()
assert template.count("def main():")==1 and main==template[template.index("def main():"):]
line=P["construction_contract"]["boundary"]["actual_line"]
assert main.splitlines()[238]==line and len(line)-len(line.lstrip(" "))==27 and main.count(line)==1 and main.count(" "+line)==0
raw=json.loads((D/"original-main-builder-failure.json").read_bytes())
assert (" "+line) in raw["original_V8_JS_argument"] and raw["boundary"]["partial_main_available"] is False
assert raw["actual_tool_return"] is None and raw["numeric_exit"] is None and raw["runtime_executed"] is False
assert not Path(P["scope"]["target"]).exists()
D277=D.parent/"round277-p6-t2-session-snapshot-worker-field-collision-20261017"
accepted=json.loads(checked({"path":str(D277/"root-independent-source-acceptance.json"),"bytes":3700,"sha256":"c5de6c4faa1209dfbd5a055fc84d905f4b9429415d1140af30a82c37e6be6364"}))
assert accepted["status"]=="ROOT_SOURCE_ACCEPTED_BEHAVIOR_UNVERIFIED" and checked(accepted["after"])==checked(accepted["physical_after"])
result={"round":"R278","status":"ROOT_PHYSICAL_DRAFT_AND_METADATA_DISPOSITION_ACCEPTED","identity_checks":count,"original_28_vs_actual27_unique_boundary":True,"full_original_draft_bytes_base64_mode":True,"R277_source_accepted":accepted["after"],"runner_before":None,"runtime_released":0,"T2_complete":False}
p=D/"root-input-review.json";p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"status":result["status"],"identity_checks":count,"report":pin(p)},ensure_ascii=False))
