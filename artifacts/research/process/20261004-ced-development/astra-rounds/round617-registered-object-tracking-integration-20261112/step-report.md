# R617 当前标记几何跟踪与集合准备接口

已实现可调用的 RegisteredObjectTrackerV1 和 collection 版本化准备接口。完整颜色参考用于建立原区域模板，后续当前帧颜色目标可以碎裂；唯一当前标记通过R610未修改的刚体变换推导物体姿态/抓取点。绿色区域仍需独立、当前、完整、唯一且深度有效，选中像素范围必须与冻结参考一致；未使用推导物体遮罩或注册区域坐标补全。

结果明确为 DERIVED/REGISTERED_RIGID_MODEL，prepare_only=True、execution_allowed=False。表面可见性UNKNOWN、几何/区域误差界None、native authority UNAVAILABLE；内层R610结果的NOT_EVALUATED/NOT_PERFORMED未改，包装层单独记录本地字节与时间核验。JSON导出可修改副本，不能改变内部结果或作为旧GroundingFrameInputs。它不输出target_visible事实、旧Binding、TaskStep或准入行。

入口及返回前复核场景/episode/相机/标定、校验和、UTC新鲜度[-0.05,5]秒及源/资产字节。新身份在标记失败时也记录，防止失败后重放；位移检查使用最后成功姿态及其正确时间锚点，不用失败帧时间重新标记旧姿态。无旧姿态回填。已注册资产和75mm验证器读取的原对照资产均纳入本地来源清单；这证明本地字节一致，不是发布者认证或runtime/native attestation。

基线81通过；provider缺失API预期RED后23通过；collection缺失API预期RED后9通过；新增34例纳入最终115通过（16.75s）。真实OpenCV处理新合成标记；遮挡正例里旧颜色target_visible为UNKNOWN，新准备接口得到随当前标记转动改变的抓取点。负例覆盖8个上下文字段、时间/重放/位移、失败后锚点、标记/深度、独立绿色区域、机器人状态、源/资产/别名/输入副本及处理过程中失效。

最终Ruff曾仅发现新测试解释注释103字符超长，原失败保留。R618实际Astra计划仅将此注释分两行，文本差异及AST一致，产品/其他输入未变；一次修复后Ruff exit0/[]/stderr0。沿用115通过证据，没有为注释重复行为测试。6个测试过程均已退出、stderr为空；审计文件是解释器退出前快照，过程后另核验，未观察到清理异常。

原collection全部旧定义AST一致，22项其他输入字节匹配，旧tracker/helper/owner_registration/conditions/app/protocol/配置/资产/reader与globalnative来源要求不改。没有引擎导入/渲染/动作/教师/模型/云付费/硬件、旧raw解码或数据库访问；没有benchmark或实际性能声明。完整日志及生成材料留本地，公开派生报告不是完整远端复现包。

这仅是准备接口的软件交付，不代表旧v5已解决真实遮挡、完成动作链或获得动作授权。下一轮须定义新的几何basis输入/policy/binding与条件、准入、application/reader/protocol接入，之后才能讨论激活。原计划当时写的R618后继标签保留；实际R618是注释修复，绑定工作另行编号。3次历史教师尝试、0/9资格、8秒Shield/5秒新鲜度及UNKNOWN/UNAVAILABLE均保留。

唯一独立审查为C0/I2/M0，两项Important都已修复。R619先复现“边缘遮挡后仍是小矩形却DERIVED”和“处理后过期但nested freshness仍CHECKED”；随后仅改两处新增facade方法，冻结独立参考区域的shape与bool像素字节，当前范围逐字节匹配。最终时间拒绝同步REJECTED/UNKNOWN/空几何；区域本身失败但帧仍新鲜时，保留真实的CHECKED时间标签。定向16通过，最终四文件121通过（18.77s，含40个新例），Ruff exit0/[]、stderr为空；原11个定义AST/源码及provider/22保留输入一致。原审查与失败日志均保留，没有第二次审查或伪称fresh C0/I0。

该像素规则只适用于固定注册相机/固定区域：真实区域移动、颜色/光照引起的一个像素分类变化也会拒绝。它不是校准完整性保证，不能排除观测完全相同的遮挡。旧v5在新增import graph下没有实际运行验证；本地源字节也不是加载模块或发布者认证。这些边界均不以软件测试替代，后续激活须独立制定协议与验收。
