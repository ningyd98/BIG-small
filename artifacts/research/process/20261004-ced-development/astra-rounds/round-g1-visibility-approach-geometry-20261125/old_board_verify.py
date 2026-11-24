"""Verify the old-board pixel annotations with native sensor bytes and independent camera rays."""

import base64
import gzip
import hashlib
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROUND = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(repo):
    summary = json.loads((ROUND / "old-board-observation.public.json").read_bytes())
    table = ROUND / "old-board-pixels.public.json.gz"
    archive = repo / summary["private_capture"]
    if sha(table) != summary["detail_sha256"] or sha(archive) != summary["private_capture_sha256"]:
        raise ValueError("changed image evidence")
    seals = json.loads(archive.read_bytes())["frames"]
    data = json.loads(gzip.decompress(table.read_bytes()))["frames"]
    checks = Counter()
    aliases = {}
    for key, r in data.items():
        for name, h in r["source_sha256"].items():
            if sha(repo / name) != h:
                raise ValueError(name)
        p = repo / summary["per_anchor"][key]["frame_ref"]
        frame = json.loads(p.read_bytes())
        if sha(p) != r["frame_sha256"] or r["frame_id"] != frame["frame_id"]:
            raise ValueError(key)
        fy0 = frame["intrinsics"]
        fx, fy, cx, cy = fy0
        h, w = frame["height"], frame["width"]
        rgb = np.asarray(Image.open(io.BytesIO(base64.b64decode(frame["rgb_png_base64"]))))
        depth = np.frombuffer(base64.b64decode(frame["depth_float32_base64"]), "<f4").reshape(h, w)
        camera = np.reshape(frame["camera_to_world"], (4, 4))
        obj = next(
            s
            for s in json.loads((p.parents[1] / "offline-truth.json").read_bytes())["samples"]
            if s["physics_step"] == r["physics_step"]
        )
        rot = np.reshape(obj["object_geom_rotation_row_major"], (3, 3))
        allocation = json.loads((p.parents[2] / "allocation.json").read_bytes())["geometry"]
        sides = allocation.get("development_dual", {}).get("markers") or {
            "7": {"object_T_marker": allocation["marker_to_object"]}
        }
        for code, mark in sides.items():
            transform = np.reshape(mark["object_T_marker"], (4, 4))
            world_center = rot @ transform[:3, 3] + obj["object_geom_position_m"]
            axes = rot @ transform[:3, :3]
            normal = axes[:, 2]
            vy, ux = np.mgrid[:h, :w]
            rays = (
                np.stack(((ux - cx) / fx, (vy - cy) / fy, np.ones_like(ux)), axis=-1)
                @ camera[:3, :3].T
            )
            distances = ((world_center - camera[:3, 3]) @ normal) / (rays @ normal)
            world = camera[:3, 3] + rays * distances[..., None]
            local = (world - world_center) @ axes
            half = allocation["pose_marker"]["marker_size_m"] / 2
            for region, extent in (("printed", half), ("payload_4x4", half * 2 / 3)):
                inside = np.max(abs(local[..., :2]), axis=-1) <= extent
                tab = r["views"]["native"]["registration"][code]["frozen_depth_regions"][region]
                if (
                    int(inside.sum()),
                    int(np.count_nonzero(inside & (depth > 0) & (distances - depth > 0.020))),
                ) != (tab["pixel_centers"], tab["foreground_gt20mm"]):
                    raise ValueError((key, code, region))
                checks["independent_native_region_counts"] += 1
        stored = archive.parent / (key + ".npz")
        if sha(stored) != seals[key]["archive_sha256"]:
            raise ValueError("different zero-step render")
        with np.load(stored, allow_pickle=False) as z:
            for method, v in r["views"].items():
                source = "normal" if method == "native" else method
                labels = seals[key]["labels"][source]
                if method == "native":
                    g, d = rgb, depth
                else:
                    g = z[source + "/rgb"]
                    d = z[source + "/depth"].copy()
                    baseline = z["normal/depth"]
                    valid = (depth > 0) & (baseline > 0) & (d > 0)
                    d[valid] = depth[valid] + (d[valid] - baseline[valid])
                    d[d <= 0] = 0
                gray = cv2.cvtColor(g, cv2.COLOR_RGB2GRAY)
                ids = z[source + "/geom"]
                if (
                    hashlib.sha256(np.ascontiguousarray(d).tobytes()).hexdigest()
                    != v["depth_sha256"]
                ):
                    raise ValueError((key, method, "metric depth"))
                for c in v["decision"]["candidates"]:
                    stems = c["cells"] + c["corners"] + [t["source"] for t in c["transitions"]]
                    for q in stems:
                        if sum(a[2] for a in q["weighted_native"]) != 1024:
                            raise ValueError("sampling phase")
                        for x, y, _, level, z0, label in q["weighted_native"]:
                            if (
                                int(gray[y, x]),
                                float(d[y, x]),
                                labels.get(str(ids[y, x]), "non-geom"),
                            ) != (level, z0, label):
                                raise ValueError((key, method, x, y))
                            checks["source_pixel_contributions"] += 1
                checks["views"] += 1
            if key == "d02-0128":
                c = next(c for c in r["views"]["native"]["decision"]["candidates"] if c["id"] == 28)
                depths = defaultdict(list)
                for cell in c["cells"]:
                    x, y = np.rint(cell["xy"]).astype(int)
                    label = cell["nearest_instance"]
                    depths["ID8" if label.startswith("g1_dual_id8_r") else label].append(
                        float(depth[y, x])
                    )
                aliases = {
                    "front_matches": c["exact_words"]["front"],
                    "mirrored_matches": c["exact_words"]["mirrored"],
                    "current_depth_by_independently_labeled_surface": {
                        k: {
                            "n": len(a),
                            "median_mm": 1000 * float(np.median(a)),
                            "min_mm": 1000 * min(a),
                            "max_mm": 1000 * max(a),
                        }
                        for k, a in depths.items()
                    },
                    "tcp_site_only_changed_rgb_pixels_after_hiding_all_geoms": int(
                        np.any(
                            z["no-arm-geoms/rgb"] != z["no-arm-geoms-and-tcp-site/rgb"], axis=2
                        ).sum()
                    ),
                }
        checks["native_anchors"] += 1
    return dict(
        checks=checks,
        alias_1088=aliases,
        script_sha256=sha(Path(__file__)),
        summary_sha256=sha(ROUND / "old-board-observation.public.json"),
        detail_sha256=sha(table),
    )


if __name__ == "__main__":
    result = verify(Path(sys.argv[1]))
    with (ROUND / "old-board-verification.public.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(result)
