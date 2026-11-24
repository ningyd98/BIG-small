"""Find and verify oriented DICT_4X4_50 grids using only current native image samples."""

from functools import lru_cache

import cv2
import numpy as np

CELL_XY = np.stack(np.meshgrid(np.arange(6) - 2.5, np.arange(6) - 2.5), axis=-1)
CELLS = CELL_XY.reshape(36, 2).astype(np.float32)
CORNERS = np.float32([[-3, -3], [3, -3], [3, 3], [-3, 3]])
DATA = np.arange(36).reshape(6, 6)[1:5, 1:5].ravel()
BORDER = np.setdiff1d(np.arange(36), DATA)
WEIGHTS = (1 << np.arange(16)).astype(np.int32)
DICTIONARY = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
SYMBOLS = np.array([cv2.aruco.generateImageMarker(DICTIONARY, k, 6) > 0 for k in range(50)])
PATTERNS = np.concatenate((SYMBOLS, SYMBOLS[:, :, ::-1]))
TURNS = np.int8([[[1, 0], [0, 1]], [[0, 1], [-1, 0]], [[-1, 0], [0, -1]], [[0, -1], [1, 0]]])
MIN_CONTRAST = 32
PROFILE_OFFSETS = np.linspace(-0.61, 0.61, 15)
MIN_CELL_MARGIN = 0.13
# Native samples are uint8. Class medians are half-levels and the decision threshold
# is their midpoint. Leave one quarter gray level next to each limit to the scalar path.
PHOTOMETRIC_GUARD = 0.25
ISLAND_ANGLES = np.radians(np.arange(0, 90, 7.5))
ISLAND_ROTATIONS = (
    np.stack(
        [
            np.cos(ISLAND_ANGLES),
            np.sin(ISLAND_ANGLES),
            -np.sin(ISLAND_ANGLES),
            np.cos(ISLAND_ANGLES),
        ],
        axis=1,
    )
    .reshape(-1, 2, 2)
    .astype(np.float32)
)


def _registered_lstsq_kernel():
    if np.__version__ != "2.5.3":
        return None
    try:
        from numpy.linalg import _umath_linalg
    except ImportError:
        return None
    fn = getattr(_umath_linalg, "lstsq", None)
    if getattr(
        fn, "signature", None
    ) != "(m,n),(m,nrhs),()->(n,nrhs),(nrhs),(),(p)" or "ddd->ddid" not in getattr(fn, "types", ()):
        return None
    return fn


_LSTSQ_KERNEL = _registered_lstsq_kernel()


def _table():
    lut = np.full((65536, 2), -1, np.int16)
    reverse = np.full((65536, 2), -1, np.int16)
    mirror_id = np.full(65536, -1, np.int16)
    for code, bits in enumerate(SYMBOLS):
        for turn in range(4):
            oriented = np.rot90(bits, turn)[1:5, 1:5]
            key = oriented.ravel() @ WEIGHTS
            if lut[key, 0] != -1:
                raise ValueError("dictionary does not have unique oriented words")
            lut[key] = [code, turn]
            reverse_key = np.rot90(np.fliplr(bits), turn)[1:5, 1:5].ravel() @ WEIGHTS
            mirror_id[reverse_key] = code
            reverse[reverse_key] = [len(SYMBOLS) + code, turn]
    unmatched = lut[:, 0] < 0
    lut[unmatched] = reverse[unmatched]
    return lut, mirror_id


WORDS, REFLECTED = _table()


