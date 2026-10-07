# Round66 RW1 source contract

The original TARGET_MOTION_STARTED payload has no episode_id and is preserved unchanged. Episode is sampled separately from the exact privately bound live backend. fault_records returns copied dictionaries, so a caller-provided equal dictionary cannot authorize an event. BEGIN captures live step/S/episode plus source-list length N and exact detached prefix; END requires that prefix unchanged and exactly one new TARGET_MOTION_STARTED at N, with original event step/S identical to both live endpoint samples.

Caller arguments are equality assertions only. Startup owner, live renderer lease, canonical allocation, PID/start/boot/time namespace and bound backend episode remain fixed. Counter and source failures preserve BEGIN and prohibit successful END/retry; deadline is always b-minus + 60,000,000,000 ns and upper >= deadline refuses success. Later step/S can advance monotonically on the same backend/episode.

This CPU implementation cannot prove actual fault source or renderer provenance. No RW2/RW3 wiring, public receipt reader, alarm, v3, actual, native, suspend/restart experiment, formal acceptance or G4 measurement is authorized. Saved platform evidence is referenced without another probe.
