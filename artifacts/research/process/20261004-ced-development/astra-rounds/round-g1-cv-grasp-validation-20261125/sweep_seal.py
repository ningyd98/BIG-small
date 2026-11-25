"""Archive blind predictions and the original source before comparing any later contacts."""

import argparse
import base64
import gzip
import json
from pathlib import Path

from sweep_history import ROUND, compact, digest, encoded

FILES = [
    "sweep_replay.py",
    "sweep_start.py",
    "sweep_depth.py",
    "sweep_geometry.py",
    "sweep_evaluate.py",
    "sweep_history.py",
    "test_sweep.py",
]
PLAN = "596158c29f9d43573a92c2be22a5b9db55e5d8b21f08cc8382e65e3d8b7ffb1a"


def compressed(value):
    data = encoded(value)
    z = gzip.compress(data, compresslevel=9, mtime=0)
    return dict(
        encoding="base64 gzip JSON UTF8 LF",
        uncompressed_bytes=len(data),
        uncompressed_sha256=digest(data),
        compressed_sha256=digest(z),
        data_base64=base64.b64encode(z).decode(),
    )


def save(path, blob):
    with path.open("xb") as dest:
        dest.write(blob)


def seal(raw, blind, out):
    for f in ("sweep-history.public.json", "sweep-candidates.public.json"):
        save(out / f, (raw / f).read_bytes())
    two = []
    summary = []
    for key in ("A", "B"):
        source = (raw / (key + ".json")).read_bytes()
        row = json.loads(source)
        two.append(row)
        summary.append(
            compact(row)
            | dict(
                anonymous_id=key,
                result_sha256=digest(source),
                frame_sha256=digest((blind / key / "frame.json").read_bytes()),
                proprio_sha256=digest((blind / key / "proprio.json").read_bytes()),
                geometry_sha256=digest((blind / "geometry.json").read_bytes()),
                robot_state=row["measured_robot"],
                initial_routes=row["initial_routes"],
                unknown_volume_method=(
                    "Sum of pixel-frustum volume upper bounds over boxes and "
                    "phases. Their swept volumes can overlap."
                ),
            )
        )
    output = dict(
        schema="g1-grasp-sweep-blind-v1",
        plan_sha256=PLAN,
        frames=summary,
        full_predictions=compressed(two),
    )
    save(out / "sweep-prospective.public.json", encoded(output))
    sources = {name: (ROUND / name).read_text() for name in FILES}
    files = dict((f, digest((ROUND / f).read_bytes())) for f in FILES)
    for row in two:
        assert all(files[n] == v for n, v in row["source_sha256"].items())
    receipt = dict(
        schema="g1-grasp-v1-seal",
        plan_sha256=PLAN,
        estimator_sha256=files,
        source_before_review=compressed(sources),
        framework="current RGBD, registered local geometry, synchronized robot state if available",
        outputs_sha256={
            name: digest((out / name).read_bytes())
            for name in (
                "sweep-history.public.json",
                "sweep-candidates.public.json",
                "sweep-prospective.public.json",
            )
        },
    )
    save(out / "sweep-seal.public.json", encoded(receipt))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("raw", type=Path)
    p.add_argument("blind", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    seal(a.raw, a.blind, a.out)
