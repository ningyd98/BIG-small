# 开发预检回执与物理计数负控补轮

gpt-6.2-astra / 2026-11-23 / bdb8bd415bc94cb431b4229c625eed13e82a1c48

未签发r2的本地预检暴露开发模块引用错误和层级混淆的负控。须恢复真正的Shield判定序列化并验证动作与读回字段的正常入口。

## 原始失败与原因

- Ruff报guarded_clock.py:363 F821未定义plain、guarded_clock_score.py:10 F401未用sha。实际无派发PRE抵达Shield返回后于plain(verdict)抛NameError，完整采集没有因此形成科研门拒绝。另次保留5通过、1失败、1未选择；失败将真实builder(True)错误预期为PHYSICS_STEP_INVALID。
- 产品SafetyContext.physics_step注解为int|None且没有strict设置。已独立对实际注解TypeAdapter确认True→1(int)；在独立只读探针把bool原值直接保留给原StepTimeoutRule._evaluate_physics_window，结果PHYSICS_STEP_INVALID。新增真实builder回执明确None/−1拒绝、True被规范化到1并返回STEP_TIME_OK，开发absolute_step在builder之前严格拒绝。两层约束应在各自真实入口分别核验。

## 实施步骤与验收

### 1 修复模块与分层负控

- [ ] 先验证三源码/五原件及前两轮计划SHA，保留快照。只将新适配器的序列化调用接回已导入且已有使用的r1.plain(verdict)，移除评分脚本确实未使用的sha导入。限r2诊断、评分、对应测试及证据；不修改原产品模型/原规则、r1文件或登记阈值。用实际三项PRE、真实Shield和真实采集源跑到完整审计JSON，核对同一帧、三个条件、规则reason/allowed/limiting_rule、relative=0；不能只测试工具函数或吞掉NameError。

### 2 校正测试并增加防退化

- [ ] 必须同时验证三层：①开发ActionClock初始化/position/dispatch/return对原始True/False、None、小数、负数在进入Pydantic/原Shield前拒绝（包含非法绝对原点与当步；可用不允许调用builder的计数器证无后续调用）；②真实SafetyContextBuilder.build→原pre/post路径记录True实际变成type int的1、规则STEP_TIME_OK，同时0及1正常、不足字段None/负数按规则拒绝，保存输入/输出类型；③从同一有效真实上下文用不验证字段的model_copy(update={"physics_step": True})作为明确的原始规则负控，确认保留bool再调用原StepTimeoutRule.evaluate或原pre_check，要求PHYSICS_STEP_INVALID。另保留宽限边界terminal/terminal+1、坏horizon、跨动作错原点、首反馈0/后续8和POST反序。严禁删去布尔负控或强制int(raw)。

### 3 正常入口跨层回执预检

- [ ] 用隔离的无硬件、无真实技能派发夹具，分别走开发executor包装、原SkillRegistry参数验证、StepExecutionResult精确类型/身份、内层ActionResult.details及error_code、后端真实_command_records字段契约和最终评分入口。优先从已有冷存真实回执/原产品类型取样；使用录制返回的适配器时明示SOFTWARE_ONLY，0次新物理技能，不算r2实例。覆盖真实程序预期的成功/控制失败/无action_result、错误任务/skill/attempt与缺字段拒绝，以及accepted/rejected/hold/stop/零命令。读取type、accepted、reason、command_seq、episode_id、physics_step，验顺序、同episode和动作区间；分列executor_entered、实际命令数与accepted类型，不能把停止命令或进入executor记为成功运动。全八种技能的PRE/FEEDBACK/POST和无servo阶段按前轮时基/真实合约复查；跨阶段身份、伪时钟、LIFT实测详情缺失、RELEASE尾部不足各应拒绝。

### 4 独立评分、异常分类及签发

- [ ] 用软件夹具将正常/被拒/仅进入但未派发/已入executor后失败路径的实际字典形状提交给同版评分CLI，覆盖终止时无POST或无controller_return_step的可判与不可判字段。做一例明确NameError/KeyError/未预期ValueError的工具级反例，保存异常类型、栈、步骤、最后一次真实判定，公共摘要须记工程阻塞；不得仅凭源文件在src内或广泛捕获异常就认为研究门拒绝。只有原生条件/Shield或控制回执的明确理由可分类为该层真实拒绝。保存修前失败、修后命令/退出码，两次Ruff/专项（或一次最终完整调用），上一轮约定的真实源无派发综合测试与独立语义回读均通过后，绑定最终三个源码SHA、新旧计划及软件回执、查无r2分配/instance，再按父计划签发唯一的r2开发身份和seed 23110201一次、零重试、零外呼/正式/硬件。真实执行中若程序异常，要留新原件并另行Astra，已耗身份绝不重启。

## 范围和运行前置

