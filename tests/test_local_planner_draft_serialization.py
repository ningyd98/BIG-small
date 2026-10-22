"""R306: exercise the actual local transition draft expression without lease authority."""

import ast
import copy
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cloud_edge_robot_arm.cloud.planning.models import PlannerDraft, SceneSummary


def test_local_transition_draft_json_payload():
    # Reverting the product expression to dataclasses.asdict must fail for the
    # real PlannerDraft model. This selects the expression used by _transition,
    # rather than repeating the replacement expression as the tested code.
    path = Path(__file__).resolve().parents[1] / "src/cloud_edge_robot_arm/vision/worker_runtime.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    classes = [node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "VisualWorkerRuntime"]
    assert len(classes) == 1
    methods = [node for node in classes[0].body
               if isinstance(node, ast.FunctionDef) and node.name == "_transition"]
    assert len(methods) == 1
    local = [node for node in methods[0].body
             if isinstance(node, ast.If) and isinstance(node.test, ast.Attribute)
             and isinstance(node.test.value, ast.Name) and node.test.value.id == "self"
             and node.test.attr == "_local_mode"]
    assert len(local) == 1
    bodies = [node.value for node in local[0].body
              if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)
              and any(isinstance(target, ast.Name) and target.id == "body"
                      for target in node.targets)]
    assert len(bodies) == 1
    expressions = [value for key, value in zip(bodies[0].keys, bodies[0].values)
                   if isinstance(key, ast.Constant) and key.value == "draft"]
    assert len(expressions) == 1
    code = compile(ast.Expression(body=expressions[0]), str(path), "eval")

    def serialize(draft):
        return eval(code, {"__builtins__": {}, "asdict": asdict}, {"draft": draft})

    assert serialize(None) is None
    sentinel = PlannerDraft(raw_text="request another observation",
                            parsed_json={"_sentinel": "REQUEST_MORE_OBSERVATION"})
    assert serialize(sentinel) == {
        "raw_text": "request another observation",
        "parsed_json": {"_sentinel": "REQUEST_MORE_OBSERVATION"},
        "parse_error": None, "observed_scene": None, "observation_evidence": {},
    }

    at = datetime(2026, 10, 22, 9, 30, tzinfo=timezone(timedelta(hours=8)))
    scene = SceneSummary(
        scene_version=7, updated_at=at,
        objects=[{"object_id": "cube", "object_class": "red_cube",
                  "pose": {"x": 0.1, "y": 0.2, "z": 0.3},
                  "pose_confidence": 0.9, "region_id": "target"}],
        regions=[{"region_id": "target", "center": {"x": 0.4, "y": 0.5, "z": 0.6},
                  "radius_m": 0.08}],
        obstacles=[{"kind": "wall", "points": [1, 2]}],
        scene_confidence=0.8, robot_state={"connected": True},
    )
    draft = PlannerDraft(
        raw_text="完整模型", parsed_json={"steps": [{"id": "inspect"}]},
        parse_error="diagnostic retained", observed_scene=scene,
        observation_evidence={"nested": {"captured_at": at, "tags": ["source"]}},
    )
    original = copy.deepcopy(draft.model_dump(mode="python"))
    expected = {
        "raw_text": "完整模型", "parsed_json": {"steps": [{"id": "inspect"}]},
        "parse_error": "diagnostic retained",
        "observed_scene": {
            "scene_version": 7, "updated_at": "2026-10-22T09:30:00+08:00",
            "objects": [{"object_id": "cube", "object_class": "red_cube",
                         "pose": {"x": 0.1, "y": 0.2, "z": 0.3},
                         "pose_confidence": 0.9, "region_id": "target"}],
            "regions": [{"region_id": "target",
                         "center": {"x": 0.4, "y": 0.5, "z": 0.6},
                         "radius_m": 0.08}],
            "obstacles": [{"kind": "wall", "points": [1, 2]}],
            "scene_confidence": 0.8, "robot_state": {"connected": True},
        },
        "observation_evidence": {
            "nested": {"captured_at": "2026-10-22T09:30:00+08:00", "tags": ["source"]}},
    }
    payload = serialize(draft)
    assert payload == expected
    wire = json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    restored = PlannerDraft.model_validate(wire)
    assert restored.observed_scene.updated_at == at
    assert restored.model_dump(mode="json") == expected
    assert serialize(sentinel) == sentinel.model_dump(mode="json")
    payload["parsed_json"]["steps"].append({"id": "changed"})
    payload["observed_scene"]["objects"][0]["pose"]["x"] = 99
    payload["observation_evidence"]["nested"]["tags"].append("changed")
    assert draft.model_dump(mode="python") == original
    for unsupported in ({"raw_text": "arbitrary mapping"}, object()):
        with pytest.raises(AttributeError):
            serialize(unsupported)
