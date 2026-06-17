# Phase 9 域随机化

`DomainRandomizationPolicy` 支持 `NONE`、`MILD`、`MODERATE` 和 `SEVERE`。采样由 seed 驱动，并持久化实际采样值、单位和来源文件。

覆盖参数包括 object mass、friction coefficient、actuator delay 和 camera depth noise。该策略不会随机化 `SafetyShield` 的硬性限制。
