# Deferred reset UTC originals protocol

This is a proposal only. Task2 round 2 does not implement it, change RawV3/current recorder, create data, or accept a reset inferred from SETTLE/sim_time zero.

`native.calibration.utc-originals.v2` would retain the complete interval-pair sample inventory and independent source hashes, and additionally carry a `reset_source` joining:

- Original reset journal path/SHA, original RESET operation ID, episode/clock domain/descriptor identity, exact reset-state hash, and source producer hashes already pinned by the app-owned acquisition catalog.
- Actual BEGIN and END ClockPairV3 originals measured around that exact RESET operation, with independent UTC lower/upper bracket originals for both pairs.
- Original successful RESET BEGIN/END journal rows and their state/operation/episode joins. The reset END must precede the first settling/physics/acquisition/action bracket in the same process clock domain. Full paired-clock content and independent UTC coverage must be recomputed; a caller timestamp, uncertainty, accepted flag or forged pair digest is insufficient.

The future reader must require preregistration strictly earlier than the earliest supported independent RESET BEGIN lower UTC bound and every allocated acquisition/action BEGIN lower bound. Equality, reversed/missing pairs, unmatched reset journal/state/source, clock discontinuity or unknown external UTC authority keeps the complete allocated group unavailable. Catalog/source validation must authenticate the actual acquisition implementation and original bytes; the public format alone cannot do so.

The current backend operation ledger lacks UTC brackets, and the current recorder skips RESET when building RawV3 intervals. A future versioned capture producer must genuinely collect these originals at the existing RESET boundaries, with unchanged accepted scene/controller/top-camera behavior, then freeze its source/protocol before any calibration collection. Existing v1 recordings and failed development prefixes cannot be retrospectively upgraded. Root reviews this protocol in a separate step after round 2 is quiet and independently reviewed.
