# Skill Cache

Phase 7 adds a persistent cache for high-level skill templates and execution statistics.

The cache never stores joint angle sequences, PWM, motor commands, servo pulses, raw low-level trajectories, or any result that can bypass `SafetyShield`. A cache hit only means the system may reuse a high-level `SkillName` and parameter template. Before execution, the system must still build or update a `TaskContract`, run contract validation, run `SafetyShield`, and resolve parameters against the current scene, robot state, and safety policy.

## Key Model

`SkillCacheKey` includes skill name, robot model, end effector, object class, task intent, workspace, parameter schema version, robot capability hash, safety policy hash, and calibration version. `skill_name` alone is never sufficient.

`SkillTemplate` starts as `CANDIDATE` and can become `TRUSTED`, `QUARANTINED`, `INVALIDATED`, or `EXPIRED`.

`SkillExecutionRecord` stores audited execution outcomes, safety decisions, duration, retry counts, scene confidence, network quality, and evidence hash.

`SkillStatistics` derives total executions, success/failure counts, safety rejections, timeouts, average duration, recent success rate, confidence score, consecutive failures, and last success/failure timestamps.

## State Flow

Templates are created as `CANDIDATE`. A configured promotion policy can promote them to `TRUSTED` only after enough successful, evidence-backed executions with no safety rejection or consecutive failures.

Safety rejection, emergency stop, repeated failures, invalid evidence, or incompatible current safety/capability/calibration state quarantines or invalidates the template. TTL expiry marks templates `EXPIRED`.

The repository supports InMemory and SQLite implementations with CAS template updates, execution idempotency, conflict detection, audit events, and restart recovery.
