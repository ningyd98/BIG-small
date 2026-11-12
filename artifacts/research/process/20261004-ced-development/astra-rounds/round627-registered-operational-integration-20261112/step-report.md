# R627 注册模型采集接口与独立记录：步骤报告

本轮计划由当前 Codex 制定，明确为 **非 Astra**。指定 Astra 三次容量不足，用户随后临时授权当前模型规划并继续。R627以及范围补充/失败修复R628–R633保留各自计划、输入SHA和原始失败；不将这些计划写成Astra产物。

## 本轮实现

- 在原 `SimulationWorker → NativeCollectionApplication → NativeHorizonSession → SkillExecutor` 路径增加明确的注册模型坐标分派。没有新增执行器，普通 `VisualWorkerRuntime` 仍拒绝新绑定类型。
- `RegisteredCollectionStepBinding` 保留完整内层准备绑定、原要求、租约、帧、版本、检查点和原动作时长。内层仍prepare-only，外层仍SOURCE_ONLY/无执行权限；实际实验许可留在原私有应用。
- v7独立配方/CLI保留原8动作horizon、控制器和Shield。assignments/release/实际预算均0，公共factory在创建输出/DB前拒绝未释放任务，不复用R595种子或额度。
- 新姿态可用条件只补充。旧完整可见、像素几何、原声明和UNKNOWN白名单保持原语义。残缺红色目标可生成模型坐标，但旧target_visible仍UNKNOWN，不能由此继续普通动作。
- 独立 `native.registered.action-span.v1`、registered inventory/originals schema及严格reader分支；旧raw-v3拒绝新格式。新记录核对原identity、完整执行参数、frame、lease、policy和原时效。
- 研究reader的历史adapter复用原算法并校验原记录UTC，live精确类型入口拒绝该子类。无全局改时钟。历史重算仅SOURCE_CONSISTENCY_ONLY，不能认证过去授权、当前freshness或native资格。

## 验证和原始失败

基线116PASS；新绑定15PASS与旧绑定/效果92PASS；接线27PASS；span7PASS、archive6PASS、recorder/reader3PASS、独立grounding语义/重封篡改7PASS。R627–R633当时的选定组合采用可追溯分段（后续当前字节单次回归见下）：

| 片段 | 实测 | 处理 |
|---|---|---|
| R627原final | 522PASS，1FAIL，1deselect，1第三方warning；478.01s | 历史P5registry的observations.py哈希已在BASE29560f50失效，loader正确拒绝；原件不改 |
| R632尾段 | 9PASS，1FAIL，1第三方warning；29.41s | 新合成P5及其5s/foreign-owner检查通过；真实MuJoCo节点被guard在模块查找阶段拦截 |
| R633未跑余项 | 78PASS；116.27s，rc0/stderr0/forbidden[] | 只跑78未运行节点；不重复531项已通过前缀 |

该历史阶段合计 **609项选定检查通过**。两个精确节点延期：raw-v3大缺尾子进程测试、真实MuJoCo两物理步测试。不是一次固定测试字节的整套重跑：产品和两新feature-test的12路径字节全程相同，R632只改P5测试的历史夹具helper并增一测试，其他旧函数AST相同。原失败仍是原失败，未覆写成成功。

R629修复新span对冻结tuple与JSON list的比较；R630修复新recorder测试遗漏原check_active依赖；R631修正方法片段排版补回缩进造成的超长行。修复都有独立非Astra计划和原始失败/代码快照。只读范围检查10产品模块未发现计划外旧函数改动。Ruff剩19条精确对应旧代码，新增0；实际Ruff退出码1，P5新增测试文件Ruff0。全仓旧Chinese-docstring失败没有修复或重跑，不宣称全仓绿色。

## 预算偏离与保留边界

R627原final在P5旧registry拒绝前，已校验一次仓库内历史测试帧的RGB/depth/mask；旧guard没有分类这个fixture。这一次偏离记为1，不报告旧raw解码总计0。R632改用全新合成像素和不同ID的当前源码DEVELOPMENT_ONLY描述，并加强guard禁止打开旧像素及旧marker实验目录。旧PNG/深度压缩原件、provenance和registration字节及mtime均保留，未更新其哈希来强行通过。

R632中的MuJoCo查找尝试被拒绝一次，实际引擎导入、构造、render、step、IK、控制器动作均0。原研究spool/运行数据库/模型权重/SDK/凭据未读取或交付；没有新增研究模型请求、付费云调用或硬件运行。P5候选仍NOT_ADMITTED，几何精度/整体身份未知。

## 工程裁决与代价

1. 接原teacher生产调用链，普通云端private publication后置；代价是普通云worker的注册模型实际能力尚未开放。
2. v7零释放，CPU夹具只证明接线/计算/拒绝；代价是真实factory释放、完整8动作原件和实际时延尚未验证。
3. 新逻辑追加现有模块以保留旧source keyset；代价是大模块继续增长。
4. 使用本轮artifact ledger并保留失败/快照，覆盖skill清理要求；代价是状态靠保存证据和人工核查。
5. 用户已要求自主继续并批准非Astra规划，省略routine计划确认；代价是设计在最终独立评审前无外部审查。
6. v7基于v4未释放的相同full-H配方，而非携带R595释放字段；代价是新真实运行仍需独立版本和运行计划。
7. 完整工作流内做一次fresh审查/一次fixpass，不逐task审查；代价是暂无逐阶段外部复核。
8. 有限guard回归取代裸全仓运行，明确延期两个实际/子进程节点；代价是不能宣称全仓绿或本轮验证了这两项。
9. 分段完成剩余检查并保持产品字节，保留原失败；代价是不具备单次固定测试源整套运行证据。
10. 历史adapter只重算已记录计算，不认证时间/原进程/事件权威；代价是过去授权及SI时钟来源仍未知。
11. 残缺目标/目标区域保持保守UNKNOWN，固定controller姿态不变；代价是正常遮挡及真实旋转抓取仍可能停下，后续要显式版本化条件/区域策略，不能由本轮类型接线声称已解决。