- 本轮改变新开发适配器命名引用与验证层级，不更改产品schema、布尔约束、阈值、时钟、动作窗口或安全控制。若综合预检揭示新的独立根因，保存证据并新开窄轮，独立工作不受影响。
- 输出补轮计划/步骤报告、公开精简验证及父阶段汇总；真实r2是否合格、正式首组UNKNOWN及剩余八组状态按原科学口径记录。

## 输入指纹

| 文件 | SHA256 |
| --- | --- |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-guarded-clock-20261123.z5eyfnzy/guarded-clock-r2/physics-context-ruff.log` | `3ff3acdcc97a6c44c007503fd14ebe15570ce778c127a2bc9d6c54acb796fc95` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-guarded-clock-20261123.z5eyfnzy/guarded-clock-r2/physics-context-software.log` | `ab0bcd23e1a7dd982b3b73226fb491718d9a309da7a33b871ffcca319dab8f03` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-guarded-clock-20261123.z5eyfnzy/guarded-clock-r2/physics-unaffected.log` | `0aec8b43aaec43c2716faf63a230b12fda10f09e6e789322518c186d246c6b95` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-guarded-clock-20261123.z5eyfnzy/guarded-clock-r2/bool-context-layer-readback.json` | `380ce24b48ee5d8df8996a6e263adfa7c2ae42819875f9056f2213cd9bfa9260` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-guarded-clock-20261123.z5eyfnzy/guarded-clock-r2/before-receipt-adapter-fix/snapshot.json` | `7485c2c9e594387b0299024487dced989a05361c5b0494d37244656f8b55bd52` |
| `scripts/graduation/guarded_clock.py` | `8b562e242e1c4487ba8d0632262ca6a9df9e9b73922b038099c106f70b20f06b` |
| `scripts/graduation/guarded_clock_score.py` | `95a2903e1963919ec9bbf3696a31f7d081499be999e2d920da2ec608846c7d96` |
| `tests/test_graduation_guarded_clock.py` | `b82315a579b30b51125a61c2fa2c667a10d74651e02c4b7b8ff3304640c98091` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-guarded-physics-context-20261123/plan.md` | `75f84a287ac24c8835baba8c9301d5b81cc9ab21b9fdb6db1e4466d7b5e6a202` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-guarded-physics-context-20261123/plan.json` | `791f1e55eca3c1b5520ceca70839c4bf76de6b9137f2ef5f428846677a4d925c` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-guarded-clock-20261123/plan.json` | `29abdf1f14f20ac8c9b3de6df9241fb9641def256f60fc4dce0c1de627b9038d` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-guarded-clock-20261123.z5eyfnzy/guarded-clock-r2/shield-preflight-failure.json` | `fb7142528f3c4c3c249d69e980479d07938c461e3092ad32a45bf9002924cc63` |
| `scripts/graduation/dynamic_vision.py` | `f706592a26b5d05f591c052d4d25104608110656e578b96759ad750f0b956064` |
| `scripts/graduation/dynamic_vision_score.py` | `8840134a3aef3591c2fe757b12203ec5685cea9a185620aeac3dc07fb88b48ef` |
| `scripts/graduation/perception_io.py` | `d27f404c0cf66c9996bbf0cc4f4636575f47f96150847fa8a396127ddeda0f99` |
| `src/cloud_edge_robot_arm/edge/safety/models.py` | `9597cecf9ff02c1909f705353820901aaa4219b5f71083e89b082f11f1c2d135` |
| `src/cloud_edge_robot_arm/edge/safety/rules.py` | `0582a5345328f4a49ef18dcaa51474ff99f8da7759ffe7cfce0cbdd53a5a0115` |
| `src/cloud_edge_robot_arm/edge/safety/context_builder.py` | `4615404f4259210fca1b7218cc9e5a1dc683721f0218367083a957bf41396bed` |
| `src/cloud_edge_robot_arm/edge/safety/shield.py` | `e2afac8c9f2e06270b9975562842d56177d2aa9ed05b833f0126f64951156cf9` |
| `src/cloud_edge_robot_arm/edge/runtime/skill_executor.py` | `d0ecfd4a5616b5404524554224280376e3f2dc56670417ce05e35c82aa648bc2` |
| `src/cloud_edge_robot_arm/edge/runtime/skill_registry.py` | `2cd6c6db8170778d19ecf46fc16f827df9f1809b919c1574b570349d3774df92` |
| `src/cloud_edge_robot_arm/contracts/models.py` | `d9b3888fca6bb46c62326c9bf5fd49cf4c646ce21cf29994315107bf41d79464` |
| `src/cloud_edge_robot_arm/simulation/mujoco/backend.py` | `4d6dd9e0b92efab1b3895aa66473cb739e46558b3b47260caeec114a638f7bf4` |
| `src/cloud_edge_robot_arm/vision/native_completion_horizon.py` | `7a0337c8a44e1d63188957a421dc10a49f4b80b47719d6e9d5a2d5e1382bf0a3` |
| `tests/test_native_registered_admission_replay.py` | `ceada96a5ede83e3b7a16740865a7c0e93a88cd7616bd635d76a759c9c2cb644` |
