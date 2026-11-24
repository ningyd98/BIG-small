"""Inspect repeated operations in the first candidate after its full-window budget failure."""

import argparse
import cProfile
import inspect
import json
import pstats
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from pixel_timing import SOURCES, canonical, inputs, readers, sha


def solver_witness(groups):
    from numpy.linalg import _umath_linalg

    def scalar(rows):
        return [np.linalg.lstsq(a, b, rcond=None) for a, b in rows]

    def batched(rows):
        matrices = np.stack([a for a, _ in rows])
        rhs = np.stack([b for _, b in rows])[..., None]
        m, n = matrices.shape[-2:]
        rcond = np.finfo(matrices.dtype).eps * max(m, n)
        x, residuals, rank, singular = _umath_linalg.lstsq(
            matrices, rhs, rcond, signature="ddd->ddid"
        )
        return [
            (
                x[i, :, 0],
                residuals[i] if m > n and rank[i] == n else np.empty(0),
                rank[i],
                singular[i],
            )
            for i in range(len(rows))
        ]

    evidence = []
    for (group, code, iteration, m), rows in groups.items():
        count = Counter()
        for original, candidate in zip(scalar(rows), batched(rows), strict=True):
            for key, a, b in zip(
                ("x", "residuals", "rank", "singular_values"), original, candidate, strict=True
            ):
                assert np.asarray(a).shape == np.asarray(b).shape
                assert np.asarray(a).tobytes() == np.asarray(b).tobytes()
                count[key] += 1
        evidence.append(
            dict(
                group=group,
                code=code,
                iteration=iteration,
                fit_rows=m,
                poses=len(rows),
                matches=dict(count),
                inputs_sha256=sha(
                    canonical([(sha(a.tobytes()), sha(b.tobytes())) for a, b in rows])
                ),
            )
        )
    timings = []
    for rep in range(12):
        order = [scalar, batched] if rep % 2 == 0 else [batched, scalar]
        pair = {}
        for method in order:
            start = time.perf_counter_ns()
            outputs = [method(rows) for rows in groups.values()]
            pair[method.__name__ + "_ns"] = time.perf_counter_ns() - start
            del outputs
        timings.append(pair)
    return dict(
        groups=evidence,
        samples=timings,
        numpy=np.__version__,
        public_wrapper_sha256=sha(inspect.getsource(np.linalg.lstsq).encode()),
        generalized_ufunc_signature=_umath_linalg.lstsq.signature,
        timing_scope="Existing per-fit matrices/RHS only. Includes stacking and unpacking. "
        "No estimator patch, full-frame timing, or release claim.",
    )


def trace_operations(method, frame, geometry):
    grids = method.__globals__["find_grids"].__globals__
    weak, scalar, seeds = (grids[k].__code__ for k in ("_weak_grid_cells", "_verify", "_seeds"))
    solve = np.linalg.lstsq.__wrapped__.__code__
    fits = defaultdict(list)
    actual_systems = defaultdict(list)
    neighbors = defaultdict(Counter)
    proposals = []
    group_number = 0

    def profile(call, event, result):
        nonlocal group_number
        code = call.f_code
        if code is grids["_accept"].__code__ and event == "call":
            group_number += 1
        elif code is solve and event == "call":
            parent = call.f_back
            while parent is not None and parent.f_code not in (weak, scalar):
                parent = parent.f_back
            if parent is not None:
                a, b = (call.f_locals[k] for k in ("a", "b"))
                ctx = parent.f_locals
                group = (parent.f_code.co_name, int(ctx["code"]), int(ctx["iteration"]))
                fits[group].append((sha(a.tobytes()), sha(b.tobytes())))
                if parent.f_code is weak:
                    key = (group_number, group[1], group[2], len(a))
                    actual_systems[key].append((a.copy(), b.copy()))
        elif code.co_name == "nearby" and event == "call":
            parent = call.f_back
            ctx = parent.f_locals
            key = (ctx["source"], group_number)
            neighbors[key][int(call.f_locals["i"])] += 1
        elif code is seeds and event == "return" and "levels" in call.f_locals:
            ctx = call.f_locals
            mask = (ctx["ids"][:, 0] >= 0) & (ctx["white"] - ctx["ink"] >= grids["MIN_CONTRAST"])
            proposals.append(
                dict(
                    sampled=len(mask), exact_word_and_contrast=int(mask.sum()), accepted=len(result)
                )
            )

    sys.setprofile(profile)
    try:
        val = method(frame, geometry)
    finally:
        sys.setprofile(None)
    return dict(
        measurement_sha256=sha(canonical(val)),
        same_lapack_witness=solver_witness(actual_systems),
        least_squares=[
            dict(
                caller=c,
                code=k,
                iteration=t,
                calls=len(v),
                distinct_matrix=len({a for a, _ in v}),
                distinct_rhs=len({b for _, b in v}),
                distinct_matrix_and_rhs=len(set(v)),
            )
            for (c, k, t), v in sorted(fits.items())
        ],
        nearby=[
            dict(
                source=source,
                distinct_indices=len(counts),
                calls=sum(counts.values()),
                repeated_same_seed=sum(c - 1 for c in counts.values()),
            )
            for (source, _), counts in neighbors.items()
        ],
        proposal_filter=proposals,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("diagnostic_source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    method = readers(args.diagnostic_source)["candidate"]
    index, frames, geometry = inputs()
    out = {}
    for row in index[-2:]:
        frame = frames[row["frame_id"]]
        method(frame, geometry)
        frame_counts = trace_operations(method, frame, geometry)
        times = cProfile.Profile()
        times.enable()
        for _ in range(5):
            method(frame, geometry)
        times.disable()
        stats = pstats.Stats(times)
        rows = []
        for (filename, lineno, name), (primitive, calls, own, total, _) in stats.stats.items():
            if total / 5 >= 0.00015:
                rows.append(
                    dict(
                        file=Path(filename).name,
                        lineno=lineno,
                        function=name,
                        primitive_calls=primitive,
                        calls=calls,
                        cumulative_ms_per_frame=total / 5 * 1000,
                        self_ms_per_frame=own / 5 * 1000,
                    )
                )
        frame_counts.update(
            profile_repetitions=5,
            functions=sorted(rows, key=lambda r: -r["cumulative_ms_per_frame"]),
            file_sha256=row["file_sha256"],
            checksum_sha256=frame.checksum_sha256,
        )
        out[row["file"]] = frame_counts
    doc = dict(
        detector_files_sha256=SOURCES,
        source_sha256=sha(Path(__file__).read_bytes()),
        scope="Read-only cProfile and call trace on the frozen candidate after qualification. "
        "Inclusive times carry tracing overhead and do not enter the release sample.",
        frames=out,
    )
    with args.output.open("x") as f:
        json.dump(doc, f, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
