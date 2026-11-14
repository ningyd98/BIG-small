# Cloud vision fallback for Molmo component diagnostics

The user selected the proposed route: local perception failure → cloud image review →
fresh local RGB-D validation → conditional simulated execution. This extends the
existing explicitly paid MuJoCo component diagnostic, not hardware qualification.

Approaches considered: an advisory-only cloud call would not recover a usable
candidate; a second vision call followed by the existing skill call would expand
the one-request episode budget. The selected implementation replaces the skill-only
call with one image-based candidate-and-skill-intent call when local grounding fails.
Cloud intent remains conditional on fresh local geometry checks. Successful local
grounding continues to use the existing text-and-numeric-geometry request.

The route is opt-in with `--cloud-vision-fallback`, and requires explicit
`--execute --component-diagnostic --allow-paid`. Reuse the selected Sol profile.
Send only original RGB and an optional bounded RGB crop, task descriptors, image
dimensions/crop mapping and the local failure reason. No instance IDs, physics truth,
raw depth, credentials or marker ground truth enter the cloud prompt. The cloud can
return two normalized image points and the existing core skill sequence, or refuse /
request another observation. Its response cannot supply metric coordinates, confidence,
depth, identity, timestamps, safety overrides or execution qualification.

The actual worker must capture a new frame after the cloud returns. Require the existing
paused-MuJoCo consistency checks (same RGB, session/calibration and bounded depth delta),
then independently associate candidate pixels and run the unchanged raw-depth grounding
and complete-contour tracker. Incomplete contours and missing depth still stop. Native
binding/configuration/freshness violations never trigger cloud fallback.

Keep at most one cloud request, four native generations, two planning phases, no retries.
Freeze the flag into the role policy and job parameters; record original failure, image
hashes, crop mapping, cloud response hash, point provenance and fresh-check outcome.
Default behavior and historic evidence stay unchanged. Software tests establish behavior;
they do not demonstrate actual cloud accuracy or improved physical success rates.
