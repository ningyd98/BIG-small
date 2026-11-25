"""Produce an isolated, reproducible 130 mm development source overlay from its frozen parent."""
import hashlib
import json
import shutil
from pathlib import Path

PARENT = "5c09e38b82e09a8c52de407bee97775aca8b8a48b4d14a3bfc387ffd626fa212"
BASE = Path("experiments/results/g1-visibility-pose-repair-20261124/builds") / PARENT / "runtime-source"
OWNER = "src/cloud_edge_robot_arm/vision/owner_registration.py"
RUNTIME = "scripts/graduation/dynamic_vision.py"
READER = "scripts/graduation/g1_dual_pixel_readback.py"
SCORER = "scripts/graduation/g1_dual_batch_score.py"
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parent_tree(repo):
    return repo / BASE


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("source anchor is not unique: " + old[:90])
    return source.replace(old, new)


def adapt(path, source):
    if path == OWNER:
        sep = "class RegisteredPreparedStepBindingV2"
        before, _, later = source.partition(sep)
        later = replace_once(later, '        "created_at",\n', '        "development_grasp_binding_sha256",\n        "created_at",\n')
        later = replace_once(later, '        _sources(p["grounding_source_hashes"])',
                             '        _sha(p["development_grasp_binding_sha256"])\n        _sources(p["grounding_source_hashes"])')
        later = replace_once(later, '    source = requirement.original_step\n    step = source.model_copy(',
            '    source = requirement.original_step\n    from scripts.graduation.binding import resolve_registered_parameters\n'
            '    parameters, ticket_sha = resolve_registered_parameters(_resolved_parameters, source, original, online, inputs, policy)\n'
            '    step = source.model_copy(')
        later = replace_once(later, '"parameters": _resolved_parameters(source, original, online, inputs, policy)',
                             '"parameters": parameters')
        later = replace_once(later, '            "grounded_step": step.model_dump(mode="json"),',
                             '            "development_grasp_binding_sha256": ticket_sha,\n            "grounded_step": step.model_dump(mode="json"),')
        return before + sep + later
    if path == RUNTIME:
        source = replace_once(source, "        contract, step, binding, _, _ = registered_collection_step_v2(\n            self.original,",
                              "        from scripts.graduation.binding import issue_for_episode, BoundServoFeedback\n"
                              "        contract, step, binding, _, _ = issue_for_episode(\n            self,")
        source = replace_once(source, "            provider = OpenCVServoFeedback(\n                ref,",
                              "            provider = BoundServoFeedback(\n                self.grasp_attempt, binding, ref,")
        source = replace_once(source, '                skill=name,\n                initial_target=Pose.model_validate(target),\n', '')
        source = replace_once(source, '                verify_mujoco_calibration=True,\n', '')
        return replace_once(source, "                return MotionTarget(measured, previous.orientation_wxyz)",
                            "                return provider.motion_target(previous, measured)")
    if path == READER:
        return replace_once(source, '        per_id[str(marker)] = {\n', '        attachment = np.reshape(geometry["development_dual"]["markers"][str(marker)]["object_T_marker"], (4, 4))\n'
                            '        rotation = np.reshape(measure["rotation_marker_to_world"], (3, 3)) @ np.linalg.inv(attachment[:3, :3])\n'
                            '        per_id[str(marker)] = {\n            "rotation_object_to_world": rotation.ravel().tolist(),\n')
    if path == SCORER:
        source = replace_once(source, '    tracker, targets, previews = None, [], []', '    from scripts.graduation import binding_score\n'
                              '    issues = binding_score.verify_issues(audit, frames)\n    tracker, targets, previews = None, [], []')
        source = replace_once(source, '            expected = initial.copy()', '            binding_score.verify_sample(issues, skill, sample, f)\n'
                              '            expected = initial.copy()')
        return replace_once(source, '                expected += np.subtract(f["tcp_m"], ref["tcp_m"])',
                  '                expected += np.subtract(f["tcp_m"], ref["tcp_m"])\n'
                  '                expected += binding_score.offset_delta(issues[skill][0], ref, f)')
    raise ValueError("unknown source")


def create(repo, tree):
    parent = parent_tree(repo)
    if sha(parent / "runtime-build.json") != PARENT:
        raise ValueError("unexpected frozen parent source generation")
    lock = json.loads((parent / "runtime-build.json").read_text())
    files = dict(lock["runtime_files_sha256"])
    tree.mkdir(parents=True, exist_ok=False)
    for path, expected in files.items():
        source = parent / path
        if sha(source) != expected:
            raise ValueError("changed frozen input: " + path)
        out = tree / path
        out.parent.mkdir(parents=True, exist_ok=True)
        if path in (OWNER, RUNTIME, READER, SCORER):
            out.write_text(adapt(path, source.read_text()))
            files[path] = sha(out)
        else:
            shutil.copyfile(source, out)
    for name in ("binding.py", "binding_score.py"):
        path = "scripts/graduation/" + name
        shutil.copyfile(HERE / name, tree / path)
        files[path] = sha(tree / path)
    manifest = dict(parent_sha256=PARENT, plan_sha256="596158c29f9d43573a92c2be22a5b9db55e5d8b21f08cc8382e65e3d8b7ffb1a",
                    build_recipe_sha256=sha(Path(__file__)), files=files)
    (tree / "binding-generation.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return tree, files
