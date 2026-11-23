# 独立开发实例的注册观测与动作时序补轮

gpt-6.2-astra / 2026-11-23 / bdb8bd415bc94cb431b4229c625eed13e82a1c48

r1开发入口在真实注册交接后重复取了同一步的新帧，首个MOVE_ABOVE在grounding即停，未到达真实准入和Shield。后续动作边界有同型重采风险。

## 原始证据及根因

- 冻结r1唯一已用视觉ID graduation-dev-dynamic-r1-20261123/r593-guarded、seed 23110101、SQLite job-ae1e926097a44ad6/attempt1/FAILED，已释放租约。分配SHA 2db14d49d4fb6715828511d511c82c6153a320a920a233a1d4654ede31ea2cd8；回执SHA 172227c19982ab87c1e9f96760c4d4ec27228042784940099a5e9341fdde20c7。像素共5帧：reset 0、bootstrap/handoff/首个PRE请求/terminal均120。后四项的采集身份各异；step0/120均可估计目标。
- 原栈在registered_collection_step_v2报registered collection geometry unavailable: capture_not_new_and_monotonic。实测0次准入、0个Shield、0次控制派发，原public分类、终止和安全停原样保留；补充归因为开发适配器调用时序。
- 注册对象tracker对同一ID且同checksum允许重验；新ID须同时严格推进采集墙钟和模拟时间并通过来源、TTL和重放检查。OpenCV颜色tracker有相同跨ID时间规则。Servo另有自身规则：reference初始化后第一次反馈可同物理步但必须新ID、不倒退墙钟并且帧鲜；后续反馈要求正模拟时间增量，漏帧超时照旧拒绝。

native应用将新的同一步handoff帧同时作为颜色与注册tracker的当前参考，再将同一观察传给第一步编译/Shield/条件；r1颜色tracker仍引用bootstrap，新拍的首个PRE又不同于handoff。原native session返回唯一terminal观测供本步POST和下步PRE使用。适配器在dwell终点及下步PRE再拍会再次制造等模拟时间异身份。

## 新开发分配

唯一身份 `graduation-dev-guarded-clock-r2-20261123/r593-guarded`，seed 23110201，一次、零重试，零正式claim。

### 1 冻结旧代与隔离

- [ ] 对上表所有r1原件和Git原始逐字节复核，私有目录逐项比对原final-private-manifest，全库仅从冷副本或immutable读取。r1使用bdb8bd415bc94cb431b4229c625eed13e82a1c48及其父级和既有input指纹独立复现；保留实际旧脚本/测试Git blob、源清单与登记SHA。用独立r2诊断模块/配置入口与测试复用可复用代码，不原地覆盖r1已登记实现或物理样本。旧canonical六项不重跑。

### 2 修正规定的采集角色

- [ ] 维持step0独立只读估计，实际120步settle后真实bootstrap用于构造原始契约；保留同一物理步的第二次真实、不同身份handoff并由validate_registration_handoff核验。仿照正式采集应用的_handoff_registered_capture，用handoff重建颜色tracker/伺服实际参考evidence及注册tracker；编译时的bootstrap证据另存。将handoff原观察、同一episode/step/id/sha严格传给第一次registered_collection_step_v2、PRE预览和原颜色/条件/Shield，禁止为这几个消费者分别capture。真实派发前在合法活性窗口内重验同一原件，过期立即停。

### 3 后续边界与伺服

- [ ] 为8阶段维护当前观测引用/实际物理步账本。POST采用真实控制返回/已完成dwell终点的唯一terminal采集，下一步grounding/PRE引用同一终点而非新拍。若dwell结束已有同一步原帧可直接采用；若无则在真实推进到终点后只采一次。不同真实阶段无运动时遵循各来源相同帧重复核验语义；确需不同ID时只在既有控制/保持预算内、且生产接口本来已推进的物理步上采集，记录实际步数；禁止凭空增加一步绕开期限、修改墙钟或赋新ID给旧帧。给OpenCVServoFeedback独立记reference与新反馈：首个反馈由原native servo调度采集新ID，其他反馈依原规定deadline推进；不得把servo单独允许的首次零步差传播到注册tracker或颜色facts。记录回调耗时及实际频率、动作dwell、POST、终止以及未发生的路径。

### 4 先做可定性的软件与真实来源验证

- [ ] 先对旧调度在真实tracker同一步异ID路径记录预期RED。用实际产品bootstrap、registered_collection_step_v2、evaluate_registered_conditions_v2及research_safety_shield，配备真实注册源、独立SQLite测试owner及新鲜原始RGB-D，验证相同handoff通过grounding并产生真实首个PRE条件和Shield回执（无需允许派发）。可另起明确的无派发软件夹具采新鲜开发单帧，或使用原生产归档replay及其实际评估时钟；不得篡改归档原字节、伪造回执或将历史墙钟改作实时。旧基线不同ID同一步拒绝、同ID改字节、过期、跨episode/回放、错误handoff与POST->PRE交接、正常后续步/反向步、servo第一次同一步独立新ID及后续重复拒绝分别钉断言。验证八动作预定消费者序列的结构与真实生产reference语义，并按实际来源标注逐边证据；采用现有软件正控核全链时不能报为闭环成功。若开发测量的PRE有真实UNKNOWN/FAIL，不改判据，不用teacher专属例外生成准入。

