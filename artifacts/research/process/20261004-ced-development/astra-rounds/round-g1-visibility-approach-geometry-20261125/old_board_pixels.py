"""Replay unchanged historical camera states; exported counterfactuals are offline diagnostics."""

import argparse
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import cv2
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

PRIVATE = Path("experiments/results/g1-visibility-pose-repair-20261124")
FORMAL = Path("experiments/results/g1-formal-paired-20261124")
TRAIN = PRIVATE / "batches/train-feedback-deadline-01/d02"
GENERATION = "c3ca24cf1dc459651bd99dc85a997c36d39108c91d3cf7fb73d35e8071487261"
PLAN = "f73a383f23408f6d53d30677928545ed4e515419ab0ed16da7b391c1275ed015"
ROUND = Path(__file__).resolve().parent


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def put(path, data):
    value = (
        json.dumps(
            data,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":") if path.suffix == ".gz" else None,
            indent=None if path.suffix == ".gz" else 2,
        ).encode()
        + b"\n"
    )
    with path.open("xb") as stream:
        if path.suffix == ".gz":
            with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as archive:
                archive.write(value)
        else:
            stream.write(value)
    return sha(path)


def load_context(repo):
    plan_file = ROUND / "plan.json"
    if sha(plan_file) != PLAN:
        raise ValueError("unbound geometry plan")
    hashes = json.loads(plan_file.read_bytes())["inputs_sha256"]
    root = repo / PRIVATE / "builds" / GENERATION / "runtime-source"
    sys.path[:0] = [str(root), str(root / "src")]
    ref = Path("scripts/graduation/g1_formal_failure_occlusion.py")
    if sha(repo / ref) != hashes[str(ref)]:
        raise ValueError("changed original zero-step reconstruction")
    spec = importlib.util.spec_from_file_location("g1_reference_occlusion", repo / ref)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    manifest_file = FORMAL / "originals-manifest.json"
    if sha(repo / manifest_file) != hashes[str(manifest_file)]:
        raise ValueError("changed formal frame manifest")
    formal = json.loads((repo / manifest_file).read_bytes())["files"]
    hashes.update({str(FORMAL / k): v["sha256"] for k, v in formal.items()})
    return root, old, hashes


def cases(repo, root, hashes):
    families = [("d02", TRAIN, root)] + [
        (f"f{n:02d}-{arm}", FORMAL / f"trials/f{n:02d}-{arm}", repo / FORMAL / "runtime-source")
        for n in range(1, 5)
        for arm in ("original", "dual")
    ]
    for label, head, asset_root in families:
        raw = head / "instance"
        paths = [head / "allocation.json", raw / "offline-truth.json", raw / "pixel-index.json"]
        digests = {str(p): sha(repo / p) for p in paths}
        if any(hashes.get(k) != h for k, h in digests.items()):
            raise ValueError("case registration or evidence differs " + label)
        alloc, truth, index = [json.loads((repo / p).read_bytes()) for p in paths]
        if index["allocation_sha256"] != digests[str(paths[0])] or (
            truth["allocation_sha256"] != index["allocation_sha256"]
            or truth["episode"] != index["episode"]
            or truth["scene"] != index["scene"]
        ):
            raise ValueError("mismatched registered case")
        geom = alloc["geometry"]
        xml = asset_root / geom["asset_path"]
        if sha(xml) != alloc["asset_sha256"] or alloc["asset_sha256"] != truth["asset_sha256"]:
            raise ValueError("mismatched registered physical asset")
        rows = (
            [r for r in index["frames"] if r["physics_step"] >= 1056]
            if label == "d02"
            else index["frames"][-3:-1]
        )
        if len(rows) != (6 if label == "d02" else 2):
            raise ValueError("unexpected anchor sequence")
        digests[str(xml.relative_to(repo))] = sha(xml)
        for row in rows:
            p = raw / row["file"]
            if hashes.get(str(p)) != row["file_sha256"] or sha(repo / p) != row["file_sha256"]:
                raise ValueError("changed original " + str(p))
            digests[str(p)] = row["file_sha256"]
        yield (
            label,
            repo / raw,
            geom,
            xml,
            {s["physics_step"]: s for s in truth["samples"]},
            rows,
            digests,
        )


