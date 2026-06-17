# Phase 8 验收

验收命令：

```bash
python scripts/verify_phase8.py
```

验证器会检查：

- Phase 8 imports。
- 虚拟时钟确定性。
- 网络故障注入。
- PCSC、ETEAC 和 AUTO smoke 运行。
- 目标移动和网络中断场景。
- 过期/重复/乱序命令场景。
- Skill Cache 消融场景。
- 急停场景。
- SQLite 重启场景。
- 可复现性比较。
- artifact 完整性检查。
- 完整套件启动检查。
- `pytest tests/test_phase8_*.py -q`。
- Phase 3 到 Phase 7 的验证脚本。

任一失败都会非零退出，并打印失败项名称和错误摘要。

实现期间观察到：

- `python scripts/verify_phase8.py` 通过了全部 16 项检查。
- `python scripts/run_phase8_experiments.py --suite smoke --output /tmp/... --seeds 0 --networks NORMAL` 生成了 `run_count=21`、`success_count=18`。
- `python scripts/run_phase8_experiments.py --suite full --output /tmp/... --seeds 0:0 --networks GOOD` 成功启动，并生成 `run_count=45`、`success_count=36`。
