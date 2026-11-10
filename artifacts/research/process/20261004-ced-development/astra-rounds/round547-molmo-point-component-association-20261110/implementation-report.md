# R547 实施报告

实际 Astra 计划13项输入及native-01全部26份raw核验通过。根因是小红块原生点偏在灰桌面，现有原始深度拒绝正确；没有坐标缩放或深度解析错误。

新增 point_association.py，按固定半径/唯一局部完整区域/显式颜色语法提名内部点；所有局部候选先计数，不能过滤不利候选后选最近物体。原生预测、几何采样点与候选证据分别保存，helper源SHA进入证据与factory角色源码清单。直接有色点与放置区点不移动；旧原生provider、CLI、几何、tracker和阈值字节保持不变。

测试先记录33 failed/78 passed；其中25个新helper用例实际被fixture漏sim_time_s遮挡，并非有效功能RED。近邻规划正例原失败，实施后正例及7类旧门拒绝通过。其后28 failed/83 passed涉及25项夹具字段和3项旧证据字段断言；由实际Astra R548仅纠正夹具并保持拒绝断言。最终322相关用例PASS（含38旧tracker、2launcher）；13文件Ruff/diff check通过。诊断note E501由实际Astra R549仅以AST等价拆行处理，历史日志原样保留。

## 运行证据

- OFFLINE_STATIC_DIAGNOSTIC：旧点(179,109)仍被原始几何拒绝；提名(179,119)后静态原几何/轮廓通过。归档采集时间/checksum不变，生产adapter仍以stale拒绝且0定位/云调用。原26份raw均核验。
- REAL_LOCAL native-02：独立新增预算1load/2generations，在新鲜S01 seed0采集上运行，资源/GPU锁/26模型资产和R545 imports/ABI准入全部通过。目标原生(179,109)，唯一局部红区域内部点(179,119)，放置点(130,72)；local_geometry_status=READY、diagnostic_passed=true、exit0。查询1.2120s/0.7846s，加载2.2989s（第二次受本机缓存影响，不作统一冷启动结论），整个进程18.17s。
- 当前未启用真实云端：native-02管线实际为PLANNER_FAILED，原因为诊断cloud明确抛RGBDModelUnavailable。不得将本地几何PASS标为完整云规划PASS。接口PLANNED只来自明确CPU/API夹具。
- native-01永久保留geometry NOT_READY/exit2；累计2load starts/4generation starts且4completed，0paid/0hardware，R547额度已用完，无追加重试。

两次均为真实重新采集，但S01 seed0确定性相同，RGB/depth字节一致，采集时间、episode/observation ID与checksum不同；这是单场景适配验证，不是跨场景准确率、独立样本胜率或正式研究。extent_complete=false、depth bound未给出；无连续控制/物理/heldout/G1/G2验收。原始数据与派生mask仅保留本地ignored边界，native-cumulative-summary.json为摘要，不是完整复现包。

verified-source-manifest.json记录最终源码SHA；native-02-command/result记录实际命令/退出。R548/R549报告与R542阶段总结合并呈现软件、离线、真实本地、云、物理与正式研究状态。

提交后补齐原计划的唯一候选但窗口被图像截断负例，26项helper用例通过；在源码提交51103483ef83b1a7bb2252443f749f15d1c48bc2上完整相关套件322 PASS/1既有warning，原321日志不改写。最终日志见R542 execution/task4-final.log。
