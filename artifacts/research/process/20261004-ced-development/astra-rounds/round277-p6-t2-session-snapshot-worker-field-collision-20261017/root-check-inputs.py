from pathlib import Path
import hashlib,json,base64
D=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round277-p6-t2-session-snapshot-worker-field-collision-20261017")
checks=0
def checked(row):
 global checks
 p=Path(row["path"]); b=p.read_bytes()
 assert len(b)==row["bytes"] and hashlib.sha256(b).hexdigest()==row["sha256"]
 checks+=1
 return b
P=json.loads(checked({"path":str(D/"plan.json"),"bytes":11777,"sha256":"6fff34587879ccede65c2856f5cdd3acf60ad782dfbe73da5ef83db13457e32f"}))
O=json.loads(checked(P["input_observation"]))
assert P["actual_model"]==O["actual_model"]=="gpt-6-astra" and P["inputs"]==O["inputs"] and len(P["inputs"])==15
for row in P["inputs"]: checked(row)
M=json.loads(checked(P["full_before"]["manifest"]))
b=checked(M["original"])
assert b==checked(M["archive"])==checked(P["full_before"]["physical"])==base64.b64decode(M["base64"],validate=True)
assert Path(M["original"]["path"]).lstat().st_mode==Path(M["archive"]["path"]).lstat().st_mode==M["mode"]==33204
C=P["scope"]["exact_replacement"]; old,new=C["old"].encode(),C["new"].encode()
assert b.count(old)==1 and b.count(new)==0
after=b.replace(old,new,1)
assert len(after)==C["expected_after_bytes"]==20953 and hashlib.sha256(after).hexdigest()==C["expected_after_sha256"]=="48e4c9da3e70ef370d0c2fb3618cdac468e0286ac23ca4d8f97c0dbbbfb7517a"
result={"round":"R277","status":"ROOT_INPUT_AND_UNIQUE_SOURCE_SCOPE_ACCEPTED","checks":checks,"before":M["original"],"derived_after":{"bytes":len(after),"sha256":hashlib.sha256(after).hexdigest()},"runtime_released":0,"T2_complete":False}
p=D/"root-input-review.json"; p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
r=p.read_bytes(); print(json.dumps({"status":result["status"],"checks":checks,"report":{"path":str(p),"bytes":len(r),"sha256":hashlib.sha256(r).hexdigest()}},ensure_ascii=False))
