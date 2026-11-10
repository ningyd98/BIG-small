# Molmo2-ER / OpenCV / 云端技能规划阶段总结

2026-11-10；开发分支 codex/molmo-opencv-grounded-planner-20261110。本轮实现显式接入，并完成单场景真实本地几何验证；默认在线服务尚未切换。

Molmo2-ER只接收RGB做目标/放置区定位；OpenCV与对齐原始optical-z float32米制深度生成几何，现有云端角色只输出技能，原PlanningPipeline生成可信字段并校验合同。沿用当前选定云端gpt-6.1-sol、安全密钥/传输、顶视相机、可见标记及控制器配置。

|验收层|实际结果与边界|
|---|---|
|软件接口/相关回归|322 PASS，13文件Ruff、差异检查通过。包含原RGBD/抓取/profile/跟踪回归与新增边界负例。|
|完整云规划接口|CPU/API夹具返回PLANNED，验证技能白名单、可信字段、Sol路由/参数及失败关闭；不是真实云端结果。|
|离线原始帧诊断|原生点仍拒绝；局部关联后静态几何通过；归档时间不变，生产入口仍拒绝过期，0实际调用。|
|真实本地 native-01|1load/2gen completed；原生点落桌面，几何NOT_READY，exit2，全部原件保留。|
|真实本地 native-02|1load/2gen completed；新采集S01 seed0，局部唯一红区域关联后几何READY，exit0；两查询1.212s/0.785s。|
|真实云端|NOT_PERFORMED。native-02管线实际PLANNER_FAILED：no-paid诊断cloud明确未请求，不能称端到端云规划通过。|
|连续控制/实机/正式研究|NOT_PERFORMED；不继承历史系统或G1/G2/heldout接受状态。|
|全量测试|FAILED_AND_INCOMPLETE：实现前基线23failed/49errors，1054passed/2skipped后中止；EGL复跑仍见既有失败后按精确PID停止，未修无关问题。|

## 本次适配修复

首轮真实原生目标(562,458)转换为原图(179,109)，实际是灰桌面，距14px红块4px。现有深度门正确拒绝。实际Astra R547在固定颜色方块范围增加一次有界RGB局部关联：本例19px窗口内恰有一个完整红区域，选择(179,119)，原native点、候选区域及helper SHA均独立保留；之后仍执行原始深度/抓取/全局颜色唯一性/轮廓/TTL门。放置点(130,72)保持原样。

几何目标可见顶面约(0.45078,0.00258,0.07007)m，现有抓取profile给出TCP约z=0.04505m。这只是当前校准仿真范围的开发估计，extent_complete仍false，无新增深度误差界、成功概率或物理完成声明。

两轮共2次模型加载、4次生成启动且4完成、0付费请求、0硬件派发，累计额度2/4已用完。native-02是重新采集的确定性同一S01场景，不能据此推导跨场景准确率或模型排名。

## 审查与步骤

R542原始集成计划与输入SHA已保存；R543保持AST的样式修复；R544独立实际Astra审查C0/I5全部修复，覆盖请求漂移、重复JSON、paid失败判定、raw生命周期和解码失败计数；R545独立append-only运行时覆盖未改Torch/Transformers/.pth；R546固定observer每次attempt归属。R547新定位关联、R548测试/诊断夹具纠正、R549一条note样式均先有实际Astra计划再执行。

R547原25项测试被缺必填fixture字段遮挡，明确不作有效功能RED证据；错误与修复日志均保留。所有步骤报告分别位于相应round/implementation-report.md，最终源SHA位于R547 verified-source-manifest.json，真实记录摘要位于R547 native-cumulative-summary.json。全量失败原件与分类在execution/full-suite-classification.json。

使用入口见 docs/research/molmo-opencv-grounded-planner.md；当前为opt-in service factory/CLI。真实云端结合验证及控制器接入、连续运动/物理验证仍需分别提供真实证据。源代码与派生开发证据本地分支交付；完整raw、模型/SDK、运行数据库和凭据留在本地，清单不等于完整远端复现包。公共推送遵循既有明确公开授权边界。
