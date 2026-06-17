# Operator Confirmation

Phase 10.2A replaces permanent operator strings with one-time
`OperatorConfirmation` records.

An operator confirmation is bound to robot identity hash, real robot config
hash, requested acceptance level, requested action, short validity window, and
verified local origin.

The raw token is never written to artifacts. Artifacts store only the token hash
and confirmation metadata. A consumed token cannot be reused. Level 0 read-only
checks may use a site session record; Level 2 and higher require a fresh
confirmation for each independent motion action.