def _sample(gray, xy):
    """Bilinear sampling at native pixel centers; calls use their real in-frame footprint."""
    flat = np.ascontiguousarray(xy, dtype=np.float32).reshape(-1, 2)
    if len(flat) < 32767:
        native = cv2.remap(gray, flat[None, :, :], None, cv2.INTER_LINEAR)
        return native.reshape(xy.shape[:-1])
    # OpenCV's remapper accepts a signed-short maximum dimension; pad in short rows.
    width = min(1024, len(flat))
    pad = (-len(flat)) % width
    if pad:
        flat = np.pad(flat, ((0, pad), (0, 0)), mode="edge")
    uv = flat.reshape(-1, width, 2)
    return (
        cv2.remap(gray, uv, None, cv2.INTER_LINEAR).ravel()[: xy.size // 2].reshape(xy.shape[:-1])
    )


def _quad_pose(quad):
    p = np.float32(quad).reshape(4, 2)
    basis = np.stack(((p[1] - p[0] + p[2] - p[3]) / 12, (p[3] - p[0] + p[2] - p[1]) / 12))
    if np.linalg.det(basis) < 0:
        basis = basis[::-1]
    return p.mean(axis=0), basis


def _seeds(centers, bases, gray):
    """Decode center samples in batches; every returned proposal still needs edge verification."""
    if not len(centers):
        return []
    centers, bases = np.float32(centers), np.float32(bases)
    points = CELLS @ bases + centers[:, None, :]
    levels = _sample(gray, points)
    border, data = levels[:, BORDER], levels[:, DATA]
    ink = np.median(border, axis=1)
    white = np.sort(data, axis=1)[:, -3:].mean(axis=1)
    threshold = ((white + ink) / 2)[:, None]
    lookup = (data > threshold) @ WEIGHTS
    ids = WORDS[lookup]
    contrast = white - ink
    possible = np.flatnonzero((ids[:, 0] >= 0) & (contrast >= MIN_CONTRAST))
    if not len(possible):
        return []
    edges = border[possible]
    supported = (edges > threshold[possible]).sum(axis=1) <= 2
    deviations = abs(edges - ink[possible, None])
    supported &= (deviations > 0.35 * contrast[possible, None]).sum(axis=1) <= 4
    hit = possible[supported]
    # Prefer the pose with well-separated cell classes for a given physical candidate.
    strength = abs(levels[hit].astype(float) - threshold[hit]).mean(axis=1)
    return [
        (int(ids[j, 0]), centers[j], TURNS[ids[j, 1]].T @ bases[j], float(w))
        for j, w in zip(hit, strength, strict=True)
    ]


@lru_cache(maxsize=100)
def _transitions(code):
    bits = PATTERNS[code]
    cells, axes, signs, lines, ends, held = [], [], [], [], [], []
    for axis in (0, 1):
        sequence = bits if axis == 0 else bits.T
        for i, j in zip(*np.where(sequence[:, 1:] != sequence[:, :-1]), strict=True):
            mid = (j + 1.0, i + 0.5)
            if axis:
                mid = mid[::-1]
            cells.append(np.asarray(mid) - 3)
            axes.append(axis)
            signs.append(1 if sequence[i, j + 1] else -1)
            lines.append(int(j + 1))
            endpoints = ((j + 1, i), (j + 1, i + 1))
            ends.append([tuple(map(int, p if not axis else p[::-1])) for p in endpoints])
            held.append((sum(a == axis for a in axes) - 1) % 3 == 1)
    return (
        np.float32(cells),
        np.array(axes),
        np.array(signs),
        np.array(lines),
        ends,
        np.array(held),
    )


def _crossings(gray, grid, basis, center, threshold, contrast, axes, signs):
    # A leading dimension optionally groups independent poses for a single native remap.
    tangent = basis[..., ::-1, :]
    lengths = np.linalg.norm(basis, axis=-1)
    axis_normals = np.stack([tangent[..., 1], -tangent[..., 0]], axis=-1)
    axis_normals /= lengths[..., ::-1, None]
    axis_normals *= np.sign((axis_normals * basis).sum(axis=-1))[..., None]
    normals = axis_normals[..., axes, :]
    positions = grid @ basis + np.expand_dims(center, -2)
    delta = (PROFILE_OFFSETS * lengths[..., None])[..., axes, :]
    samples = _sample(gray, positions[..., None, :] + delta[..., None] * normals[..., None, :])
    profile = (samples.astype(float) - np.asarray(threshold)[..., None, None]) * signs[:, None]
    crossing = (profile[..., :-1] <= 0) & (profile[..., 1:] > 0)
    distance = np.where(crossing, abs(delta[..., :-1] + delta[..., 1:]), np.inf)
    index = np.argmin(distance, axis=-1).ravel()
    rows = np.arange(len(index))
    flat_profile = profile.reshape(len(rows), -1)
    flat_delta = delta.reshape(len(rows), -1)
    slope = flat_profile[rows, index + 1] - flat_profile[rows, index]
    frac = -flat_profile[rows, index] / np.maximum(slope, 1e-8)
    offsets = flat_delta[rows, index] + frac * (
        flat_delta[rows, index + 1] - flat_delta[rows, index]
    )
    # A crossing with inadequate class evidence near either neighboring cell is unsupported.
    minimum = 0.12 * np.asarray(contrast)[..., None]
    good = crossing.any(axis=-1) & (profile.min(axis=-1) <= -minimum)
    good &= profile.max(axis=-1) >= minimum
    return positions, normals, offsets.reshape(good.shape), good


@lru_cache(maxsize=100)
def _homogeneous_grid(code):
    grid = _transitions(code)[0]
    return np.column_stack((grid, np.ones(len(grid))))


def _pose_lstsq(matrices, rhs):
    """Solve independent affine fits with the original NumPy LAPACK operation and cutoff."""
    m, n = matrices.shape[-2:]
    if (
        _LSTSQ_KERNEL is not None
        and len(matrices) > 1
        and n == 6
        and m >= n
        and matrices.dtype == np.float64
        and rhs.dtype == np.float64
        and rhs.shape == matrices.shape[:-1]
    ):
        cutoff = np.finfo(np.float64).eps * max(m, n)
        try:
            with np.errstate(invalid="raise", over="raise", divide="raise", under="ignore"):
                x, _, ranks, singular = _LSTSQ_KERNEL(
                    matrices, rhs[..., None], cutoff, signature="ddd->ddid"
                )
            # Ill-conditioned systems and uncertain numerical outcomes retain the public
            # scalar driver, including its full rank and error handling.
            if (
                np.isfinite(x).all()
                and np.isfinite(singular).all()
                and (ranks == n).all()
                and (singular[:, -1] > 8 * cutoff * singular[:, 0]).all()
            ):
                return x[..., 0], ranks, singular
        except (FloatingPointError, TypeError, ValueError, np.linalg.LinAlgError):
            pass
    results = [np.linalg.lstsq(a, b, rcond=None) for a, b in zip(matrices, rhs, strict=True)]
    return (
        np.stack([r[0] for r in results]),
        np.array([r[2] for r in results]),
        np.stack([r[3] for r in results]),
    )


def _weak_grid_cells(gray, code, seeds):
    """Prove strict native photometric failures; other seeds retain the full scalar verifier."""
    grid, axes, signs, _, _, held = _transitions(code)
    bits = PATTERNS[code].ravel()
    centers = np.array([s[1] for s in seeds], float)
    bases = np.array([s[2] for s in seeds], float)
    homogeneous = _homogeneous_grid(code)
    active = np.ones(len(seeds), bool)
    rejected = np.zeros(len(seeds), bool)
    for iteration in range(5):
        corners = CORNERS @ bases + centers[:, None]
        active &= ((corners >= 1) & (corners < np.array(gray.shape[::-1]) - 2)).all(axis=(1, 2))
        active &= (np.linalg.norm(bases, axis=-1) * 6).min(axis=1) >= 8
        active &= np.linalg.det(bases) > 0
        indices = np.flatnonzero(active)
        if not len(indices):
            break
        values = _sample(gray, CELLS @ bases[indices] + centers[indices, None]).astype(float)
        black = np.median(values[:, ~bits], axis=1)
        white = np.median(values[:, bits], axis=1)
        contrast = white - black
        threshold = (white + black) / 2
        deviations = abs(values[:, ~bits] - black[:, None])
        limit = 0.35 * contrast[:, None]
        max_outliers = (~bits).sum() / 5
        support = (contrast >= MIN_CONTRAST) & ((deviations > limit).sum(axis=1) <= max_outliers)
        definite = (contrast < MIN_CONTRAST - PHOTOMETRIC_GUARD) | (
            (contrast >= MIN_CONTRAST)
            & ((deviations > limit + PHOTOMETRIC_GUARD).sum(axis=1) > max_outliers)
        )
        rejected[indices[definite]] = True
        active[indices[~support]] = False
        if iteration == 4:
            # Same four pose updates and final native samples as _verify. A strict negative
            # outside the one-quarter-level guard cannot satisfy its original 0.13 margin.
            smallest = abs(values - threshold[:, None]).min(axis=1)
            rejected[
                indices[support & (smallest + PHOTOMETRIC_GUARD < MIN_CELL_MARGIN * contrast)]
            ] = True
            break
        indices = indices[support]
        if not len(indices):
            break
        _, normals, offsets, good = _crossings(
            gray,
            grid,
            bases[indices],
            centers[indices],
            threshold[support],
            contrast[support],
            axes,
            signs,
        )
        designs = (homogeneous[:, :, None] * normals[:, :, None, :]).reshape(len(indices), -1, 6)
        fits = good & ~held
        counts = fits.sum(axis=1)
        active[indices] = False
        for m in np.unique(counts[counts >= 6]):
            rows = np.flatnonzero(counts == m)
            row, column = np.nonzero(fits[rows])
            matrices = designs[rows[row], column].reshape(len(rows), m, 6)
            rhs = offsets[rows[row], column].reshape(len(rows), m)
            changes, ranks, _ = _pose_lstsq(matrices, rhs)
            valid = (ranks == 6) & np.isfinite(changes).all(axis=1)
            targets = indices[rows[valid]]
            change = changes[valid].reshape(-1, 3, 2)
            bases[targets] += change[:, :2]
            centers[targets] += change[:, 2]
            active[targets] = True
    return np.flatnonzero(rejected)


def _verify(gray, code, center, basis):
    grid, axes, signs, lines, endpoints, held = _transitions(code)
    bits = PATTERNS[code].ravel()
    center, basis = center.astype(float), basis.astype(float)
    for iteration in range(5):
        corners = CORNERS @ basis + center
        if (corners < 1).any() or (corners >= np.array(gray.shape[::-1]) - 2).any():
            return None
        if (np.linalg.norm(basis, axis=1) * 6).min() < 8 or np.linalg.det(basis) <= 0:
            return None
        values = _sample(gray, CELLS @ basis + center).astype(float)
        black, white = float(np.median(values[~bits])), float(np.median(values[bits]))
        contrast, threshold = white - black, (white + black) / 2
        if contrast < MIN_CONTRAST:
            return None
        # A painted symbol has two supported photometric populations. A bright
        # specular patch amid varied grey robot surfaces can spell a sparse word
        # at the centers while its presumed black cells span most of the contrast.
        if np.count_nonzero(abs(values[~bits] - black) > 0.35 * contrast) > len(values[~bits]) / 5:
            return None
        points, normals, offsets, good = _crossings(
            gray, grid, basis, center, threshold, contrast, axes, signs
        )
        fit = good & ~held
        design = _homogeneous_grid(code)[:, :, None] * normals[:, None, :]
        design = design.reshape(-1, 6)
        if fit.sum() < 6:
            return None
        if iteration == 4:
            break
        update, _, rank, _ = np.linalg.lstsq(design[fit], offsets[fit], rcond=None)
        if rank != 6 or not np.isfinite(update).all():
            return None
        change = update.reshape(3, 2)
        basis += change[:2]
        center += change[2]
    if not np.array_equal(values > threshold, bits):
        return None
    # All 16 data cells and the four complete black sides must be supported by native samples.
    if np.min(abs(values - threshold)) < MIN_CELL_MARGIN * contrast:
        return None
    # Check the local footprint of every bit against those populations as well.
    offsets_xy = np.float32([[-0.15, 0], [0.15, 0], [0, -0.15], [0, 0.15]])
    footprint = (CELLS[:, None, :] + offsets_xy) @ basis + center
    samples = _sample(gray, footprint).astype(float)
    cell_measurements = np.median(samples, axis=1)
    if not np.array_equal(cell_measurements > threshold, bits) or np.any(
        abs(cell_measurements - threshold) < MIN_CELL_MARGIN * contrast
    ):
        return None
    reverse_id = REFLECTED[bits[DATA] @ WEIGHTS]
    reverse_only = code >= len(SYMBOLS)
    conflict = not reverse_only and reverse_id not in (-1, code)
    supported = good & (abs(offsets) <= 0.75)
    line_counts = [len(set(lines[supported & (axes == a)])) for a in (0, 1)]
    ends = [
        set(p for j in np.flatnonzero(supported & (axes == a)) for p in endpoints[j])
        for a in (0, 1)
    ]
    vertices = sorted(ends[0] & ends[1])
    if (
        min(line_counts) < 2
        or len(vertices) < 4
        or np.linalg.matrix_rank(np.subtract(vertices[1:], vertices[0])) < 2
    ):
        return None
    # Withhold entire segments throughout refinement. An absent held-out crossing fails the fit.
    if not good[held].all():
        return None
    rms = float(np.sqrt(np.mean(offsets[held] ** 2)))
    if rms > 0.75:
        return None
    transition_points = []
    for j in np.flatnonzero(good):
        xy = points[j] + normals[j] * offsets[j]
        transition_points.append(
            dict(
                axis=int(axes[j]),
                line=int(lines[j]),
                grid=grid[j].tolist(),
                pixel=xy.tolist(),
                residual_px=float(offsets[j]),
                held_out=bool(held[j]),
            )
        )
    return dict(
        id=code % len(SYMBOLS),
        pattern=code,
        center=center,
        basis=basis,
        corners=CORNERS @ basis + center,
        front_face_ambiguous=bool(conflict or reverse_only),
        grid_support=dict(
            exact_dictionary_matches=0 if reverse_only else 1,
            contrast_gray=contrast,
            threshold_gray=threshold,
            cell_values=values.tolist(),
            cell_local_medians=cell_measurements.tolist(),
            transition_points=transition_points,
            lines_per_axis=line_counts,
            supported_vertices=vertices,
            heldout_rms_px=rms,
            heldout_rms_per_axis_px=[
                float(np.sqrt(np.mean(offsets[held & (axes == a)] ** 2))) for a in (0, 1)
            ],
            reflected_pattern_only=reverse_only,
            reflection_equals_same_dictionary_rotation=bool(reverse_id == code),
        ),
    )


@lru_cache(maxsize=1)
def _island_offsets():
    """Centroids and areas of connected white islands for every dictionary word and rotation."""
    descriptors = set()
    for bits in PATTERNS:
        for connectivity in (4, 8):
            n, _, stats, centers = cv2.connectedComponentsWithStats(
                bits.astype(np.uint8), connectivity=connectivity
            )
            for i in range(1, n):
                for turn in TURNS:
                    xy = (centers[i] - 2.5) @ turn
                    descriptors.add(
                        (
                            round(float(xy[0]), 3),
                            round(float(xy[1]), 3),
                            int(stats[i, cv2.CC_STAT_AREA]),
                        )
                    )
    return np.float32(sorted(descriptors))


def _contours(gray):
    # Illuminated and shaded ink can have very different native levels. The thresholds
    # produce seeds only. The independent cell and held-out edge tests use original gray.
    otsu, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU)
    quads, islands = [], []
    for level in set((int(otsu), 96, 144, 192)):
        contours, hierarchy = cv2.findContours(
            np.uint8(gray < level), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
        )
        if hierarchy is None:
            continue
        for i, c in enumerate(contours):
            rect = cv2.minAreaRect(c)
            (u, v), (w, h), _ = rect
            if hierarchy[0, i, 3] < 0:
                if hierarchy[0, i, 2] >= 0 and min(w, h) >= 7 and max(w, h) < 1.4 * min(w, h):
                    quads.append((cv2.boxPoints(rect), "ink_contour"))
            elif min(w, h) > 1.6:
                m = cv2.moments(c)
                if m["m00"] > 2:
                    # Hole contours run through the surrounding ink pixels.
                    area = max(1.0, m["m00"] - 0.5 * cv2.arcLength(c, True) + 1)
                    islands.append((m["m10"] / m["m00"], m["m01"] / m["m00"], area))
    return quads, islands


