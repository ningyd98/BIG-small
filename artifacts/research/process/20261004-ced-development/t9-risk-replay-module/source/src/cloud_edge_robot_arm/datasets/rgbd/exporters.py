"""Grounding SFT export; simulator labels are confined to assistant targets."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from cloud_edge_robot_arm.datasets.rgbd.models import SplitManifest, canonical_json
from cloud_edge_robot_arm.datasets.rgbd.quality import validate_dataset


def export_grounding_sft(
    root: Path, split: Literal["train", "calibration", "selection"], output: Path
) -> int:
    """Export all retained examples, including explicit observation requests.

    User content contains exactly an instruction and two opaque RGB/depth image
    paths relative to dataset root. Metric depth/calibration references remain
    top-level metadata. The test role is denied at runtime as well as in typing.
    """
    if split == "test":
        raise ValueError("test holdout export is denied")
    if split not in {"train", "calibration", "selection"}:
        raise ValueError("unknown training split")
    from cloud_edge_robot_arm.datasets.rgbd.writer import _atomic_write, load_records
    from cloud_edge_robot_arm.vision.offline_reader import resolve_payload

    root, output = Path(root).resolve(), Path(output).resolve()
    report = validate_dataset(root)
    if not report.valid:
        raise ValueError("dataset validation failed: " + "; ".join(report.errors))
    # Never allow an export destination to overwrite original evidence or audit.
    if output == root or output.is_dir():
        raise ValueError("export output must be a file")
    if output.is_relative_to(root) and output.parts[len(root.parts)] != "exports":
        raise ValueError("export inside a dataset must use the exports directory")
    audit = SplitManifest.model_validate_json(
        resolve_payload(root, "reports/split_audit.json").read_bytes()
    )
    rows = []
    for record in sorted(load_records(root), key=lambda item: item.sample_id):
        if audit.sample_assignments[record.sample_id] != split:
            continue
        labels = record.labels
        assistant = {
            "action": labels["suggested_action"],
            "positive": labels["positive"],
            "negative_reasons": labels["negative_reasons"],
            "execution_verified": False,
        }
        if labels["positive"]:
            assistant.update(
                {key: labels[key] for key in ("target_pixel", "destination_pixel", "surface_point")}
            )
        rows.append(
            {
                "schema_version": "rgbd.dataset.v1",
                "sample_id": record.sample_id,
                "split": split,
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "instruction": labels["instruction"],
                            "images": [record.paths["rgb"], record.paths["depth_vis"]],
                        },
                    },
                    {"role": "assistant", "content": canonical_json(assistant)},
                ],
                "metadata": {
                    "dataset_root": str(root),
                    "depth": record.paths["depth"],
                    "camera": record.paths["camera"],
                    "source": record.source,
                    "label_source": record.label_source,
                    "content_hash": record.content_hash,
                },
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(output, "".join(canonical_json(row) + "\n" for row in rows).encode())
    return len(rows)
