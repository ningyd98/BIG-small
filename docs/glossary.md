# Glossary

- `PCSC`: Periodic Cloud Supervisory Control. Cloud periodically supervises edge execution.
- `ETEAC`: Event-Triggered Edge Autonomy Control. Edge reacts to events and requests cloud help only when needed.
- `AUTO`: Deterministic selector between PCSC and ETEAC; not a third execution mode.
- `TaskContract`: Versioned high-level task message accepted by the edge runtime.
- `SafetyShield`: Edge safety layer that evaluates runtime context before and after skill execution.
- `HardwareExecutionGate`: Phase 10 gate that fail-closes real robot execution unless all hardware conditions pass.
- `Synthetic Dry-Run`: Framework-only dry-run using synthetic planning summaries; it does not claim MoveIt collision validation.
- `MoveIt Runtime Dry-Run`: ROS 2 / MoveIt planning-only run with `sent_to_hardware=false`.
- `Hardware Read-Only`: Real controller state readback without motion.
- `Hardware Motion`: Physical robot movement after sequential acceptance levels and operator confirmation.
- `artifact`: File produced by a verifier or experiment.
- `evidence`: Artifact content used to support a status claim.
- `provenance`: Source, command, environment, and hash metadata that explain how evidence was generated.
- `source tree hash`: Hash of the source tree used to bind evidence to implementation.
- `acceptance level`: Sequential real-hardware readiness level from `NONE` to `LEVEL_6`.
- `operator confirmation`: Short-lived, one-time, action-bound local confirmation for hardware actions.
- `sim-to-real gap`: Difference between simulation and real hardware behavior across timing, perception, control, contact, and safety metrics.
