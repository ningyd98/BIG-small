# CPU 原帧基准的单来源绑定与静态修订

原计划全部 29 个直接输入与 1,212 个帧文件在动工前逐一对上原摘要。首次预检运行前，独立开发改动了共享工作树的 `native_checkpoint_diagnostic.py`。前置保留原退出 1，同时核对已冻结源和 Git 对象的原文件，三者记录如下。

| 来源 | SHA256 |
| --- | --- |
| 父计划、实际运行冻结副本、Git 1c50c2d7 与 902c2702 | `a1c22853004ddddcbc12bdd3c4726d2dc54f7925fe6537d37c6887b5e965073d` |
| 第一次失败时的共享工作树 | `b83983a9a76e20b25fbc7f2f2dc8041f0ee3bd8810704d66cd8cb756cdbc4d15` |

新解析仅允许 `inputs_sha256` 中的该确切键及确切原 SHA 使用历史冻结副本。其他直接文件、所有帧文件、原件库存、保护清单和实际导入仍按原条件验证。未使用导入 io、datetime 机械删除，未用循环绑定更名。产品与父计划文件原字节保留。

定向 RED 2 个预期失败、10 个通过。实现后 12 项软件正负控通过，Ruff 通过。首次实际 preflight stderr SHA256 为 `a9e3803d87b973aa9d61bbc35d336c56d066ff5f361932474c3dfcb14e4f6718`。定向 GREEN JUnit SHA256 为 `4d57eef6d3dade65d11e13a5f194e341d57644a18a82d06c911ab526c3419474`。复验的真实输入预检和 242 份默认 level 6 载荷基线退出 0，预检 stdout SHA256 为 `2b7f4149f31c929c72b2e77647e558950465680598334584bcc99f3820ddd4a5`。12 项软件验证只支持来源映射与负控，实际计时和资格见父轮独立报告。

私有原件在 `experiments/results/phase9/p0-teacher-action-window-benchmark-20261120/`。
