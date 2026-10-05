"""Independent remaining reference kinds and rehashed output probes; no execution."""
from dataclasses import asdict, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import hashlib
import json

from tests.test_native_references import sample
from cloud_edge_robot_arm.vision.native_references import resolve_native_reference, validate_native_reference
from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry

results = []
with TemporaryDirectory(prefix='ced-native-ref-independent-') as temp:
    for skill in ('MOVE_ABOVE', 'RETREAT'):
        directory = Path(temp) / skill
        directory.mkdir()
        inputs = sample(directory, skill)
        reference = resolve_native_reference(**inputs)
        expected_kind = 'OBJECT_CONTACT' if skill == 'MOVE_ABOVE' else 'FIXED_WORLD_TCP_GOAL'
        assert reference.kind == expected_kind
        assert reference.endpoint_xyz == (0.45, 0.0, 0.16)
        assert reference.fixed_goal_coordinate_invariant == (skill == 'RETREAT')
        received = {}
        def capture(*args, **kwargs):
            received.update(kwargs)
        robot = SimpleNamespace(move_above=capture, retreat=capture)
        definition = SkillRegistry.default().definition_for(inputs['step'].skill)
        definition.handler(robot, definition.validate(inputs['resolved'].parameters), inputs['resolved'].timeout_ms)
        assert tuple(received['resolved_target'].model_dump().values()) == reference.endpoint_xyz
        assert received['timeout_ms'] == 10000
        validate_native_reference(reference, **inputs)
        forged = replace(reference, endpoint_xyz=(99.0, 99.0, 99.0))
        fields = asdict(forged)
        fields.pop('reference_digest')
        digest = hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        forged = replace(forged, reference_digest=digest)
        try:
            validate_native_reference(forged, **inputs)
        except ValueError:
            pass
        else:
            raise AssertionError('rehashed endpoint substitution accepted')
        results.append({'skill':skill,'real_registry_endpoint_forwarding':'PASS','rehashed_endpoint_substitution':'REJECTED','native_admission':False})
print(json.dumps({'scope':'SOFTWARE_ONLY_NO_PHYSICS_OR_RENDERING','results':results}, indent=2))