def _inside(candidate, u, v):
    uv = np.array((u, v)) - candidate["center"]
    return np.max(abs(np.linalg.solve(candidate["basis"].T, uv))) < 3.4


def _accept(gray, seeds, source, candidates, failed):
    if not seeds:
        return
    ordered = sorted(seeds, key=lambda s: -s[3])
    codes = np.array([s[0] for s in ordered])
    centers = np.array([s[1] for s in ordered])
    bases = np.array([s[2] for s in ordered])
    ignored = np.zeros(len(ordered), bool)
    screened, weak = set(), set()
    peer_masks = {}

    def nearby(i):
        center_deltas = centers - centers[i]
        basis_deltas = bases - bases[i]
        position = np.linalg.norm(center_deltas, axis=1)
        angle = np.linalg.norm(basis_deltas.reshape(len(bases), 4), axis=1)
        nearby = (codes == codes[i]) & (position < 0.25) & (angle < 0.08)
        # At a threshold, use the original per-vector norms and comparisons.
        borderline = (abs(position - 0.25) < 1e-6) | (abs(angle - 0.08) < 1e-6)
        for j in np.flatnonzero((codes == codes[i]) & borderline):
            nearby[j] = (
                np.linalg.norm(center_deltas[j]) < 0.25 and np.linalg.norm(basis_deltas[j]) < 0.08
            )
        return nearby

    for i, (code, center, basis, _) in enumerate(ordered):
        if ignored[i]:
            continue
        if any(
            c["pattern"] == code
            and np.sum(c["basis"] * basis) > 0.8 * np.sum(basis**2)
            and _inside(c, *center)
            for c in candidates
        ):
            continue
        if code in failed and code not in screened:
            pending = ~ignored & (codes == code)
            peers = []
            for j in range(i, len(ordered)):
                if pending[j]:
                    peers.append(j)
                    peer_masks[j] = nearby(j)
                    pending &= ~peer_masks[j]
            if len(peers) >= 2:
                discarded = _weak_grid_cells(gray, code, [ordered[j] for j in peers])
                weak.update(peers[j] for j in discarded)
            screened.add(code)
        mask = peer_masks.pop(i, None)
        ignored |= nearby(i) if mask is None else mask
        if i in weak:
            continue
        result = _verify(gray, code, center, basis)
        if result is not None:
            result["origins"] = [source]
            candidates.append(result)
        else:
            failed.add(code)


