# 源漂移负控夹具修复

复核了 Astra 计划、三个源码输入和两个私有原始证据的 SHA256。使用项目 Python、候选工作树的绝对 `PYTHONPATH`，以及进程启动前设置的 `MUJOCO_GL=egl` 和 `PYOPENGL_PLATFORM=egl` 复现。四个定向节点在修复前为 1 失败、3 通过。第二个源漂移节点在 `collection_body` 阶段因测试桩不接受 `diagnostic` 参数而提前返回。原始运行回执和 stderr 保留在本地。 [原始失败](red.public.txt) · [回执 SHA256 与字段读回](fixture-readback.json)

`tests/test_native_single_teacher_release.py` 的流程测试桩采用与调用点一致的关键字参数，并断言 `diagnostic is None`。原测试仍检查两个源读取关口、零动作派发、零完成动作、资格为 `UNKNOWN`、未准入及 owner 清退。两个产品输入文件的 SHA256 与计划一致。 [实施计划](plan.md)

四个定向节点复验通过。两个源漂移节点分别在 `preflight` 与 `collection_body` 报出预期的 `synthetic source drift`。包含完整单教师测试文件的六文件回归共 313 个节点，294 通过，19 跳过，退出码为 0。四个定向节点均在构造 EGL 渲染对象前停止。本轮未启动真实采集。 [定向复验](green.txt) · [六文件回归](suite.txt)

对测试文件及 `native_collection_application.py`、`sqlite_repository.py` 分别运行 Ruff 和 `mypy --follow-imports=silent`。忽略行号偏移后，Ruff 前后各 89 条，mypy 前后各 129 条，诊断内容与出现次数相同。 `git diff --check` 通过。 [静态检查对比](static-check-comparison.json)

本轮验收范围是软件负控可达及邻接回归。真实动作耗时、实际停机效果和正式研究资格均由对应证据轮记录。
