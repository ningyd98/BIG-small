# Clean-capture boundary correction — software and capture only

The actual clean yellow block RGB component includes antialias border pixels that
sample table depth. Comparing adjacent depth against the deepest pixel of that whole
RGB component falsely rejected a complete visible top. The outer ring now compares
against the separately observed top mode; all original measured RGB/depth points
remain in the conservative silhouette. Invalid, nearer or coplanar neighbors remain
unavailable. No interval tolerance, color threshold or calibration bound was widened.

The immutable clean capture regression first failed with
target_outer_boundary_depth_unresolved. Final related suite: 55 passed, exit 0;
scoped Ruff and mypy exit 0. The actual tool-result record is in green-record.md;
baseline/, source/, source-hashes.json and review-package.diff preserve exact versions.
Independent review is pending. The prior noisy-red adaptation reports are retained.

A new actual capture after correction exited 0 with VISIBLE_METRIC_UNKNOWN. Its raw
files and assessment are in ../t7b-real-clean-capture-3/, with algorithm SHA recorded
at capture. Both clean captures reuse the already excluded development group
g-b5c050eaad3b86539df2065da588fe32. Model requests 0, robot actions 0, physical success
NOT_RUN. No noise is injected into this raw capture, but no validated finite sensor
bound or continuous stability evidence is supplied; metric authorization and native
completion remain UNKNOWN. These frames are not formal opportunity data or G1/G4.