## 验收边界与下一阶段

一次完整差异独立评审已完成：C0/I1/M1。评审的具体模型无法核验；早先root ledger/request称其actualAstra属于误标，原字节保留并在此更正。I1已按实际gpt-6-astra R634/R635计划完成唯一修复pass；M1延期，没有第二次普通review。当前为选定软件验证完成。没有当前完整v7八动作原件，不将decoder单元测试当作整组独立验收。正式状态NOT_ACCEPTED/native UNAVAILABLE；未获得九组合格证据，未证明G1定位P90≤10mm或静态抓放≥90%。8sShield/5sframe/原TTL/lease/取消/源检查/已选标记相机控制器保持原门槛。

后续推进真实正常链前，还须处理注册定位与原默认完整可见/完整绿色区域条件的版本适配、当前完整采集性能、独立实际attempt/源/clock证据。不会通过删除原显式声明、伪造误差界或把UNKNOWN改PASS来制造通过。

已知旧Minor：native_full_horizon_originals模块头部仍沿用“no runtime DB”旧描述（v6当前reader实际有既存DB只读业务查询/初始化bookkeeping）；未在本轮修饰性修复。


## R634–R635：真实执行器入口的最终校验

R634、R635计划由显式指定的实际gpt-6-astra生成，与此前R627–R633非Astra计划分开记录。旧代码行为RED实测：分配执行记录区间后，UTC刚好到达绑定截止时间，执行器仍被调用一次；9.86s失败日志保留。修复在公共recorder实际executor调用紧邻前加入默认空hook，v7专用recorder委托原应用消费单次PRE上下文；核对同一acquisition/原始帧/步骤/identity/source generation、真实取消/租约/原单调时钟边界，全部慢操作及deadline解析后才自读最终UTC，严格拒绝截止相等。旧路径默认行为保持；没有新执行器、source keyset或公开release。

第一GREEN未通过：任务origin与capture事件混用了当前回执，真实owner抛出OperationalTimeError。已暂停并由实际Astra R635限定caller修正；原错误日志、代码快照及有效期内正例RED10.78s保留。两个事件分别使用原句柄读当前回执，按原规则检查deadline/age，不改owner API、不换算时钟域或刷新截止。此前两次软件夹具预检错误（缺MuJoCo运动学字段、guard参数低于原最小值）也保留；它们不当作产品漏洞RED。

定向 **70PASS / 239.53s**。最终同一份14个代码/测试文件字节做一次完整选定组合：**624PASS、2deselected，869.74s，rc0/stderr0/forbidden[]**。收集前已指定两节点排除，节点清单及前后SHA全部保留；不再依靠先前522+9+78来声明当前通过。15项新增检查覆盖区间/BEFORE_SUBMIT慢工作、晚租约读取、当前短租约与5s帧截止、未来时间、同S换帧、原identity/步骤/协议变化、取消、租约读取期间复制源实际字节变化、重放、部分执行失败。有效期内经过30ms后，同一执行器callback仅进入一次；软件callback明确返回无控制成功，不冒充真实H完成。真实v7准入负例证明pose PASS时，完整可见性UNKNOWN仍STOP且不产生pending。ABORTED/PARTIAL和失败horizon证据保留。

当前组合保留1条既有第三方警告（Starlette/AnyIO弃用提示），未通过抑制或改依赖隐藏。全选路径Ruff实际rc1，19项精确对应原问题，新增0；本次3产品模块和records测试Ruff0。全仓旧 `tests/test_chinese_comment_checker.py::test_model_control_public_api_has_chinese_docstrings` 仍未解决，未宣称全仓绿色。当前guard没有旧raw、原运行DB、模型、付费、硬件或真实引擎调用；早先历史测试帧偏离1次与被拒MuJoCo查找1次继续计入，不被本轮清零。

补充裁决及代价：

12. 接受I1为Important，按一次review/一次fixpass处理，并为新token错误单独实际Astra子轮；代价是没有第二次review，依据行为RED与当前组合GREEN闭合。
13. same-S recapture此前未找到正常私有调用路径，不能称为已证实旧漏洞；新入口仍核对acquisition并通过主动注入负例。代价是仍不保证任意敌对内存并发或最终检查到Python调用间调度原子性。
14. 旧原件保留判断依赖已有SHA/stat/effect记录，不重新打开旧像素/原DB；代价是这不是新的完整raw独立审计或完整远端复现包。
15. 普通worker/公开factory继续拒绝零释放v7，并保留九组、定位误差、历史授权/时钟真实性的未知；代价是不能据本轮软件交付宣称真实/正式任务通过。
16. 评审型号无法核验，仅实际计划R634/R635标为Astra；代价是不给评审作Astra专项背书，保留误标原始证据而非重写历史。
17. 下一阶段性能候选只制定有限CPU语义等价计划，未在本次回归期间改动产品；代价是现阶段不声称新增真实capture或完整任务时延提升。继承Minor M1的模块头DB隔离说明继续延期。
