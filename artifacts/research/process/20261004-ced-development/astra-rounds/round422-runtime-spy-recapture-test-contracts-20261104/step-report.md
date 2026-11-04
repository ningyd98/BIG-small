# R422 测试前置契约修复步骤报告

本轮按实际gpt-6-astra计划执行，规划输入42项在实施前全部匹配。基线HEAD/upstream为f63e271f56a361b43d84be5538f73efe6afce226，研究分支research/20261004-continuation。目标是恢复测试前置契约，不把22个前置失败等同于22个产品缺陷。

## 修改及不变条件

仅修改tests/test_visual_worker_execution.py的共享RuntimeSpy构造器：增加明确_local_mode=False及SOFTWARE_ONLY注释，沿用非local的durable预算。它不授予worker所有权；生产ExecutionPolicy严格type检查不改。supervision继续共享同一episode helper，没有复制替身。

tests/test_rgbd_closed_loop.py仅把安全helper的无参recapture lambda改成只接受completion关键字。原负速度-4.0、1.5上限、pre/post分支、真实shield和executor不改，没有宽泛kwargs吞错。新增test_visual_worker_test_contracts.py的三个测试经真实check_active/recapture/budget_payload/execute消费者，验证旧deadline不能刷新、非local分支不调用local时间API、completion确实抵达真实post拒绝。

两个旧文件与HEAD的精确差异已经机械核对，原22节点对应19个测试函数完整AST不变。1310个基线源文件仅两个获批旧测试改变，另新增一个测试；其余1308项及全部406个src生产源文件字节未变。40项不在修改范围内的规划输入再次匹配。

## 测试证据

25项RED（原22+新3）各执行一次：23项在缺_local_mode处失败、2项在completion关键字处失败；所有setup/teardown通过。没有把导入错误、不预期PASS或未开始节点当RED。

47个唯一GREEN节点各执行一次：execution模块16、supervision模块15、实际安全helper消费者9、legacy模式兼容4、新contract3；37pure和10个真实仓库/owner软件节点。47 STARTED，47 setup PASS、47 call PASS、47 teardown PASS；JUnit无failure/error/skip；无xfail、INCOMPLETE或自动重试。原22均包含在47内，没有额外重复执行。原测试输入/断言和参数不变，目标call通过而非仅消失早期接口异常。逐节点映射见final-integrity.json。

真实Memory/SQLite仓库、取消后owner拒绝、伪造观测、UTC租约撤销、未知mode拒绝、STOP/CONTINUE不能授权未知action等反例保持。post超速实际执行一次软件executor后，由真实shield的SAFETY_POSTCHECK拒绝；pre拒绝时不分发。native仅表示真实软件仓库/owner，未调用实体机器人、真实相机或外部模型。

GREEN JUnit累计case时间70.180秒，独立supervisor阶段累计155.278秒；不是端到端研究性能指标。每node pure cap120秒/native600秒，cleanup30秒是保护上限。72个stage均自然FINISHED、owned reaped，signals/errors/source_drift/remaining_live/ports_after为空。未用退出后清理冒称API返回时FD审计，本轮没有新的进程内FD测量。

两个旧文件diff-check与新contract文件Ruff、format检查通过。按计划没有批量格式化旧文件或重跑全项目静态治理。

## 归档发现及后续边界

测试结束后，额外本地raw复制脚本误以为每个pytest stage都会创建basetemp，在首个纯测试red-001的assert source.is_dir()失败；没有开始复制、删除或修改原件。72项测试状态不受影响。按AGENTS暂停相关归档，另交实际Astra R423行政补充计划；原AssertionError与72目录inventory保留，16个目录存在、56个不存在。该发现是采集假设错误，不是新产品/测试失败。不得造缺失目录冒充raw，也不重跑测试。最终归档处理见R423步骤报告。

原R413的35FAIL/1INCOMPLETE及R419–421证据仍保留，不把本轮47PASS减算为新的全量通过率。未重跑4751/full5580或P0测试；生产RGBD入口、未资格化性能/质量和正式研究/实体gate继续按原边界保持。

## 执行裁定

沿用用户授权的现有研发checkout、现有依赖和精确47节点，优先于通用新worktree/安装/全suite默认；代价是本轮不证明更广回归。保留所有ledger/raw优先于技能清理默认，代价是本地存储增加。通用task-done会重跑已完成节点，因此采用保存的有界节点结果作为完成记录，保持25RED+47GREEN零重试边界；代价是没有额外广域验证。研发分支提交/推送是AGENTS已指定的交付方式，不进行main合并或另询问集成菜单。

一次fresh Astra联合审查与选择性Git交付另留记录。完整stdout/stderr、资源/进程详单、DB与basetemp均本地保留；远端仅明确清单内代码/计划/小型终态证据，不是完整远端复现包。

R423归档收口：实际Astra11输入复核后，一次执行校验16个实际目录的create-only副本，459文件/17,266,800 bytes匹配；56缺失仅记录ABSENT_OBSERVED，不推断历史或造目录。72 validation树和原件身份/内容不变；清单及完整raw/DB local-only，未重跑测试。详见R423 step-report.md。