def modes(old, model, extra):
    from scripts.graduation import proposal_camera as cam

    basic = {
        "normal": (),
        "no-palm": ("hand",),
        "no-left": ("left_finger_geom",),
        "no-right": ("right_finger_geom",),
        "no-palm-and-fingers": old.HAND,
    }
    if not extra:
        return basic
    all_geoms = tuple(cam.arm_geometries(model).values())
    return {
        **basic,
        "no-link6": ("link6",),
        "no-link6-palm-and-fingers": ("link6", *old.HAND),
        "no-arm-geoms": all_geoms,
        "no-arm-geoms-and-tcp-site": all_geoms,
    }


def capture(repo, out):
    from scripts.graduation import proposal_camera as cam

    from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    root, old, hashes = CONTEXT
    if os.environ.get("MUJOCO_GL") != "egl":
        raise ValueError("registered EGL renderer required")
    out.mkdir()
    files = {}
    with (repo / PRIVATE / "egl.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for name, raw, _geom, xml, states, rows, digests in cases(repo, root, hashes):
            model = mujoco.MjModel.from_xml_path(str(xml))
            data = mujoco.MjData(model)
            camera = MuJoCoRGBDCamera(mujoco, model, width=320, height=240)
            try:
                for row in rows:
                    frame_path = raw / row["file"]
                    frame = RGBDObservation.model_validate_json(frame_path.read_bytes())
                    if (
                        frame.frame_id != row["frame_id"]
                        or frame.checksum_sha256 != row["checksum_sha256"]
                    ):
                        raise ValueError("frame identity mismatch")
                    state = states[row["physics_step"]]
                    fk = cam.restore(model, data, state)
                    q = int(model.joint("object_free").dofadr[0])
                    data.qvel[q : q + 6] = (
                        state["object_linear_velocity_m_s"] + state["object_angular_velocity_rad_s"]
                    )
                    mujoco.mj_forward(model, data)
                    state_hash = camera._physics_state_hash(data)
                    key = name + "-" + frame_path.stem
                    arrays, labels, hidden = {}, {}, {}
                    methods = modes(old, model, name == "d02" and row["physics_step"] == 1088)
                    for method, names in methods.items():
                        saved = model.site_rgba.copy()
                        hidden_site = method == "no-arm-geoms-and-tcp-site"
                        try:
                            if hidden_site:
                                model.site_rgba[model.site("tcp").id, 3] = 0
                            rendered = old.render(camera, model, data, frame, names, state_hash)
                        finally:
                            model.site_rgba[:] = saved
                        hidden[method] = {"geoms": names, "sites": ["tcp"] if hidden_site else []}
                        for channel in ("rgb", "depth", "geom"):
                            arrays[method + "/" + channel] = rendered[channel]
                        labels[method] = rendered["labels"]
                    archive = out / (key + ".npz")
                    with archive.open("xb") as stream:
                        np.savez_compressed(stream, **arrays)
                    files[key] = dict(
                        archive_sha256=sha(archive),
                        registered_sources=digests,
                        state_sha256=state_hash,
                        fk=fk,
                        hidden=hidden,
                        labels=labels,
                        frame_id=frame.frame_id,
                        checksum_sha256=frame.checksum_sha256,
                    )
            finally:
                camera.close()
    put(out / "capture.json", {"plan_sha256": PLAN, "frames": files})
    print("22 registered anchors captured", flush=True)


def stencil(xy, gray, depth, ids, labels):
    """Source texels and OpenCV's 1/32-pixel interpolation phase at one native point."""
    x, y = map(float, xy)
    qx, qy = np.rint(np.float32([x, y]) * 32).astype(int)
    i, j = qx // 32, qy // 32
    ax, ay = qx % 32, qy % 32
    pixels = []
    for u, v, w in (
        (i, j, (32 - ax) * (32 - ay)),
        (i + 1, j, ax * (32 - ay)),
        (i, j + 1, (32 - ax) * ay),
        (i + 1, j + 1, ax * ay),
    ):
        if w:
            pixels.append(
                [
                    int(u),
                    int(v),
                    int(w),
                    int(gray[v, u]),
                    float(depth[v, u]),
                    labels.get(int(ids[v, u]), "non-geom"),
                ]
            )
    return {"xy": [x, y], "weighted_native": pixels}


def measure(frame, geom, rendered_ids, labels):
    from scripts.graduation import g1_visibility_grid as grid
    from scripts.graduation import g1_visibility_vision as vision
    from scripts.graduation import proposal_camera as cam

    rgb, depth = cam.rgb(frame), cam.depth(frame)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    candidates, ambiguous, rejected = grid.find_grids(
        gray,
        depth,
        np.sqrt(frame.intrinsics[0] * frame.intrinsics[1]),
        geom["pose_marker"]["marker_size_m"],
    )
    result = vision.measure_frame(frame, geom)
    if result["observed_ids"] != sorted(c["id"] for c in candidates):
        raise ValueError("independent candidate grid differs from full observer")

    def at(xy):
        return stencil(xy, gray, depth, rendered_ids, labels)

    evidence = []
    for c in candidates:
        support = c["grid_support"]
        xy = grid.CELLS @ c["basis"] + c["center"]
        near = np.rint(xy).astype(int)
        bits = np.array(support["cell_values"]).reshape(6, 6) > support["threshold_gray"]
        matches = {}
        for orientation, bitmap in (("front", bits), ("mirrored", np.fliplr(bits))):
            matches[orientation] = [
                [int(k), t]
                for t in range(4)
                for k in np.flatnonzero(np.all(grid.SYMBOLS == np.rot90(bitmap, t), axis=(1, 2)))
            ]
        samples = [
            dict(
                at(p),
                cell=i,
                nearest_instance=labels.get(int(rendered_ids[v, u]), "non-geom"),
                center_gray=support["cell_values"][i],
                local_median=support["cell_local_medians"][i],
            )
            for i, (p, (u, v)) in enumerate(zip(xy, near, strict=True))
        ]
        evidence.append(
            dict(
                id=c["id"],
                pattern=c["pattern"],
                origins=c["origins"],
                center_px=c["center"].tolist(),
                exact_words=matches,
                front_face_ambiguous=c["front_face_ambiguous"],
                corners=[at(p) for p in c["corners"]],
                cells=samples,
                contrast=support["contrast_gray"],
                threshold=support["threshold_gray"],
                supported_vertices=support["supported_vertices"],
                lines_per_axis=support["lines_per_axis"],
                heldout_rms_px=support["heldout_rms_px"],
                heldout_rms_per_axis_px=support["heldout_rms_per_axis_px"],
                transitions=[
                    dict(row, source=at(row["pixel"])) for row in support["transition_points"]
                ],
            )
        )
    return dict(
        observed_ids=result["observed_ids"],
        usable_ids=result["usable_ids"],
        selected_id=result["selected_id"],
        reason=result["reason"],
        disagreement_m=result["target_disagreement_m"],
        usable=result["usable"],
        per_id_grasp_m={k: s["grasp_world_m"] for k, s in result["by_id"].items()},
        ambiguous=ambiguous,
        rejected_quad_count=rejected,
        candidates=evidence,
    )


def regions(frame, state, spec, rgb, depth, ids, labels):
    from scripts.graduation import g1_visibility_grid as grid

    old = CONTEXT[1]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    poly = old.polygon_geometry(frame, state, spec)
    meta, _, _ = old.geometry_evidence(frame, poly, depth)
    homography = cv2.getPerspectiveTransform(grid.CORNERS, np.float32(poly["print_xy"]))
    centers = cv2.perspectiveTransform(grid.CELLS[None], homography)[0]
    meta["registered_cells"] = [
        dict(
            stencil(xy, gray, depth, ids, labels),
            cell=j,
            printed_white=bool(spec["bits"].ravel()[j]),
        )
        for j, xy in enumerate(centers)
    ]
    meta["instance_histograms"] = {
        name: old.geom_hist(ids[poly["roi"]], poly["areas"][name], labels)
        for name in ("printed", "payload_4x4", "quiet", "black_border")
    }
    return meta


def figure(samples, path):
    colors = {"hand": (236, 74, 91), "link6": (235, 152, 7), "printed": (2, 153, 124)}
    font = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

    def text_font(size):
        return ImageFont.truetype(font, size)

    canv = Image.new("RGB", (959, 621), (249, 249, 246))
    draw = ImageDraw.Draw(canv)
    draw.text(
        (18, 10), "G1 接近阶段第 1088 步的原图与同姿态对照", fill=(21, 36, 42), font=text_font(24)
    )
    draw.text(
        (18, 51),
        "左上为 ID7，右下为 ID8。小圆点标出反射候选 28 的 36 个格心所在表面。",
        fill=(62, 76, 79),
        font=text_font(16),
    )
    names = [
        ("native", "原图", "ID7、反射 28 · 拒绝"),
        ("overlay", "原图 · 格心实例", "纸面 20，手掌 11，第六连杆 5"),
        ("no-palm", "只隐藏手掌", "ID7 · 接纳"),
        ("no-right", "只隐藏右指", "ID7、反射 28 · 拒绝"),
        ("no-arm-geoms", "隐藏全部机械臂几何", "ID7 · 接纳"),
        ("no-arm-geoms-and-tcp-site", "再隐藏 TCP 可视站点", "ID7、ID8 · 分歧 3.21 mm"),
    ]
    for i, (k, title, caption) in enumerate(names):
        x = 17 + (i % 3) * 316
        y = 84 + (i // 3) * 252
        original, candidate = samples[k if k != "overlay" else "native"]
        im = (
            Image.fromarray(original)
            .crop((160, 84, 223, 134))
            .resize((252, 200), Image.Resampling.NEAREST)
        )
        if k == "overlay":
            pen = ImageDraw.Draw(im)
            for c in next(r for r in candidate["candidates"] if r["id"] == 28)["cells"]:
                u, v = c["xy"]
                xx = (u - 160 + 0.5) * 4
                yy = (v - 84 + 0.5) * 4
                color = colors.get(c["nearest_instance"], colors["printed"])
                pen.ellipse((xx - 2.3, yy - 2.3, xx + 2.3, yy + 2.3), fill=color)
        canv.paste(im, (x, y + 23))
        draw.text((x, y), title, fill=(20, 35, 41), font=text_font(16))
        draw.text((x, y + 227), caption, fill=(43, 62, 66), font=text_font(14))
    draw.text(
        (18, 595),
        "青绿为 ID8 纸面，红为手掌，橙为第六连杆。各图采用同一裁区，物理步进次数为零。",
        fill=(51, 72, 77),
        font=text_font(13),
    )
    with path.open("xb") as stream:
        canv.save(stream, format="PNG")


def analyze(repo, out):
    from scripts.graduation import proposal_camera as cam

    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    root, old, hashes = CONTEXT
    seal_path = out / "capture.json"
    seal = json.loads(seal_path.read_bytes())
    if seal["plan_sha256"] != PLAN:
        raise ValueError("unbound diagnostic capture")
    detail, summary, illustration = {}, {}, {}
    for case, raw, geom, xml, states, rows, digests in cases(repo, root, hashes):
        model = mujoco.MjModel.from_xml_path(str(xml))
        specs = old.transforms(model, geom)
        for row in rows:
            p = raw / row["file"]
            key = case + "-" + p.stem
            src = seal["frames"][key]
            saved = out / (key + ".npz")
            if sha(saved) != src["archive_sha256"] or digests != src["registered_sources"]:
                raise ValueError("changed original or diagnostic render")
            f = RGBDObservation.model_validate_json(p.read_bytes())
            state = states[row["physics_step"]]
            rgb, depth = cam.rgb(f), cam.depth(f)
            with np.load(saved, allow_pickle=False) as z:
                views = {}
                normal_rgb, normal_depth = z["normal/rgb"], z["normal/depth"]
                common = (normal_depth > 0) & (depth > 0)
                alignment = dict(
                    rgb_different_px=int(np.any(rgb != normal_rgb, axis=2).sum()),
                    depth_p99_abs_mm=float(
                        np.quantile(abs(depth[common] - normal_depth[common]), 0.99) * 1000
                    ),
                    mask_disagreements=int(((depth > 0) != (normal_depth > 0)).sum()),
                )
                for name in ["native", *src["hidden"]]:
                    source = "normal" if name == "native" else name
                    labels = {int(k): v for k, v in src["labels"][source].items()}
                    ids = z[source + "/geom"]
                    rgb_view = rgb if name == "native" else z[source + "/rgb"]
                    depth_view = (
                        depth
                        if name == "native"
                        else old.paired_depth(depth, normal_depth, z[source + "/depth"])
                    )
                    packet = f if name == "native" else old.packet(f, rgb_view, depth_view, name)
                    decision = measure(packet, geom, ids, labels)
                    views[name] = dict(
                        decision=decision,
                        registration={
                            code: regions(f, state, s, rgb_view, depth_view, ids, labels)
                            for code, s in specs.items()
                        },
                        rgb_sha256=old.digest_array(rgb_view),
                        depth_sha256=old.digest_array(depth_view),
                        instance_source=(
                            "normal_zero_step_aligned" if name == "native" else "same_render"
                        ),
                        hidden=src["hidden"].get(name, {}),
                    )
                    if key == "d02-0128":
                        illustration[name] = (rgb_view.copy(), decision)
                native = views["native"]["decision"]
                normal = views["normal"]["decision"]
                alignment["native_normal_decision_equal"] = all(
                    native[k] == normal[k]
                    for k in ("observed_ids", "usable_ids", "selected_id", "reason", "usable")
                )
                detail[key] = dict(
                    frame_id=f.frame_id,
                    checksum=f.checksum_sha256,
                    frame_sha256=sha(p),
                    physics_step=row["physics_step"],
                    source_sha256=digests,
                    archive_sha256=src["archive_sha256"],
                    static_state_sha256=src["state_sha256"],
                    fk=src["fk"],
                    alignment=alignment,
                    views=views,
                )
                summary[key] = dict(
                    step=row["physics_step"],
                    frame_ref=str(p.relative_to(repo)),
                    alignment=alignment,
                    outcomes={
                        m: {
                            k: v["decision"][k]
                            for k in ("observed_ids", "usable_ids", "reason", "disagreement_m")
                        }
                        for m, v in views.items()
                    },
                )
    if len(detail) != 22 or set(detail) != set(seal["frames"]):
        raise ValueError("incomplete anchor set")
    data = ROUND / "old-board-pixels.public.json.gz"
    detail_sha = put(
        data,
        dict(
            schema="g1.approach.old-board.pixel-evidence.v1",
            plan_sha256=PLAN,
            frames=detail,
            native_stencil_layout=[
                "x",
                "y",
                "bilinear_weight_over_1024",
                "gray_uint8",
                "current_optical_depth_m",
                "rendered_instance",
            ],
            coordinates="Every cell and held-out transition uses native pixel centers. "
            "Instance identity and registered projections are retrospective annotations.",
        ),
    )
    fig = ROUND / "old-board-approach.public.png"
    figure(illustration, fig)
    put(
        ROUND / "old-board-observation.public.json",
        dict(
            schema="g1.approach.old-board.summary.v1",
            plan_sha256=PLAN,
            script_sha256=sha(Path(__file__)),
            detail_sha256=detail_sha,
            figure_sha256=sha(fig),
            private_capture=str(seal_path.relative_to(repo)),
            private_capture_sha256=sha(seal_path),
            anchors=len(detail),
            original_native_frames=len(detail),
            static_captures=sum(len(s["hidden"]) for s in seal["frames"].values()),
            parameters={
                "camera": "320x240",
                "physics_steps": 0,
                "noise": "paired original residual on common valid rays",
                "registration": "original sealed per-episode asset and camera",
                "hand_geometries": old.HAND,
            },
            per_anchor=summary,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["capture", "analyze"])
    parser.add_argument("repo", type=Path)
    parser.add_argument("private", type=Path)
    args = parser.parse_args()
    CONTEXT = load_context(args.repo.resolve())
    if args.operation == "capture":
        capture(args.repo.resolve(), args.private)
    else:
        analyze(args.repo.resolve(), args.private)
