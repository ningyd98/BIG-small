# 安全策略文档

## 概述

BIG-small 边缘安全盾采用"fail-closed"设计：安全规则默认拒绝，只有所有规则通过才允许执行。

## 策略层次

```
硬限制 (HardSafetyLimits)
  ↓ min()
运行策略 (OperationalSafetyPolicy)
  ↓ min()
任务契约限制 (TaskContract.safety_constraints)
  ↓ min()
设备限制 (device_limits)
  ↓
= 有效约束 (MergedSafetyConstraints)
```

**关键原则**：云端和任务契约只能收紧约束，不能放宽本地硬限制。

## 禁止字段

以下参数名在安全盾中被硬拒绝：
- `disable_safety`
- `bypass_safety`
- `ignore_collision`
- `force_execute`

## 安全决策

| 决策 | 语义 | 后续动作 |
|------|------|----------|
| ALLOW | 安全 | 正常执行 |
| ALLOW_WITH_LIMITS | 部分限制 | 使用 limited_parameters 执行 |
| PAUSE | 需要等待 | 暂停任务 |
| REQUEST_CORRECTION | 需要修正 | 请求云端修正 |
| REJECT | 不安全 | 拒绝执行 |
| EMERGENCY_STOP | 危急 | 立即急停 |

## 默认阈值

| 参数 | 默认值 | 说明 |
|------|--------|------|
| max_tcp_velocity | 0.5 m/s | TCP 最大速度 |
| max_joint_velocity | 1.0 rad/s | 关节最大速度 |
| minimum_safe_height | 0.08 m | 最低安全高度 |
| max_reach_m | 0.65 m | 最大可达距离 |
| obstacle_safety_distance | 0.05 m | 障碍物安全距离 |
| scene_staleness_ms | 5000 ms | 场景数据过期时间 |
| telemetry_staleness_ms | 5000 ms | 遥测数据过期时间 |
| watchdog_timeout_ms | 30000 ms | Watchdog 超时 |

## 低高度例外

以下技能豁免最低安全高度检查：APPROACH, GRASP, PLACE, RELEASE
