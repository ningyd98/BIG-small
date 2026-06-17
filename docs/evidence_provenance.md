# Evidence Provenance

Phase 10.2A evidence records source provenance separately from artifact
commits. The primary immutable source identifier is `source_tree_hash`, computed
from tracked source, scripts, configs, tests, and docs while excluding
`artifacts/**`.

Required fields:

- `generated_from_commit`
- `source_tree_hash`
- `worktree_clean`
- `diff_hash`
- `verifier_version`
- `command`
- `config_hash`
- `environment_hash`
- `generated_at`

Verifier artifacts are accepted only when their recorded source tree hash
matches the current source tree. Development evidence may be generated with a
dirty worktree, but final authority is based on source tree identity, not on an
artifact file committing itself.
