# 启动角点策略的配对开发实验

基线 004f9c837ce10fea4a3db6097c3f9abb5909d139。四个既有留出组g01/g02第120步启动帧，NONE未观察到标记、SUBPIX观察到；g03/g04两者均观察到，之后MOVE_ABOVE停止。原始帧仅作开发诊断。单帧识别是否足以过完整bootstrap、是否能改善实际闭环仍未知。

## 限定实现

在独立开发工作树检出同基线，先以SHA核对并导入已有开发runner/scorer的准确版；被冻结原树及正式采集不写。原 derive_registered_object_geometry 已有显式 corner_refinement；在 native_collection_grounding 的 collection_bootstrap_evidence→bootstrap_collection_tracker 增加仅关键字可选策略，缺省维持完全一致的 NONE 路径。为 V2 factory/constructor 的 region reference 调用与开发 Episode 启动、reset只读参考、guarded handoff 加同一绑定策略；逐个核对 native_collection_grounding 的其他消费者及 build_collection_contract_v2、条件/源生成，保留其原语义。V2 nominal provider 自身原先 SUBPIX 维持，试验的差异只落在原 NONE 启动消费者；V1、原生协议、归档回放默认不传参数。开发策略对象只接受固定 schema/version、mode、真实 catalog digest 与资产 SHA，对照 EXACT_DEFAULT(缺省),处理 EXPLICIT_SUBPIX；签发时连同胶水脚本、Python模块实际文件路径、分配、worker source generation 和每处消费模式/对应frame SHA入账。明确拒绝未知策略、错source或共享不同模式的引用。

两臂使用同一份新冻结的开发软件代际并逐项枚举、核验实际在执行的全量产品源码与开发脚本；原 catalog 仅供差异核验，不允许拿旧 catalog 冒充修改后源码、放宽 pin 或绕过正常 tracker/Shield。旧默认脚本和正式旧v9/v10继续使用归档树。允许在启动前将已验证的新来源树复制为不可变的独立开发快照，并由新版本开发分配入口核验与旧 catalog 仅允许计划中产品文件差异，以及运行时真实导入位置。不得全局 monkeypatch、运行时改源码、对失败帧改阈值、读离线真值控制。若涉及新的未列校验失败则封存原证与另轮处理；历史读回与不受影响工作继续。

## 固定帧与负控

先锁四张第120步、角色bootstrap真实帧。独立从默认和显式SUBPIX正常入口分别重算完整 evidence、原ID、有效深度/目的地/目标TCP，记录包括未过后续校验的原始原因；四张原图先封存两个版本决定，再接离线物理作误差审核。负控用源标明的派生帧或原校验夹具：错ID/已知标记缺失和目标无效深度均不得准入，篡改source/帧校验/策略拒绝，其他保护照旧。负控不是实测成功数。拒绝接受任意字符串。专项测试覆盖未传与历史相同、V2内部region、外部 boot/handoff 与 reset只读，不借用上帧成功。若完整帧结果与单帧预测不符如实记录；通过来源/安全负控才可运行新留出，不以旧帧上成功数作为入选条件。

## 实跑与验收

独立预分配名义正下机位、r593标记、原控制器，三个全新(x,y,z,yaw)为 (.437,.012,.035,.06)、(.463,-.012,.035,-.06)、(.451,.021,.035,.14)；种子24112601..24112603，组内相同初态、噪声、动作/超时、单实例独占目录/SQLite。每组两臂，顺序 默认/显式、显式/默认、默认/显式，共6次各一次，零重试。真实运行 allocate、固定帧blind replay、freeze、每实例 capture、独立score。计各臂启动通过数/3、实际首次PRE/dispatch/POST，记录最早终止原因及标记覆盖；完整在线效果、独立抬升≥50mm≥0.5s、区内稳定≥1s、无安全违规及全部阶段同时成立才记完整成功/3，按组列配对差。后续阶段失败不移出分母。未执行分列。封存源差异、逐帧角色与真实模式、全程像素及稠密物理、硬安全与步骤报告。此试验只评价特定软件模式与三个独立开发位姿；旧正式claim、新商业模型与实机调用均为零。
