# 步骤50：逐步RGB-D记录器

已实现 `research/step_rgbd.py`，为既有教师逐物理步观察回调提供独立研究采集记录。每个实际step关联原episode/sim-time、开始/结束monotonic与名义UTC、RGB/depth相同physics-state hash；完整RGBDObservation以gzip无损保存。原最大模拟采样间隔0.005秒、step0及完整终态核对保持不变；缺步、跨episode、错帧或相机来源变化时拒绝。

13项缺模块合格RED保留；首轮GREEN的合法source枚举fixture错误另存，修正fixture后13项通过。独立审查另复现两项P2：首个BEGIN日志写入失败可重试并错误COMPLETE；公开episode/gap字段可变更原始约束。四项合格RED后，将原约束改为只读属性，日志首写进入终止保护，FAILED日志自身失败不掩盖原异常；另列已分配attempt与真正开始的camera调用。最终17项回归和独立17项均通过，原反例关闭。原源/测试两文件、原REQUEST_FIX及失败日志均保留。

source/test Ruff/format与source mypy通过；推送前七文件联合定向检查81通过（16.36秒），包括默认配置、marker资产/可见性、目标边界、运动输入、runtime binding和本模块。套件有重叠，不累计作研究分母，不宣称全仓通过。详见[独立模块审查](independent-module-review.md)与[机器验证](module-verification.json)。

本步没有实际渲染、物理步、模型调用或硬件。新的完整动作内采集script及独立重放仍在准备，尚未执行；不能把模块测试或4807帧的资源估计当作已发生实验。名义UTC括号不证明外部UTC不确定度，采样序列不授连续未来速度界、native或正式阶段权限。相机私有原始采集还必须单独登记，不能冒称已经产生typed raw-v3 CAPTURE。

下一项采用同一顶视相机、原控制器、独立outboard-v3资产和新排除开发组，每个真实物理step采集一次，解码留在动作结束后离线。脚本在零噪声前提下验证RNG/cache/data/control/model不变，原教师动作只调用一次。先审查冻结，再串行跑唯一attempt；保存全部UNKNOWN与失败。见[采集方案](plan.md)、[时钟来源审查](clock-review.md)。

独立分析发现原统一运动量对主动搬运不可行：旧LIFT完整窗口位移87.8mm、MOVE_TO_REGION345.2mm，即使几何误差/年龄为0，总物体运动项仍超过10mm容差。已形成[动作参照设计](../t7b-native-calibration-source/design.md)，需要把实际编译出的参照与定位/控制误差绑定；当前仅为明确设计，未实施或授权限，不放宽容差、完整horizon、条件及安全门。基本真实校准、Max、机会/故障/B0/INITIAL/METHOD/FINAL保持未验收，边缘模型后置。

用户本步新增Git管理/推送要求。既有研发代码、测试、配置、必要原始fixture及步骤49报告已进入研发快照提交 `d3472a562356e6edc3dc1da2aa07a45096b54e5c`；本模块与本步报告按独立交付另提交。完整Git交付与本地批量数据范围见[Git记录](../../../../../docs/research/process/git_delivery_20261005.md)。
