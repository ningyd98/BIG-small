# P6 Stage A ROOT 限定软件验收

决定：ROOT_BOUNDED_STAGE_A_SOFTWARE_ACCEPTED；完整P6、公开发布闭合、native/physics/hardware/actual/formal均未验收。


## 2026-10-12 当前 P6 A 阶段状态（R155）

本段更新并覆盖此前正文中 P6 A 待执行、待终审或未验收的当前状态描述；此前正文和各轮记录保留为历史。

ROOT 已依据 R152 独立终审限定接受 A 阶段软件交付，上限为 LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO。终审在此范围内 Critical、Important、Minor 已确认问题均为0，24/24读取已用尽。

40个唯一通过节点来自四次实际运行：历史 GREEN20 的19 PASS（原1 FAIL完整保留）、R147修正foreign单例1 PASS、new19的19 PASS、R141 CPU受控正链1 PASS。这不是一次40节点运行；R145类型变更和R147夹具变更仅按已核精确证明沿用证据。原静态失败与过程工具失败未删除。

CPU正链先调用原episode一次，仅注入六项结局flags，22个自然文件hash已核；模型调用、动作和物理量证据均为0。legacy UTC veto保留。B9公开确认与SQL历史区分仍为OPEN，精确terminal COMMIT成功后失确认组合未实际执行。B/C/D为NOT_ACTIVATED，P6_complete=false；native、physics、硬件真实运行与formal验收均未提升。

下一步依既定顺序推进B9/B、C、P7/P8、D；B9需显式区分SQL事实与已确认发布，并先按Astra计划限定验证。R153旧HEAD前置失败原件保留；R154只读诊断的文本覆盖限制及eligible=false未改写。R155明确采用315fd不相交基线，保全100个开题文档相关既有文件，不对其语义作本轮判断。本段编制时Git交付待执行，实际提交、推送与三SHA结果以本轮提交外postpush-receipt.json为准。远端选定载荷不是完整raw/数据库复现包。

验收记录：/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round155-p6-disjoint-head-finite-delivery-20261012/acceptance.json

终审原件：/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round152-p6-review-recovery-index-schema-20261012/review/final-review.json SHA256 db83f79f83f9fd50e56b965949a913da90f7c485776c16f15aa75e7c812b5bf4

交付实际收据：/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round155-p6-disjoint-head-finite-delivery-20261012/postpush-receipt.json

六份冻结源码：

- /home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py SHA256 524bce7ee480fc7f9757e23a8360257900d3600c3b6842c46b80d0771201ec90
- /home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py SHA256 e4a60c5c8dd6edd468f3033637fce3003ec83dcd0599c59d31dff99dd0291e32
- /home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/simulation_runtime/repository.py SHA256 228e5480630fe14ad6752ec75f9ea42f4c1cf89c8ce278b6378b2ab9a5624447
- /home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/simulation_runtime/worker.py SHA256 d0833f98112ccac9b5e9b04163dfcbf2f7d1d053f72c9ab7a7a18398a5e6cdab
- /home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/simulation_runtime/recovery.py SHA256 70edefdc953cea27c65d9fe6228aaf7be4a062320c306966c5c7f04862857d79
- /home/ningyd/文档/ChatGPT/BIGsmall/tests/test_operational_runtime_closure.py SHA256 c1a68fe0b5ff88bdf604e4859a17da73f61f56b1fd934897f0e66a484d9ae861
