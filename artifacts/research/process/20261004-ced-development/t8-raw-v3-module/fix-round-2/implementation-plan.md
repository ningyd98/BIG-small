# Raw-v3 actual source compatibility fix2

Authorized original two files research/raw_episode_v3.py and tests/test_raw_episode_v3.py; preserve all previous artifacts. Reviewed fix1 base774 manifest67d752..., root review81f32d... CHANGES_REQUESTED.

RED/GREEN actual current+clip(target-current,-.10,.10)+bias/gain then actuator range clip, wrong unclipped output rejection; original camera captured_at within complete same-source BEGIN/END UTC nominal bracket, missing end INCOMPLETE, before/after/reversed INVALID. Preserve targets/timestamps/checksums/counts; uncertainty None remains UNAVAILABLE. Re-run unchanged root compatibility script with explicit expected statuses, original terminal/latch script, scoped original109+new CPU and static; exact774 owned2-only freeze and history/posthash. No simulator/state/step/render/capture/model/controller/provider call in this fix.
