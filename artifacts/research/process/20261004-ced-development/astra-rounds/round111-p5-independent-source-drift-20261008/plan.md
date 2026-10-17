# R111 P5 独立 source drift 测试覆盖修复

实际 gpt-6-astra；PLANNED_PENDING_ROOT_ACTIVATION。实现仍为原 gpt-6.1-sol。只改 `tests/test_operational_windows.py` 中原 `test_source_and_budget_changes_invalidate_window` 一个节点；九产品源、三fixture、共享helpers、其他31节点均不改。原32节点分母不扩张。

## 问题与证据

这不是新运行失败：R110新2节点真实PASS，R107原30适用复用；完整不同作者审查发现 C1，结论 NEEDS_TEST_COVERAGE_FIX。R110冻结测试:426–448 先改 job.timeout_seconds；operational_windows._check_live:310–317 检出 `_job_source(current) != s.job_source` 后 `_revoke_worker`，owner永久closed。恢复SQL值后再改临时 source_root/device.py，第二个 owner.check 在 _check_live:289 的 closed guard 即返回UNKNOWN，未执行:320–324 的 pin_worker_source_inventory。原测试因此不能独立证明文件漂移导致拒绝。master Task5 Step5 和 R100 source/budget 变化失效要求未满足动态验证；产品实际 worker_owner.py:253–290 有真实源文件SHA核对，不能据源码存在冒充已测。

完整审查 MD d66db45d8081f23f53c604630c093c269533b1471d5c796493a25c8e02c15e01 / JSON732c09b2c320d76108b78938428cdeca490770d8f8dec0a8e0e2f8a0eb21d643 原件保留。本计划保留旧GREEN/所有失败/预算，旧“PASS”是真实执行结果但不足C1需求覆盖，不改写它。

## 夹具可重复性与唯一实现方式

只读确认 `exercise` 每次创建自己的 CpuCounter/open clock list、错误/结果列表和真实 `software_factory`，并关闭 event repo；worker.poll_once 结束 heartbeat/join/release，_execute finally撤销owner。`software_factory` 首先 `source_root=tmp_path/'source'; source_root.mkdir()`，所以必须先创建两个不同case根；_queued_closed_loop_worker 用传入case根的 runtime.db，event repo也在该根的events.db，artifact_root同根。`role_binding` 的三个小源包括真实登记 device.py，非仓库产品文件。猴补丁都通过传入的MonkeyPatch安装；每个case独立context退出后还原，不把上一case的backend/runtime/counter留到下个。

在原节点内部顺序执行固定 `budget`、`source` 两个case，不parametrize、不加新测试函数或共享helper。对每项先 `case_root=tmp_path / mutation; case_root.mkdir()`（不覆盖旧目录），再 `with monkeypatch.context() as local_patch:` 调用既有 `exercise(local_patch, case_root, callback)`。callback闭包使用当前case且同步执行，不借上一owner；可用默认参数绑定mutation，避免晚绑定歧义。

每个新worker callback都必须：

1. 获取本次真实 `runtime._operational_owner`，记录 owner对象/其真实 domain.startup_nonce/独立repo路径供节点末尾核对；断言owner未closed。用既有 `event(owner)` + owner.issue 创建5s capture窗口，明确 `owner.check(...).status == VALID` 基线，保持raw counter不变。不mock check/registry/from_worker，不人为清closed，也不复用旧event/window。
2. **budget case**：保存本次数据库的原timeout值，真实SQLite UPDATE为原值+1；再次确认调用前owner尚未closed，实际 owner.check必须UNKNOWN。以try/finally恢复该case SQL原值，行身份/job_id不变。不可期待恢复值复活已撤销owner，不续期、不重建owner。该case不改任何文件或其他预算。
3. **source case**：不改数据库/任何预算/lease/origin。保存本次 runtime.source.source_root/'device.py' exact bytes，核当前SHA等于本次冻结 source_hashes['device.py']，记录当前timeout未变。try中追加固定 `b'# drift\n'` 到这个临时登记源，断言字节/SHA确实变化，且check前本次owner仍未closed；调用真实 owner.check必须UNKNOWN。finally写回原bytes并核exact相等。不得改 expected source hash、替换 pin函数、跳过source validation或用未注册文件。不得把“写回字节后可恢复live权限”增加为验收承诺。
4. 两次exercise各自仍执行已有close_call_count==1/clock.closed检查。节点末尾核两个owner对象不同、startup_nonce不同、repo路径不同，确保独立域/生命周期；不要比较或min两个域的计数。finally恢复和context退出也必须在断言失败时运行。测试自身失败保持原CPU工件与退出，不自动重跑。

