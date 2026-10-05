# Version-bound visual repair builder

This implements the already approved T13 candidate-building boundary. It produces no dispatch, ACK, activation, retry resolution or physical success. The existing ReplanApplyService remains the sole submission entry.

1. Write RED cases for exact dependency-window replacement, preservation of unrelated unfinished steps and completed effects, fresh-frame proof, stale versions, provider mutation and late return.
2. Build candidates from a typed, copied active-contract/checkpoint/dependency context, the actual new RGB-D observation and canonical online condition evidence. Missing proof/provider yields a response without executable steps. Recompute the window rather than trusting caller labels.
3. A provider returns one replacement for each authorized original step. Assemble the full remaining sequence using byte-equivalent copies of unrelated steps, so the existing remaining-step merge cannot silently drop them. Completed physical effects require current canonical PASS; ordinary repair cannot compensate or replay a completed effect.
4. B4 expands the authorized replacement scope to all remaining steps on the same failure/request/observation inputs, with the same preservation and safety requirements. Revalidate copied provider inputs and the clock after return. Record the original rejection logs and source hashes, run related checks and obtain independent review.

Actual Max planning and native calibrated evidence remain prerequisites. Software fixtures are explicitly software-only; no fallback model or invented condition proof is permitted.