### 5 签发r2与执行

- [ ] 完成上述零派发验证、ruff、相邻真实源码专项；复核本计划两文件SHA、旧归档版本、r2最终代码/测试/读回SHA、456项显式v4源明细、相机及标记资产、发布ID/seed全局无占用、≥1GiB、EGL可用、新私有目录、原60分钟墙钟限制。签发只含这个新ID的一次性开发登记并验证排他目录创建/无可复用claim。使用原选择的守卫、八技能顺序/预算、顶视320×240、原阈值与原相机/控制器；零任务模型/外呼/硬件/正式claim/研发重试。保存原始时序表、契约、实际候选/PRE和Shield拒绝原因或真实动作全段、步步物理真值另存封存，两遍只读评分。异常即保留最近边界及未运行分母，不另占身份。

### 6 验收与论文回填

- [ ] 在r1与r2分栏列真实采集数、派发、候选、PRE/POST与Shield、待验证阶段、像素/真值时间及0.5s/1s实际可评价窗口，软件夹具、真实开发组件、正式资格分列。若真实PRE因未校准深度/运动界或其他原门拒绝且证据可追溯，明确具体缺项，不拔高为已证明方法收益。若未到PRE或发生其它异常，诚实标记新的工程阻塞、保留原始证据，再由Astra计划处理；不得把编程异常称为科学边界。生成补轮报告/阶段总结与公开摘要，登记原件SHA及本地/上游/远端三SHA。

## 边界与验收

- 修改范围为新/独立的毕业诊断入口、测试、公开小结和现有论文版次的实测数，不改产品src、原正式配置、物理步与墙钟语义、源校验/新鲜度、登记合法性、条件阈值、拒绝或safe stop。若新增入口复用旧类，应以可核验适配替换时序，三个关键边界以上基线代码路径永久保留。
- 成功标准为修复时序能够实到首个真实PRE并如实确认原条件与Shield的结论，或保留可定位的新阻塞；冻结v10正式UNKNOWN与其它八组NOT_RUN不因本轮改变。

## 已核对输入

