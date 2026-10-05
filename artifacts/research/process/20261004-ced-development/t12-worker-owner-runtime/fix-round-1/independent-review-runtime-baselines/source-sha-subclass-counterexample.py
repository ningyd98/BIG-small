from pathlib import Path
import hashlib,json,tempfile
from cloud_edge_robot_arm.vision.worker_owner import pin_worker_source_inventory

class PermissiveHash(str):
    def __eq__(self,other):return True
    def __ne__(self,other):return False
    __hash__=str.__hash__

root=Path(tempfile.mkdtemp(prefix="worker-owner-sha-subclass-"))
(root/"source.py").write_text("VALUE=1\n")
actual=hashlib.sha256((root/"source.py").read_bytes()).hexdigest()
wrong="f"*64
try:
    pin_worker_source_inventory(root,{"source.py":wrong},required_paths={"source.py"})
except ValueError as error:control=str(error)
else:raise AssertionError("plain wrong hash control accepted")
try:
    pinned=pin_worker_source_inventory(root,{"source.py":PermissiveHash(wrong)},required_paths={"source.py"})
except (ValueError,TypeError) as error:
    outcome={"status":"REJECTED","reason":str(error)}
else:
    outcome={"status":"ACCEPTED_WRONG_SOURCE_HASH","returned_value":str(pinned["source.py"]),"returned_type":type(pinned["source.py"]).__name__}
print(json.dumps({"scope":"SOFTWARE_ONLY","control":control,"actual_sha256":actual,"wrong_sha256":wrong,"outcome":outcome,"source_bytes_unchanged":True,"actual_authority":False},indent=2))
