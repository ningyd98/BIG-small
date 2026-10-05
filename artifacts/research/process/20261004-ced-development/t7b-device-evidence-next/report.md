# 步骤49：实际可见性与校准输入

本步在保留原相机和控制器的条件下，完成一次新的实际仿真搬运：初始与九个动作后帧均 OBSERVED（10/10），原中心标记九个动作后UNKNOWN保留。4807个完整物理状态由独立审查逐字段复算，与原运行仅episode_id不同。开发主线仍T12/18、T13并行，边缘型号后置；基本几何/连续证书、实际Max及正式实验尚未验收。

## 独立交付

| 部分 | 结果与证据 |
| --- | --- |
| 独立outboard-v3可见标记资产 | 5项合格RED；24项相关CPU与5项独审通过；物理/相机/控制器参数保留，视觉编译统计限制明确 |
| 单次实际开发搬运 | 9动作、743命令、4806物理步；10/10边界可见，独立评分限定SUCCESS；原始hash/严格decoder/评分/完整状态复算通过 |
| 量测目标边界RGB-D | 6项合格RED；初版101CPU/2实际物理测试排除、7项边界独审通过；构造器P2另经3种合格RED修复，最终50项marker回归及独立8项复核通过；原始轮廓与邻域深度保留，完整范围仍UNKNOWN |
| 点运动校准输入 | 初版129相关CPU；可变marker类型P2经3RED修复，最终16项新模块CPU及16项独审通过；仅采样割线速度，不授连续证书 |

局部来源和复现分别见[实际可见性报告](../t7b-visible-marker-next/report.md)、[目标边界报告](../t7b-marker-extent-next/report.md)和[点运动输入报告](../t9-motion-residuals-next/report.md)。三份限定独审分别为[实测源/原始资料](../t7b-visible-marker-next/independent-review.md)、[边界数据](../t7b-marker-extent-next/independent-review.md)和[运动输入补修](../t9-motion-residuals-next/independent-review.md)。边界构造器的可变嵌套marker问题另见[三文件补修报告](../t7b-marker-extent-next/fix-round-1/report.md)：真实类型检查和重建验证先于读取字段，原始包及21份非owned来源不变；独立8项（6.64秒）复核及原固定digest反例的变更前后拒绝检查关闭该P2。原发现、原RED和旧REQUEST_FIX均保留。套件有重叠，不把测试数量相加成研究分母；未跑或宣称全仓通过。

新实际标记是无质量/无接触模拟视觉附件，不代表实体安装验收。小标记姿态误差经100mm附件偏置放大：单组最大marker中心0.941mm、反推物体中心6.393mm、旋转0.063192rad。这些是离线误差诊断，不能写入native基本界。原native builder保持几何/运动界None，基本标定来源应独立于T9风险及INITIAL，不能形成相互依赖的放行开关。

本步实际新增1组开发仿真动作实验、1setup及10边界采集调用；远端/Max调用和真实硬件为0。实际源码28文件只占320879字节，79份原始文件hash固定。独立风险与边界开发未运行新的相机/provider/物理过程。实际执行脚本的I001和3处E501按执行时字节保留；离线verifier静态问题已修复并复算通过。

剩余关键工作是：真正的基本几何与动作窗口运动来源、可见性连续采样及跨组校准、完整目标与真实attachment来源、Max规划/成本证明、风险校准、完整机会/200故障、合格四周期B0、INITIAL/METHOD/FINAL与恢复验收。当前校准输入不替代这些研究前置。详细机器索引见[第49步状态](../implementation-status-step49.json)，完整方法要求继续按原总计划实施，`formal_accepted=false`。

收尾[定向检查](../documentation-check-step49.json)核对12份当前文本/局部报告、36份当前源码、28份实际运行来源及归档、79份原始文件、最终三份独审与局部报告hash；第48步索引未改。明确范围git diff --check退出0。检查不扩大为全仓或正式验收。
