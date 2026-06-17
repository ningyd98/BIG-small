# Sim-to-Real Evaluation

Phase 10 prepares paired simulation and hardware result schemas. A valid pair
must reference the same task contract hash, software commit, simulation backend,
and real hardware backend identity.

Required metrics:

- planning time
- actual execution time
- TCP trajectory length
- final position error
- skill duration
- safety interventions
- retry count
- success rate

Reports must separate model, perception, control, timing, contact, and friction
gaps. Mock, MuJoCo, Isaac, or dry-run results cannot be used as the real backend
side of a pair.
