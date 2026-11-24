"""Exact-source edit recipe for the isolated development runtime's visual inputs."""

from __future__ import annotations

import hashlib

VISION = "src/cloud_edge_robot_arm/vision/"
GROUNDING = "src/cloud_edge_robot_arm/research/native_collection_grounding.py"
TRACKING = VISION + "registered_object_tracking.py"
SOURCE_SHA256 = {
    VISION
    + "marker_families.py": "93fe11e893b3d9caeb0d891e60ad46d9c26ce13b0c88357b5e4751c389c317e1",
    VISION
    + "native_calibration.py": "c6b7cec347258b3144d226484465d835b0927ffaadb4c7e50b28a07f85aed430",
    VISION
    + "registered_objects.py": "279e1d4520508e458fea1932aa877a26f5e9d4a5a7050692c410ddf758ae5ff4",
    TRACKING: "537705727cbaa4aaad6b89d54d0494989cb21b1df01afde63cb073a7f6523a40",
    VISION
    + "owner_registration.py": "17ccc6ea0c6e3095e77a37880b4fcbc7448eef88ecf94813369e5daaff28a43a",
    VISION + "servo.py": "5532047540e1ae2871031a0df24e12fa533c52f2c355681d80858b6af6f297e2",
    GROUNDING: "720a999f2e7b349eca2adad055fd69eb31e634c013aa8dee3cf4c208ac188204",
}


