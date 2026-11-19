# 教师有界测量的独立读回与 v9 来源核对

实际有界 MuJoCo 诊断退出 0。事后 read_diagnostic.py 第 33 行错误地要求 raw-artifacts 具有 UNBOUND scope，首次抛出 AssertionError: SOURCE_CONSISTENCY_ONLY，首次派生输出为空。raw_episode_v3.py 的生产 recorder 明确定义 SOURCE_CONSISTENCY_ONLY。原实测含 16 帧受控姿态及一个独立的原时限片段；454 个登记来源中 sol_molmo_components.py 在运行期间有并发变更，完整工作树冻结未通过。

先保存首次读回脚本原字节、空输出及首错的真实记录；如 stderr 只见于终端，则明确来源，不能伪造原始日志。仅把辅助 reader 第 33 行校验改为生产定义的精确 scope，并验证已有原件的 source_consistency 等标识和来源绑定。以新文件名读取原帧 SHA、相机/状态时间、PRE/POST 候选数、实际控制器返回与急停、真实单调钟、记录/渲染耗时及剩余未归因；分开有界 265/1920 段和独立姿态采集。对同一原件两次读回获得一致的稳定字段，并用副本篡改 scope/帧摘要作负控。历史首错与测量原件只读。

v9 初次 Ruff 两项 E501 仅机械折行并核对两文件 AST 前后一致。按父轮单独把最新全部 v9 源、配置、构建/解释器和真实 import 路径冻结到持久隔离目录。核对本次有界实测实际使用的来源，对未记录的运行时 import 如实记未知；独立整包命令和负控再核对实际导入路径与前后哈希、prepare/错组拒绝/完整 registry reader 结果。运行原专项测试及 Ruff；60 passed/19 skipped/58 deselected 原回执保留。是否运行新首组及独立 reader 按父轮的实际准入与原独占窗口，新的付费与任务模型请求数为零。该段原件只支持来源一致性和组件级实测；动作是否覆盖八项、资格与误差界须由完整独立 reader 按实际输入计算。

## 后继独占窗口的最小实际诊断

在软件与零释放负控完成、GPU/EGL 空闲且原件输出空间充足时，使用全包冻结并核对实际导入的 checkout、新目录和唯一诊断 ID。保持旧诊断与教师 claim 分离；新窗口在同一原姿态/相机/控制器设置与原帧族上运行。PRE 真实观测调用 bootstrap_registered_collection_tracker_v2 并绑定登记、冻结 source root/hashes；分立的 MOVE_ABOVE 实际姿态 16 帧逐帧将真实受感本体状态和新 RGB-D 送入 registered_collection_grounding_preview_v2。记录 registration、frame/hash/时间/年龄、原颜色分裂及拒绝、注册推断和遮挡证据；预览阶段不提交动作资格，模拟真值仅作事后对照。

另一段保留原 8 秒墙钟、全采样密度与安全停止；在真实 owner 内给 backend._operation_detach、所用 recorder._record_frame/_sensor_frame、实际观测转换、归档序列化与写出、渲染分别设非语义计时。区分嵌套的父/子区间、互斥净时长、未归因残余和退出后 flush，给出计数、原记录完整性、观察开销与来源。仅对本段时钟定量，不与 1801 的 100 ms 合并。原窗口启动前后校验冻结全包与实际加载模块路径。两片段输出、负控与独立读回分开保存；若单一可修成本有实证，报告最小改动、对照及所需下一轮，不靠减少原件、采样密度、延长 8 秒或替换时钟放行。取得合格一组的运行授权已具备，按父轮依实测准备情况释放首组并单独 reader，原 8 动作与全时域验收仍逐件判断。
