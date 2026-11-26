"""Explain the registered shadow's rejected near-neighbor samples at the original first refusal."""
from unittest.mock import patch

import numpy as np

import shadow_edges
import shadow_readback as reader


def explain(destination):
    packets, bindings = reader.exposure_metadata()
    entry = packets["t02/1512"]
    path = reader.ROOT / entry["path"]
    frame = reader.checked_packet(path, entry["sha256"])
    identity, geometry = reader.bound(*bindings["t02"])
    detector, marker_sha = reader.native_marker(reader.GENER)
    table = np.load(reader.cv_pin(reader.CAL_REL + "/table.npy"), allow_pickle=False)
    assert marker_sha == reader.PLAN["marker_sha256"]
    evaluate = shadow_edges.extend_edges
    samples = []

    def inspect_mask(state, table_depth, evidence):
        chosen = evaluate(state, table_depth, evidence)
        x, y, sign = (state[key] for key in ("xx", "yy", "sign"))
        depth, gray = (state[key] for key in ("depth", "gray"))
        near = state["last"] - state["first"] > 9
        old = state["match"] & near & (state["fg"] - state["bg"] > 22)
        active = old.sum(axis=1)
        anchors = list(zip(x[old & (active == 1)[:, None]], y[old & (active == 1)[:, None]], strict=True))
        eligible = (active == 0)[:, None] & state["match"] & near
        for row, index in zip(*np.nonzero(eligible), strict=True):
            col, pos = int(x[row, index]), int(y[row, index])
            if not any(abs(a - col) == 1 and abs(b - pos) <= 1 for a, b in anchors):
                continue
            scan = [pos + k * sign for k in (-3, -2, -1, 0, 1, 2)]
            values = [int(gray[v, col]) for v in scan]
            samples.append({
                "side": state["side"], "edge_xy": [col, pos], "gray_inner_to_outer": values,
                "extended_contrast_dn": values[0] - values[-1],
                "inner_endpoint_drop_dn": values[0] - values[1],
                "outer_endpoint_drop_dn": values[-2] - values[-1],
                "monotonic": all(a >= b for a, b in zip(values[:-1], values[1:], strict=True)),
                "table_residual_mm": [1000 * abs(float(depth[v, col]) - float(table_depth[v, col])) for v in scan[-2:]],
            })
        return chosen

    with patch.object(shadow_edges, "extend_edges", inspect_mask):
        old, candidate, edges, status = shadow_edges.pose_readback(
            frame, detector(frame, geometry), geometry, identity, 1512, table, False,
        )
    assert old is None and candidate is None and len(samples) == len(edges) == 2
    reader.write(destination, {
        "source_frame_sha256": entry["sha256"], "step": entry["step"], "status": status, "samples": samples,
    })


if __name__ == "__main__":
    import sys
    from pathlib import Path

    explain(Path(sys.argv[1]))