def adapt_source(path, baseline_bytes):
    path = str(path)
    if path not in SOURCE_SHA256:
        raise ValueError("source outside the isolated dual visual overlay")
    if hashlib.sha256(baseline_bytes).hexdigest() != SOURCE_SHA256[path]:
        raise ValueError("baseline source SHA differs for " + path)
    source = baseline_bytes.decode("utf-8")
    before = ""

    def change(needle, replacement):
        nonlocal source
        if source.count(needle) != 1:
            raise ValueError("non-unique development source anchor in " + path)
        source = source.replace(needle, replacement)

    def insert(needle, prefix):
        change(needle, prefix + needle)

    # No import of an execution controller. Only the observer is imported lazily
    # inside a dual branch, including when this patch is used for the +Y arm.
    after_import = "from __future__ import annotations\n"
    change(
        after_import, after_import + "\nfrom scripts.graduation import g1_dual_asset as _g1_dual\n"
    )
    if path == VISION + "marker_families.py":
        insert(
            "    if type(family_id) is not str or family_id not in _FAMILIES:\n",
            "    if type(family_id) is str and family_id == _g1_dual.FAMILY:\n"
            "        return _g1_dual.family()\n",
        )
        insert(
            '    pose = data.get("pose_marker", {})\n',
            "    if _g1_dual.matches_identity(data):\n"
            "        _g1_dual.validate_geometry(data)\n"
            "        return _g1_dual.family()\n",
        )
    elif path == VISION + "native_calibration.py":
        insert(
            '        if set(data) not in (keys, keys | {"marker_family"}) or (\n',
            "        if _g1_dual.matches_identity(data):\n"
            "            _g1_dual.validate_geometry(data)\n"
            '            keys.add("development_dual")\n',
        )
        insert(
            "        if self.marker_family_id in (PREPARE_ONLY_FAMILY, "
            "SIDE_PREPARE_ONLY_FAMILY):\n",
            "        if self.marker_family_id == _g1_dual.FAMILY:\n"
            "            _g1_dual.validate_asset(root)\n"
            "            return\n",
        )
    elif path == VISION + "registered_objects.py":
        insert(
            '    options = {} if corner_refinement == "NONE" else '
            '{"corner_refinement": corner_refinement}\n',
            "    if scope.marker_family_id == _g1_dual.FAMILY:\n"
            "        from scripts.graduation.g1_dual_observer import derive\n"
            "        return derive(current, payload, provenance)\n",
        )
    elif path == TRACKING:
        insert(
            "        self._source_hashes = dict(\n",
            "        if self._registration.marker_family_id == _g1_dual.FAMILY:\n"
            "            self._required_paths |= _g1_dual.check_source_binding(\n"
            "                payload, source_hashes)\n",
        )
        change(
            "            marker_registration_hash=self._registration.pose_marker.digest(),\n",
            "            marker_registration_hash=(geometry.marker_registration_hash\n"
            "                if geometry is not None and\n"
            "                self._registration.marker_family_id == _g1_dual.FAMILY\n"
            "                else self._registration.pose_marker.digest()),\n",
        )
    elif path == GROUNDING:
        insert(
            "    NativeGeometryRegistration(geometry).validate_asset(ROOT)\n",
            "    if family.family_id == _g1_dual.FAMILY:\n"
            "        complete = _g1_dual.geometry_descriptor()\n"
            '        common = {k: v for k, v in complete.items() if k != "development_dual"}\n'
            "        if geometry != common:\n"
            '            raise ValueError("runtime camera, rigid geometry or asset differs")\n'
            "        geometry = complete\n",
        )
        change(
            '    if len(boxes) != 38 or len({b["name"] for b in boxes}) != 38:\n',
            "    if registration.marker_family_id == _g1_dual.FAMILY:\n"
            "        _g1_dual.check_source_binding(data, sources)\n"
            "        expected_names = _g1_dual.box_names()\n"
            "        if len(boxes) != len(expected_names) or "
            '{b["name"] for b in boxes} != expected_names:\n'
            '            raise ValueError("complete dual cube, plates, bridges and ink required")\n'
            '    elif len(boxes) != 38 or len({b["name"] for b in boxes}) != 38:\n',
        )
    elif path == VISION + "owner_registration.py":
        # Restrict to the actual step V2 consumer. The V1 signature/identity rule remains original.
        before, start, source = source.partition("class RegisteredGroundingFrameInputsV2")
        if not start:
            raise ValueError("registered V2 owner missing")
        before += start
        change(
            "            or geometry.marker_estimate.observed_marker_ids\n"
            '            != (reg.to_payload()["pose_marker"]["marker_id"],)\n',
            "            or (not _g1_dual_owner(obs, reg, geometry)\n"
            "                if reg.marker_family_id == _g1_dual.FAMILY\n"
            "                else geometry.marker_estimate.observed_marker_ids\n"
            '                != (reg.to_payload()["pose_marker"]["marker_id"],))\n',
        )
        insert(
            "        from dataclasses import asdict\n",
            "        from scripts.graduation.g1_dual_observer import (\n"
            "            matches_current_owner as _g1_dual_owner,\n"
            "        )\n",
        )
    elif path == VISION + "servo.py":
        insert(
            "    family = marker_family(family_id)\n",
            "    if family_id == _g1_dual.FAMILY:\n"
            "        from scripts.graduation.g1_dual_observer import servo_measure\n"
            "        return servo_measure(observation, diagnostics)\n",
        )
        insert(
            "        grasp, estimate = measure_registered_marker_grasp(\n",
            "        if self.marker_family_id == _g1_dual.FAMILY:\n"
            "            diagnostics = {}\n"
            "            grasp, estimate = measure_registered_marker_grasp(\n"
            "                observation, self.marker_family_id, diagnostics=diagnostics)\n"
            "            self._development_dual_measurement = {k: diagnostics[k] for k in (\n"
            '                "frame_id", "checksum", "observed_ids", "usable_ids", "selected_id",\n'
            '                "target_disagreement_m", "grasp_world_m",\n'
            '                "registration_id", "asset_sha256")}\n'
            "            if grasp is not None:\n"
            "                self._observed_marker = estimate\n"
            "            return grasp\n",
        )
        insert(
            '            **({"region_support": region_support} '
            "if region_support is not None else {}),\n",
            '            **({"development_dual_marker": self._development_dual_measurement}\n'
            "               if self.marker_family_id == _g1_dual.FAMILY else {}),\n",
        )
    return (before + source).encode("utf-8")