| 文件 | SHA256 |
| --- | --- |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-dynamic-qualification-20261123/plan.md` | `0e7f20762677a0e4f52be44f4add46316efe3ff3a70aa34866ddf35b6c54f195` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-dynamic-qualification-20261123/plan.json` | `566581347e15ab63ab58be0d78c0fca6b2a104044f29d0cf2601772d2cb95f8b` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-dynamic-qualification-20261123/allocation.public.json` | `70cff51801d68231284c0939c4715fbb17bbc0b5e534b8499e7e129853e2cb02` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-dynamic-qualification-20261123/allocation-vision.public.json` | `2db14d49d4fb6715828511d511c82c6153a320a920a233a1d4654ede31ea2cd8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-dynamic-qualification-20261123/vision.public.json` | `11e0400a0a10787f130fc8b63668e2835f4f2e807c6412346ed4fc837263ad25` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-dynamic-qualification-20261123/physics.public.json` | `0cf71541253c36086e0bc5c5482f3d31d4c58d0a610471d0ecdef7a51f973e06` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-dynamic-source-catalog-20261123/plan.json` | `65e284aa34ed8135fdf776a5198021755b27caa50de456689433c38dde27cf0e` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/run-receipt.json` | `172227c19982ab87c1e9f96760c4d4ec27228042784940099a5e9341fdde20c7` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/final-private-manifest.json` | `527f2daa3b922e4f15119c8cf9b30b92439c824237eb9ca3fe3346648fb2dfb2` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/r593-v4-source-inventory.json` | `d53265be1210528e58962aee6568cf4d73a32553256032077a06e19b70068d13` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/independently-replayed.json` | `11e0400a0a10787f130fc8b63668e2835f4f2e807c6412346ed4fc837263ad25` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/instance/pixel-index.json` | `fcea744c9460b9c9fd953a2a2ce6668c3519dc20c13a049ecbba3f3642da9321` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/instance/acquisition-seal.json` | `0cd00e7b50570a874e109fde625d3b79a89d4ffba2fc2e7d72eeaab626f9d36d` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/instance/decision-seal.json` | `ea07ece5328e430e20619ce1ba72f9ebda77e75024f8e5796614ed51a6739333` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/instance/online-audit.json` | `7210ed1b247a61e80de12e279f0a0c93cc6c24124a1439e55606e07c4e974e51` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/instance/run.json` | `34345f4e252c719cb4238d99eeb2c38428a8d8d7e3eb43f182b50957d2e78878` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/instance/development-worker.db` | `4098c2c7a2ed4924053b4c20592527f29a054911caffae19decfc338ffa450ab` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/instance/offline-truth.json` | `506b3d266aacc007fa7686bf8615efd52325095a108ef4556b1b32519ca48332` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/instance/decisions.json` | `18ff8275be4527dfc8b1c2d533a56eec7c392293619f9132394f9028d77bbac1` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/instance/frames/0000.json` | `600202b3f60c1f95ca177830df2f5735e5bf12bd4168915b787f6cef54355a1e` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/instance/frames/0001.json` | `001447464e7c1221fddcf12135a64f03b04c10cb8db419506039441c8cd7cd79` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/instance/frames/0002.json` | `4fe19ed0e103d07e9fba2a99fa3bf4a21dbd07d75a7429bd3c619e0f8c95aca3` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/instance/frames/0003.json` | `ac5ead1c22ee1c6fa6afb14f2c12a2dbbe00cd51eb528bd40688a1aadfd484e5` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/instance/frames/0004.json` | `d19499e1c1b19d9bd27e42b4325d909abcf8a8a6e26412f89932633346afa99c` |
| `scripts/graduation/dynamic_vision.py` | `f706592a26b5d05f591c052d4d25104608110656e578b96759ad750f0b956064` |
| `scripts/graduation/dynamic_vision_score.py` | `8840134a3aef3591c2fe757b12203ec5685cea9a185620aeac3dc07fb88b48ef` |
| `scripts/graduation/perception_io.py` | `d27f404c0cf66c9996bbf0cc4f4636575f47f96150847fa8a396127ddeda0f99` |
| `tests/test_graduation_dynamic_vision.py` | `ad897df4391bec226aac0103e18c717b95eb33cf0ffbf35ca14eb1ebf9a5f119` |
| `src/cloud_edge_robot_arm/research/native_collection_application.py` | `f878b74e43f1315df3fdf6385c0d7199fe4e7ca1cd60776ccf2c413e1e61bfb5` |
| `src/cloud_edge_robot_arm/research/native_collection_grounding.py` | `720a999f2e7b349eca2adad055fd69eb31e634c013aa8dee3cf4c208ac188204` |
| `src/cloud_edge_robot_arm/research/native_full_horizon_originals.py` | `408502ad0f4cd59dcd3d348a6d1642f2c13a7779df68371dc86e42de74179528` |
| `src/cloud_edge_robot_arm/simulation/mujoco/native_horizon.py` | `d52d7a612544cbddde4a42ba0a2c1e827db2ed12d80f75b29f952e43cc5d38d3` |
| `src/cloud_edge_robot_arm/simulation/mujoco/visual_servo.py` | `71218ee666b8b90772cc9e3a03bab93c45c57d3ae6017c8ec734e9dd3fb13ff8` |
| `src/cloud_edge_robot_arm/vision/servo.py` | `5532047540e1ae2871031a0df24e12fa533c52f2c355681d80858b6af6f297e2` |
| `src/cloud_edge_robot_arm/vision/tracking.py` | `9c8cf00659dd3542d21f108df21a1880b3b540d07e9fd2fcd7ce020a1d6d876b` |
| `src/cloud_edge_robot_arm/vision/registered_object_tracking.py` | `537705727cbaa4aaad6b89d54d0494989cb21b1df01afde63cb073a7f6523a40` |
| `src/cloud_edge_robot_arm/vision/owner_registration.py` | `17ccc6ea0c6e3095e77a37880b4fcbc7448eef88ecf94813369e5daaff28a43a` |
| `src/cloud_edge_robot_arm/edge/evidence/conditions.py` | `9583d8330ead52c68632c5ed63e8fb302044ca5b0ccbd8c5b5bf9cd064cbdddc` |
| `src/cloud_edge_robot_arm/edge/safety/shield.py` | `e2afac8c9f2e06270b9975562842d56177d2aa9ed05b833f0126f64951156cf9` |
| `tests/test_native_registered_admission_replay.py` | `ceada96a5ede83e3b7a16740865a7c0e93a88cd7616bd635d76a759c9c2cb644` |
| `tests/test_registered_collection_execution.py` | `f949dfdf9bdfa245d2304d431641e7d24ff1eb35893cd5fb711c3b4a27928bb1` |
| `tests/test_native_collection_grounding.py` | `28ce1f4e3b4c57bc1748afb4051527bb7f20a2f85f86ba2b283939576636ac12` |
| `tests/test_visual_servo_control.py` | `6dda4a6cf64587008aca9ca102c73acc0bff3a6fbff34d4fffbb2828548b6bbc` |
