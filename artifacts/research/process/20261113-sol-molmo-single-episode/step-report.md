# Sol+Molmo 单场景入口阶段交付（2026-11-13）

已交付统一的配置准备、注册标记检查、真实Sol+Molmo规划和本地证据入口。**用户计划中的完整物理抓放仍未完成**：`--execute`明确BLOCKED，动作0；本轮没有成功抓放记录，不能声明G1、合格B0或T8完成。

## 软件和使用

新增 `scripts/run_sol_molmo_single_episode.py`，复用当前工作树src，默认只登记固定S01/seed42001，不读secret、不加载模型、不渲染或推进物理。支持check-marker、plan-only及执行前置拒绝。完整参数/命令见 `docs/research/sol_molmo_single_episode.md`。

`RoleModelBundle`并不是cloud/local模型容器；本入口使用现有build_molmo_grounded_planner、ModelControlService、MolmoPointProvider和PlanningPipeline，不改角色/契约构造器。只读SQLite查找精确Sol profile，经已有加密secret store读取凭据，不激活配置。专用Molmo环境保持原Torch/Transformers，仅可追加既有应用依赖。原始输入/回复/深度/权重及密钥不进入公开交付。

借用采集器不能apply_scene，改由采集会话拥有backend并RESET固定S01；不冒称seed产生了独立随机场景。标记注册按精确family/尺寸/资产哈希，UNKNOWN不自动写OCCLUDED。

## 真实验证

| 实验 | 结果 | 边界 |
|---|---|---|
| 默认dry-run | 退出0、PREPARED | 模型/物理/动作0，success=false |
| 45mm outboard_v3标记 | 首尾UNKNOWN/known_marker_not_observed | 121步、0动作；不能证明原假设的可见性修复 |
| 75mm +Y已登记标记对照 | 首尾OBSERVED | 121步、0动作；只证明两个静态采样，非抓后或连续可见 |
| 首轮真实Molmo/Sol | 1load/2gen/1cloud，收到真实回复后拒绝 | 本入口云后补帧推进1步，与既有暂停sim_time_s绑定冲突；失败完整保留 |
| 修正补帧的新版本 | 1load/4gen/1cloud，PLANNED | 10步合同、云后真实新帧复核和最终准入PASSED，0动作 |
| 执行前置 | 退出3、BLOCKED | 不加载模型/付费/动作，不静默回退 |

修复只移除了新入口refresh中的物理推进，使用同一会话当前模拟时刻重新采集真实新帧，没有改旧帧、TTL、深度阈值或既有复核器。模型累计2load、6gen、2cloud，未重试同版本；修复后独立新版本预算另行记入计划。四个真实采集前缀共485物理步、12帧。包括准备/前置在内九份输出，175个文件由独立脚本逐字节/SHA和RGBD checksum重新读回，标记原始解码结果及三次渲染状态哈希一致。

真实规划发生在最终类型标注和异常归档修正之前。各回合的源码指纹保留原样，执行期间无漂移；不将其冒称最终提交逐字节重跑，未为类型/归档修正再次付费。最终版本另有dry-run/执行前置和267项回归验证。选择的源码清单不等于全运行时或完整远端raw复现包。

## 失败、测试和审查

首轮13个RED命中缺接口；首GREEN为12通过/1失败，原因是公共深度预览写入器不接受全无效深度，新增该情况下原始RGB/depth/mask保留后通过。来源删除反例和暂停补帧分别保留RED。CPU完整规划测试先暴露夹具缺scene_id、随后暴露旧两查询夹具不能复用四查询；修正测试来源后真实管线通过，不改变生产门限。

最终19项新入口测试，六文件限定回归 **267 passed，4.55秒**；Ruff、format、两个生产源mypy和diff检查通过。全仓pytest -x已尝试，94通过后停在既有 `test_model_control_public_api_has_chinese_docstrings`，该检查涉及七处未修改的model_control定义；有既有Starlette依赖警告。全仓未通过，未修改无关文件消除旧失败。

一次独立当前模型审查报告0 Critical/0 Important/2 Minor。两项归档问题按实际影响升级为需修复：中断不能保留PREPARED标签，启动时源码缺失不能只留下空目录。两项独立RED后在同一修复轮完成：中断保存INTERRUPTED并继续抛出；初始源码失败保存INCOMPLETE/FAILED和清单。267项回归覆盖修复，无第二次整体审查，Astra调用0。

## 剩余实际阻塞

1. 旧视觉episode只接受精确标定资产，标记XML不能通过改路径继承资格。
2. Molmo专用主线程、云后新帧和真实OpenCV worker的合同/来源/动作资格交接未集成。直接送进旧后台模型线程或改用LEGACY会绕过既有边界，本轮未这样做。
3. 标记与运动几何资格、完整抓取/放置/释放，以及既有搬运后遮挡问题仍待解决。原outboard45mm假设在本次初始状态就未得到支持。

因此，下一出口是合法的标记资产动作资格及真实worker交接，然后取得完整任务的正/负证据和独立批测，再开展四周期B0与另120组基础先导。本轮仅提交入口、测试、文档、计划和派生报告，完整用户目标保持未完成；不生成研究冻结包。
