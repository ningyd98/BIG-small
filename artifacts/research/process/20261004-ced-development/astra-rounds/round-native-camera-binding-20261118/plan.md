# Astra：全部相机回退绑定与显式MuJoCo标定核验

实际 `gpt-6-astra`，2026-11-18，PLANNED_NOT_FIXED，输入SHA见JSON。只读规划0GPU/API。原审查报告含完整CPU复现脚本，无另存原stdout日志；新RED必须持久保存脚本、日志和JUnit，不能虚构旧raw。

两项确证：fixed02 MOVE sample0105要求view01，误返回不同机位且晚8物理步的sample0106仍提交；PLACE sample0015-view01只把标定改成1111111111111111并重封包仍通过，原正确标定d7ed4da1b0052f10。原因分别是回退绑定仅位于nonplanarity分支，及只校验版本是否变化。真实后端归档绑定正确，未观测到这些故障引起实际错误动作。

1. 先以报告中的真实归档像素CPU RED复现两项，再加普通marker/各region错误、混合第二次nonplanarity、错误位置/旋转、推进或倒退时刻、重复ID、伪标定反例。原帧保持不变，测试clock只还原其原采集时刻。
2. 所有fallback attempt>0在update提交前共同核验：请求的完整光学外参（位置与朝向）、与本次首帧相同sim_time、新唯一ID、不同相机。按既有position/look-at与世界Y-up计算期待外参，保留浮点转换所需紧容差，不扩大几何容差。普通错误和非平面混合不能重置两视角/期限。reobserving标志只管特殊proposal和RETREATregion语义。任何绑定错立即STOP，不再当可恢复错。
3. 显式component调用传严格bool/defaultFalse的MuJoCo标定校验。参考帧及每次采集均按生产camera.py规则：四内参+十六行主序外参，小端float64，SHA256前16hex。外部相机默认字符串版本语义不改，不凭帧自报source启用。生产输出字节不变。
4. component每个sample从首capture前绑定后端step/simtime和命令游标，换机位/采集前后及返回target前检查物理不推进、无joint/其它执行命令，仅允许期待相机命令。检查新增命令后缀，不在热循环复制全部历史。拒绝不得污染accepted状态；保留原渲染配对状态校验。
5. CPU真实帧正反例与既有安全回归通过后，仅1次完整零API原协议GREEN，EGL+共享GPU锁，模型网络硬阻断。原8技能/9段及终帧效果、worker完成和独立物理成功全部验证。保留sample+IK≤100ms、max2、2mm、TTL和所有安全门；不加GPU探查或单独GPU RED。

fixed01失败、fixed02/03真实成功、44101 MOVE4200缺角失败永久保留，不重试、不针对44101调参。总真实cap仍7cloud28local，已耗4/16，余44102..44104仅3cloud12local。补门和唯一协议GREEN后冻结新source SHA再启动余3个，逐条注明源码版本变化：这是开发表征，不冒同一源版本或formal holdout。预登记严格几何安全STOP按失败样本保留并可继续下个未运行seed；安全绑定破坏/基础设施错误/新计划外根因则停止交下一轮。每项120s、0retry、1cloud4local，旧失败不得替换。

控制器/轨迹/视角排名/几何噪声阈值/期限/H1/P12/UTC不动。本轮软件门通过不授予正式研究资格：formal NOT_ACCEPTED、qualified_groups_added0、真机NOT_STARTED。
