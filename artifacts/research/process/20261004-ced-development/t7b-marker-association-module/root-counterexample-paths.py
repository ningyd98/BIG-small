from pathlib import Path
from dataclasses import replace
import hashlib
import importlib.util
import json
import tempfile
from cloud_edge_robot_arm.vision.marker_association import load_marker_registration
spec = importlib.util.spec_from_file_location("marker_tests", Path("tests/test_marker_association.py"))
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)
module, observation, registration, context = t.inputs()
probe_root = Path(tempfile.mkdtemp(prefix="marker-root-symlink-"))
link = probe_root / "linked-source-root"
link.symlink_to(t.ROOT, target_is_directory=True)
changed = replace(registration, root=link)
answer = module.replay_marker_target_development(observation, changed, context)
config_via_parent_link = link / "configs/research/ced_marker_registration_v1.yaml"
try:
    loaded = load_marker_registration(config_via_parent_link, expected_registry_sha256=hashlib.sha256(t.CONFIG.read_bytes()).hexdigest(), root=t.ROOT)
    loader = {"accepted": True, "same_digest": loaded.digest() == registration.digest()}
except ValueError:
    loader = {"accepted": False}
print(json.dumps({"symlink_root_sources_valid": changed.sources_valid(), "symlink_root_status": answer.status, "symlink_registry_parent": loader, "admission": answer.admission_status, "whole_identity": answer.whole_target_identity_status}, indent=2))