该节点的 workload 为2个新鲜真实worker/2个独立临时SQLite环境，pytest节点仍1。临时device.py是明确CPU注册源一致性负控，不代表设备产品/实际模型/硬件source资格。每个case的普通factory模拟episode仍SOFTWARE_FACTORY_ONLY，不拿终态FAILED当目标测试失败。

## 精确限定与一次性命令

ROOT先核21有限pins和当前13输入，确认R110作者终态/无在途。冻结本计划后新activation；R111/implementation、green及/tmp/bigsmall-p5-r111-green必须缺席，不复用或清理旧叶。先保存原测试before，只用直接apply_patch改变上述一个函数。没有新import需求：现有hashlib/sqlite3/Path/monkeypatch均可用。

顺序及新预算各最多1：

1. `.venv/bin/python -m ruff format tests/test_operational_windows.py`（仅此NEW测试文件），保存semantic-before/format-after。
2. `.venv/bin/python <R111>/implementation/delta-proof.py`：纯stdlib AST/type_comments/tokenize/hash/JSON，不产品import、不重跑旧proof。确认唯一变化是该node；原decorators/32分母不变；所有其他函数/类/helpers/import的AST相同，全部原其他assert保留；格式不改AST/typecomment/ignore关联/注释。具体检查两个fresh exercise路径、context、mkdir先后、两个VALID基线、两单一突变+实际拒绝、finally exactrestore，不能用“assert总数增多”代替语义审查。九产品+三fixture+两legacy源码/OC1源测试配置均原SHA；生成原31实际node适用清单：R107原30去除C1=29，加R110原2=31。
3. `.venv/bin/python -m ruff check tests/test_operational_windows.py`。
4. `.venv/bin/python -m ruff format --check tests/test_operational_windows.py`。
5. `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_operational_windows.py::test_source_and_budget_changes_invalidate_window --basetemp=/tmp/bigsmall-p5-r111-green --junitxml=artifacts/research/process/20261004-ced-development/astra-rounds/round111-p5-independent-source-drift-20261008/implementation/green/junit.xml`。

环境 PYTHONDONTWRITEBYTECODE=1、PYTHONPATH=src:.；单独保存每条argv/UTC/exit/stdout/stderr，预期全部exit0。新GREEN精确1unique/1PASS/0fail/error/skip，且节点确实完成两case；保存新CPU文件清单的相对路径/bytes/SHA，raw/DB仍本地，不能只存pytest绿点就冒称两个cause分别测试。记录budget/source两个case的独立工作目录与最终测试断言，审查通过实际代码/原工件核对，不新增测试运行。

旧R110五预算全部耗尽；本计划明确新增的是上面五项，不重置历史。RED/import-sort/全32/OC1/compile/mypy/额外repro/collect/actual/network/Git/子代理均0。任何计划外失败或新根因停并保留原件；不得临时扩scope或重跑。

## 验收边界

本轮新1 + 原31适用 = P5 32 unique需求覆盖，另原60OC1仅适用复用；不是新跑32/92，旧C1那次PASS仍保留但不再作为独立source负控证据。最终必须原不同作者审查C1闭合、13输入与静态/新1原结果，之后ROOT才接受P5；不以计划或测试绿点替代独审。所有其他P5审查结论和P6/actual/native界限不变。Git仍后续严格有限路径，包含三fixture及两legacy source-before，不上传完整CPU/raw/DB。
