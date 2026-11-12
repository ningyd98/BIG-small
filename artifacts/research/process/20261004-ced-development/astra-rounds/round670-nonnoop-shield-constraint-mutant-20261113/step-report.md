# R670：修复无效测试变异并完成分段验证

R669选定451项的运行以404通过、1失败停止，46项未运行。原失败不是生产读取器漏检：shield_contract_constraints将minimum_safe_height=0.0除以2，输入仍为0.0，重建的grounded合同与原合同完全一致，读取器正确接受。失败现场、日志及原顺序清单均保留。

实际gpt-6-astra在修复前生成并保存plan.md/plan.json，包含5个输入的字节数及SHA256。Root重新核对适用性后，只修改tests/test_registered_collection_records.py中的test_r643_reader_rejects_resealed_changes：约束变异增加0.001，并在重放/重封前比较规范化JSON，断言输入实际改变。此值只用于负向测试候选，不修改生产安全约束或门限。真实Shield重放allowed=True、关联摘要重算、读取器拒绝、原件恢复及全部77个变异条目保持。

限定补跑的前提全部满足：

- 其他15个基线路径字节不变；唯一变化精确匹配计划允许的测试AST差异。其余5个选定测试文件字节不变，前404项测试、模块代码、辅助函数及装饰器保持。
- 原运行日志恰好404个通过事件后失败；451个节点顺序唯一。补跑清单恰好为原清单下标404起的47项，顺序无变化、无遗漏。
- 解释器和pyvenv配置SHA未变，154个依赖元数据文件未更新，无任务安装或pytest插件/配置漂移；432个相关生产源码、配置和资产SHA全部匹配。
- git跟踪的src/scripts路径集合仍为608，无增删；这与上述432项相关输入核验口径不同。

在PYTHONPATH=src:.、PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1下使用原虚拟环境运行guarded-verify.local.py r670-continuation：47 passed in 398.36s，退出码0，无跳过或取消选择，守卫forbidden=[]。失败节点成功完成77个不变分支，循环没有提前退出语句；每个协调修改且重封的候选均被独立读取器拒绝。最终Ruff、格式、AST和diff空白检查通过，运行后16个文件SHA与验证快照匹配。

结果为451项分段覆盖通过（404项历史通过＋47项新通过）。原404通过、1失败的尝试继续记为失败；不能称为一次完整451项全绿运行。原始日志、顺序回执、守卫记录、源码快照及SHA关联保存在本地coverage-result.local.json和对应R643证据中；本摘要不是完整远端复现包，也没有第二次完整独立审查。

应用实际MuJoCo、任务模型推理、云端规划和硬件命令均为0；新增研究合格组0，v8完整组/注册表未释放，正式验收NOT_ACCEPTED。90度旋转反例仍UNKNOWN/STOP；没有放宽门限、丢弃像素或更改原始失败输入。
