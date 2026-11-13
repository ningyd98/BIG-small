# Sol/Molmo组件执行攻坚报告

当前模型实施，非Astra。基线8b996603；用户已明确授权MuJoCo组件诊断并保留硬安全检查。

## 根因与最终范围

标记资产SHA不同是添加可视标记后的真实差异，不是注册过期；采用精确注册和XML结构等价，仅新增开发组件许可，原校准SHA不变。Molmo需专用主线程；新增真实worker持有的两阶段补帧、4定位/1Sol和完整PlanningPipeline。源码进一步确认T10几何/运动误差证书与连续稳定证据未成立，普通--execute仍明确拒绝，组件分支不冒充正式VisualWorkerRuntime准入。

新增75mm标记、+Y外伸140mm的固定组件变体，37个零质量零接触标记；移除后物理、相机与控制器结构等同原scene.xml。旧45mm初始未知、旧75mm/100mm外伸放置后遮挡导致6动作停止的负例保留。变体未进入原生prepare/release资格。

真实SQLite SimulationWorker持有租约和固定attempt；边界/50ms墙钟轮询核对完整租约，派发前再核对。SkillExecutor与SafetyShield共用实际组件执行视图，原合同和未认证条件完整保存。关节/速度/TCP/连接/急停/碰撞反馈每物理步检查。当前目标和目的地RGB-D身份支持不可省略；离线真值只用于独立评价。120秒任务、16000步；同步原生调用为前后截止校验，不能强制在120秒中断内部模型。

## 软件验证与独立审查

- 限定回归789通过，119.51秒，含既有Molmo、marker、worker及SafetyShield；审查/发布修复后211项最终集成通过87.20秒（含实际SQLite worker成功终态与8技能物理成功，外部云/点位为软件替身）。
- 一次独立审查（当前模型，非Astra）发现2个Important：动作中完整租约核对缺失；组件文件可能覆盖真实worker失败。已增加具体SQL released/attempt变化、实际worker TIMED_OUT及source漂移负例并修复。没有二次全面审查。
- 更严格的真实终态检查又暴露ActionResult对象不能被worker通用JSON发布的问题，已将worker返回数据规范为同一归档JSON；历史RECOVERY_PENDING负例保留。末尾采集失败仍保存独立物理结果并记失败。实际计数分别保存云、本地和合计。
- 全仓测试尝试：94通过后在既有model_control中文docstring 7处缺项停止，不能声称全仓通过。
- Ruff所选14文件通过。git diff --check报告新标记XML第2行尾空白一处，保留实际注册和运行的资产字节；不是功能失败。
- 新文件/入口/同步调用的5文件mypy检查通过；grounded_planner已有15项类型问题由HEAD原件复现，未扩大修改范围。

## 实际模型结果

第一实际版本模型加载1次，定位/云/动作0次，33.42秒，在角色配置绑定处停止。免费诊断确认桥接遗漏role_config_version，真实已更新配置与默认版本1不符；保留版本1对照、新增版本7失败反例后修复。修复后50项通过3.77秒，免费真实配置验证通过、模型请求0。第二新版本真实Sol/Molmo运行完成：worker SUCCEEDED，COMPONENTS_COMPLETED，8/8控制器技能成功，component_success=true、physical_success=true。加载1次、原生定位4次、云请求1次（合计模型调用5），墙钟34.00秒，无重试。两实际版本合计加载2次、定位4次、云1次，未超过预先记录的两版本预算。

独立物理评价：抬升0.17786365m，稳定保持1.258333秒，释放后在目标区稳定4.40秒；物理段19.691667秒，4727个连续样本，步骤120..4846，同一episode。检查范围内无安全违规（SCOPED_NO_VIOLATION）。从原始物理样本重新运行原评价器，结果与归档完全一致。216个原件的字节/SHA全部核对；另核对第一版本6个原件，未改历史字节。20帧RGB/原始深度/mask/实例尺寸及hash通过，每帧3个渲染pass状态一致；云后补帧物理状态未推进但观测ID/时间/checksum更新。46条角色绑定源码项与当前字节一致。

标记：20个采样中15 OBSERVED、5 UNKNOWN，释放前包括PRE_RELEASE均可见；POST_RELEASE、PRE/POST_RETREAT、末端稳定及after未知，原因known_marker_not_observed。首尾并非全可见，不能声明连续可见或把UNKNOWN升级为OCCLUDED。RETREAT经当前RGB-D红块支持与机器人反馈完成，没有完整尺度/姿态证书。这是后续姿态/连续证据适配仍需处理的缺口。

单个固定S01仅证明本次组件成功，不形成Molmo静态成功率，也不能与原Qwen 4/40直接作成功率对照。软件云/点位替身不计入真实模型效果或成功率。派生指标与证据哈希见verification-summary.json。

## 验收与交付边界

组件可报告完整动作和独立physical_success；通用success=false、online_reported_complete=null、formal_research=NOT_ACCEPTED、qualified_groups_added=0。单个固定S01不是静态成功率，T10、G1、B0、T8均未因此通过。

原始RGB-D、完整模型请求/回复、物理样本和SQLite数据库留本地；公开提交仅代码、测试、标记资产、文档与派生报告/必要哈希，不是完整远端复现包。运行说明见docs/research/sol_molmo_single_episode.md。
