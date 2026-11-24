"""Compare every actual grouped second-version system with its original public NumPy call."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from pixel_timing import ROUND, V1, prior


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("diagnostic_source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    driver = prior()
    manifest = json.loads((ROUND / "detector-source.public.json").read_bytes())
    driver.SOURCES = manifest["candidate_detector_files_sha256"]
    method = driver.readers(args.diagnostic_source)["candidate"]
    grid = method.__globals__["find_grids"].__globals__
    original = grid["_pose_lstsq"]
    rows, frames, geometry = driver.inputs()
    previous = json.loads((V1 / "solver-witness.public.json").read_bytes())
    output = {}
    for row in rows[-2:]:
        key = row["file"]
        evidence = []

        def check(a, b, evidence=evidence):
            x, ranks, singular = original(a, b)
            expected = [
                np.linalg.lstsq(matrix, rhs, rcond=None) for matrix, rhs in zip(a, b, strict=True)
            ]
            for i, (solution, _, rank, spectrum) in enumerate(expected):
                assert solution.tobytes() == x[i].tobytes()
                assert rank.tobytes() == ranks[i].tobytes()
                assert spectrum.tobytes() == singular[i].tobytes()
            hashes = [
                (driver.sha(m.tobytes()), driver.sha(rhs.tobytes()))
                for m, rhs in zip(a, b, strict=True)
            ]
            evidence.append(
                dict(
                    rows=a.shape[1],
                    systems=len(a),
                    inputs_sha256=driver.sha(driver.canonical(hashes)),
                )
            )
            return x, ranks, singular

        grid["_pose_lstsq"] = check
        try:
            result = method(frames[row["frame_id"]], geometry)
        finally:
            grid["_pose_lstsq"] = original
        original_groups = previous["frames"][key]["same_lapack_witness"]["groups"]
        assert Counter(g["inputs_sha256"] for g in original_groups) == Counter(
            g["inputs_sha256"] for g in evidence
        )
        assert driver.sha(driver.canonical(result)) == previous["frames"][key]["measurement_sha256"]
        output[key] = dict(
            file_sha256=row["file_sha256"],
            frame_id=row["frame_id"],
            checksum_sha256=row["checksum_sha256"],
            measurement_sha256=driver.sha(driver.canonical(result)),
            grouped_inputs=evidence,
            all_x_rank_s_bitwise=True,
            systems=sum(g["systems"] for g in evidence),
        )
    full = dict(
        detector_files_sha256=driver.SOURCES,
        frames=output,
        source_sha256=driver.sha(Path(__file__).read_bytes()),
        numpy=np.__version__,
        executable=sys.executable,
        baseline_system_evidence_sha256=driver.sha(
            (V1 / "solver-witness.public.json").read_bytes()
        ),
    )
    with args.output.open("x") as file:
        json.dump(full, file, sort_keys=True, indent=2, allow_nan=False)
        file.write("\n")
    print({key: row["systems"] for key, row in output.items()})


if __name__ == "__main__":
    main()
