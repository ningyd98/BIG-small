# Phase 7 验收

运行：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python -m pytest tests/test_phase7_*.py -q
python scripts/verify_phase7.py
```

`scripts/verify_phase7.py` 检查：

- Skill Cache SQLite 重启、晋升、作废。
- 缓存命中不能绕过 SafetyShield。
- 风险快照确定性，以及缺失输入 fail-closed。
- AUTO 决策矩阵。
- 驻留时间、冷却和切换次数限制的防抖。
- 模式切换 prepare/commit/abort、CAS 和幂等。
- SQLite 对 prepared transition 的重启恢复。
- Phase 5 和 Phase 6 双模式回归。
- 生产 profile 阻止 InMemory、mock 和未配置 AUTO 路径。
- 配置前不对外声明 AUTO 能力。
- 生产源码扫描占位符和绕过路径。

任一检查失败时，验证器返回非零，不吞掉子进程失败。