def _island_seeds(gray, center, area, cell):
    desc = _island_offsets()
    ratio = area / cell**2
    keep = (desc[:, 2] >= 0.6 * ratio - 0.4) & (desc[:, 2] <= 1.7 * ratio + 0.4)
    offsets = desc[keep, :2]
    if not len(offsets):
        return []
    bases = ISLAND_ROTATIONS * cell
    centers = center - offsets @ bases
    bases = np.broadcast_to(bases[:, None], (len(bases), len(offsets), 2, 2))
    return _seeds(centers.reshape(-1, 2), bases.reshape(-1, 2, 2), gray)


def find_grids(gray, depth, focal_px, marker_size_m):
    """No frame state. Check all physical footprints, including additional and foreign codes."""
    params = cv2.aruco.DetectorParameters()
    params.errorCorrectionRate = 0
    direct, _, rejected = cv2.aruco.ArucoDetector(DICTIONARY, params).detectMarkers(gray)
    contours, islands = _contours(gray)
    candidates, failed = [], set()
    for source, quads in (
        ("direct_quad", direct),
        ("rejected_quad", rejected),
        ("ink_contour", [p for p, _ in contours]),
    ):
        seeds = [_quad_pose(q) for q in quads if abs(cv2.contourArea(np.float32(q))) >= 50]
        if seeds:
            centers, bases = zip(*seeds, strict=True)
            _accept(gray, _seeds(centers, bases, gray), source, candidates, failed)
    searched = []
    for u, v, area in sorted(islands, key=lambda island: -island[2]):
        if any(_inside(c, u, v) for c in candidates):
            continue
        z = float(depth[round(v), round(u)])
        if not z > 0:
            continue
        cell = focal_px * marker_size_m / (6 * z)
        if cell < 8 / 6 or not 0.55 < area / cell**2 < 15:
            continue
        if any(
            np.hypot(su - u, sv - v) < 0.4 and abs(sa - area) < max(2, area * 0.08)
            for su, sv, sa in searched
        ):
            continue
        searched.append((u, v, area))
        seeds = _island_seeds(gray, np.float32([u, v]), area, cell)
        _accept(gray, seeds, "internal_white_component", candidates, failed)
    ambiguous = any(c["front_face_ambiguous"] for c in candidates) or any(
        _inside(a, *b["center"]) for i, a in enumerate(candidates) for b in candidates[i + 1 :]
    )
    return candidates, ambiguous, len(rejected)
