# R01 independent local actual/offline review

Decision: **PASS_SCOPED_LOCAL_ACTUAL_OFFLINE**. The retained originals and saved offline results support completion of this single excluded development capture/offline pipeline. No new qualified data defect was found. This is not a native, UTC, calibration, full-visibility or formal acceptance.

## Original identity and denominator

The supplied terminal process facts are capture session 75370 exit 0 and offline session 60356 exit 0; their complete original summary/terminal and saved VERIFIED offline result agree. This review did not rerun either process. All **4,829 raw files / 519,937,924 bytes** match the inventory by streaming their compressed SHA, with no extra, missing or changed file. The **32 live and 32 archived sources / 440,598 bytes**, **21 environment pins**, pre-model runtime record and three already-reviewed V3 sources still match. The prior 90-case suite was not repeated.

The two saved JSONL files each contain exactly **4,807** rows, ordered steps 0–4806. Every step, sim time, episode, observation ID, checksum and raw-member identity matches across both files, the saved series index and original acquisition END. The observations JSONL retains its `NOT_REQUESTED` labels; the separate markers JSONL carries the actual saved decode labels. All 4,807 allocation/completion pairs remain in the denominator, with zero failed or missing acquisition.

Original journal `record_seq` is contiguous across **35,182** rows. Its operation identities agree with the terminal ledger; it records **743 commands, 4,806 physics steps and 9 original actions**. The action BEGIN/END/TEACHER_ACTION identity and original half-open `(start_step,end_step]` ranges reproduce the reported per-action counts exactly. The original **120 settling / 9 actions / 2 dwells** recipe is complete; settling steps 0–120 contribute 121 frames and the nine action spans contribute the remaining 4,686.

## Negative observation and physical results

Independent recount gives **4,618 OBSERVED / 189 UNKNOWN**, with **43 unknown segments**. The reasons remain 186 `known_marker_not_observed` and three `registered_marker_size_inconsistent` at steps 870, 871 and 878. Every marker stability status remains UNKNOWN and geometry/angular-velocity bounds remain unavailable. The longest unknown segment is steps 876–994, 119 frames; the observed endpoints 875 and 995 are **0.5000000040000092 simulated seconds** apart. The maximum raw sampling gap **0.004166666700001542 s** meets the unchanged 0.005 s sampling limit; it does not establish a pose-observation gap or continuous pose guarantee.

Every one of the **4,807 original journal physical_source** records was independently converted through the pure `PhysicsStepObservation` / `sample_physical_observation` data path and equals its saved PhysicalSample. `evaluate_evidence` with the original evaluation_start_step 120 reproduces the saved outcome and report exactly: **SUCCESS**, lift **0.10389920812730212 m**, hold **0.7625000060999572 s**, placed stability **2.1541666839007974 s**, and **SCOPED_NO_VIOLATION**. No backend/model was constructed and no physical step occurred during this replay. This is the retained excluded-scene physical score, not online evidence or a G1 statistical result.

## Image provenance and report scope

All **8 selected PNG SHA pins** match both the exported file and the original saved frame RGB member. The exact original gzip frame PNG bytes and identity agree; only these eight selected frame JSON payloads were read, without invoking a marker decoder. Existing PNG views at 628, 629, 900 and 995 support the report's bounded visual conclusions: step 900 has visible partial gripper occlusion of the marker's left side; step 629 is close to the arm/gripper silhouette. Pixel aliasing and a common cause for all 186 missing-marker frames remain hypotheses. The three size rejections remain unchanged. The ten original boundary images provide selected boundary observations and do not substitute for complete visibility.

The report keeps its limits: outboard-v3 development asset, **640×480 / noise 0**, custom protocol and one development component; this differs from the **320×240 / noise .001** formal domain. Source authenticity stays UNKNOWN, native admission is not promoted, and calibration-group independence, external UTC, geometric calibration, future stability, continuous motion and formal acceptance remain unestablished. Complete raw remains local; the report does not claim a full remote raw reproduction package. Recorded capture wall time is **915.764513714 s**. Decoder process wall/peakRSS and independent render-pass counts were not recorded and remain null; the 4,819 camera-delegate summary total is not a render-pass count.

## Preservation

All **111 fixed non-raw slice inputs** and all **4,829 compressed raw SHA** are unchanged before/after. No fullreader, decoder, CPU90 suite, backend/model construction, physics, renderer, provider, hardware, UDP or Git operation was performed. Code, original raw, root reports and Stage files were untouched. Active `marker-v4-preparation` was excluded.

[The JSON](independent-review.json) records scoped hashes, independent counts, action ranges and physical outcome; [the log](independent-review.log) retains the exact independent recompute script and command result. Persistent writes are only these three new review files. The local capture/offline completion scope passes while its retained negative visibility and unqualified native/formal results remain explicit.
