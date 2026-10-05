# T13 dependency window — software subcomponent

The immutable dependency graph propagates invalid evidence through dependent steps,
replacing only unfinished affected steps. Completed effects and unrelated unfinished
steps remain preserved. Duplicate effects cannot be renamed into new replay steps;
missing, cyclic, forward or duplicate graph identities reject. The result is a
candidate description and does not dispatch, activate or resolve a recovery event.

The planned StepDependency contains no plan state; find_repair_window therefore adds
optional keyword expected_plan_version/expected_command_seq and rejects omitted
versions rather than inventing them. RepairWindow copies its identities and binds
these exact versions. Fresh completed-effect verification, compensation, actual
SafetyShield/submit validation and lifecycle/activation belong to the remaining T13
integration. LOCAL_RECOVER stays disabled.

Initial RED: 13 missing-module failures; added effect-identity regression also failed
before correction. Final 14 tests, scoped Ruff and mypy exit 0. Commands and output,
two source copies and exact hashes are archived. Independent review PASS covers
these two files only, including 4096 CPU reachability checks (review.md). No cloud
request, physical recovery, G4, full T13 DONE or accepted research result is claimed.
