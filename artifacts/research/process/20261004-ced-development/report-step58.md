# 第58步：标记软件补修与 OC1 独审闭合

用户要求的每轮 Astra 流程已实际应用：标记静态及真实格式衔接、OC1 静态、测试报告输出隔离、R06 文字更正均先取得对应 Astra 计划，再按白名单处理；冻结前置脚本新失败已保留并交下一 Astra，尚未重试。

## 标记完整采样软件

按[round58 标记计划](astra-rounds/round58-marker-preflight/plan.md)修复旧 V3 长 SHA 字段衔接、新 recorder 返回行与持久化 END/coordinator 的 event 一致性，以及教师动作只能为精确九项的门。prepare 源未变，不放宽0.005模拟秒采样界。新增40个格式用例由38失败/2通过转为40通过，最终同一 owned suite 131/131 通过（9.66秒）；这些重合用例不累加。四源 Ruff、格式与内存编译通过。[局部报告](astra-repair-execution/R01/marker-v4-full/implementation/round58-preflight/report.md)保留原 RED、静态失败与源码快照。

root [新进程闭包检查](astra-repair-execution/R01/marker-v4-full/implementation/root-fresh-process-closure/result.json)通过：临时目录冻结包含48个源，34个实际公共导入来源及 live/archive SHA逐项匹配，状态合同 digest 保持；写入只发生在本次临时 fixture，运行未进入模型、相机或decoder，也未读取旧压缩图像。这是源闭包软件证据，尚非生产协议冻结。

随后作者人工前置脚本把必要复用依赖44项误断言为完整48项，正式 freeze 会另外加入4份 owned 源；[原失败](astra-repair-execution/R01/marker-v4-full/implementation/production-freeze/precheck-failure.json)已保留。CLI --prepare 调用0，full-protocol不存在，四源静止。root已委派 Astra round60 metadata-only 计划（本报告时仍生成中）；独审只读进行，suite及actual等待真实冻结完成。该失败不伪报为通过，也不改产品源码来绕过。

## OC1 软件时钟

[round58静态计划](astra-rounds/round58-oc1-static/plan.md)完成限定类型注解、导入及等值字符串修正。root发现真实Linux工厂测试会覆盖固定原始收据路径后，先取得[round59输出隔离计划](astra-rounds/round59-oc1-test-output/plan.md)，只改本测试的 tmp_path 参数及 artifact 变量。其余 AST/断言、模块源码保持。见[隔离报告](astra-repair-execution/OC1/test-output-fix/report.md)。

最终root唯一全60复跑通过（pytest0.11秒、进程wall0.285秒），零失败/跳过；正常tmp_path产生的新Linux CPU收据逐字节复制到新审查目录。运行前后70个OC1原始实现/静态证据保持SHA与字节；70不代表全仓或旧raw复现。独审[源码报告](astra-repair-execution/OC1/independent-review-round59/source-review.md)为 PASS_SCOPED_SOFTWARE_OC1，无开放P1/P2；独立公开API小探针一次19场景通过，不增加60项pytest分母。

零参数Linux CLOCK_BOOTTIME工厂、启动身份、live对象来源、合法MARK/current/END重叠、整数TTL等值接受/+1ns拒绝和原始deadline等值拒绝，均达到限定软件门。真实CPU读取并不授予worker/job/lease/capture资格；checkpoint数学不保证阻塞后的dispatch或未知未来horizon。实际suspend/restart/宿主机暂停未测，UTC/SI精度仍UNVERIFIED。OC2真实来源链计划已委派Astra但本报告时未定稿，共享worker/teacher修改必须等标记actual及读出终态。

## Max当前启动与阶段边界

R06只读重新核验当前CLI环境和已知两库配置，现有enabled兼容Max profile为0；没有provider请求、建profile或DB写入。此范围不证明用户全局没有密钥，历史35次调用保持单列。原报告把四次probe请求写成“四角色”，按[文字修订计划](astra-rounds/round58-r06-readout/plan.md)只新建[更正读出](astra-repair-execution/R06/current-startup-revalidation/corrected-report.md)，保留原MD/JSON；四次为cold一次及warm三次。

本步物理采集、render、decoder、模型/provider及硬件调用均0。完整4807帧实际可观测性、OC2/3/4、九独立组、Max真实规划、G1、INITIAL/METHOD/FINAL仍未验收；主线T12/18、T13并行，边缘选型后置，formal_accepted=false，硬件NOT_STARTED，S3/S4 LOCKED。恢复wall-Rcap的软件仍按既有Astra计划等待共享源码写入窗口，未执行0002。

第56步本地提交仍为be1c10cd596926d0184d7c13268ae3c3e22109d0，383文件/20112981字节；公开推送因自动审批两次拒绝等待用户对具体载荷的批准，实际push命令0，远端最后核验24ddf13193a1547edeab39165846ff716a0b5f3d。没有新commit或绕过审批；本步源和报告尚未提交推送。批量raw仍本地，派生清单不代表完整远端复现包。
