# R382 浏览器准备证据隔离计划

实际规划者：gpt-6-astra（/root/astra_r380_r381_plans）。仅规划，未实施搬移，未运行浏览器、服务器或产品。精确57个输入 pins、25对源/副本映射、5条目标路径见 plan.json/input-audit.json。

原准备器按 R374 research stage 父路径前缀筛选，误把5份历史 invocation.json、result.json、stdout.log、stderr.log、junit.xml 与正确 backend.py+19 fixture 一起复制，因此最后预期20的断言得到25。根因是准备筛选混淆“运行输入”和“历史执行证据”，不是产品失败。原始 assertion 由主执行者报告；未提供落盘 traceback，不重造、不重跑以获取假原件。只读核验确认25份副本全部与 R374 原件 bytes/SHA一致。

限定修复：将新 R377/implementation/browser_research_green 根目录的这5个已列明副本，完整保留搬到 R377/inputs/ARCHIVAL_NOT_ACTIVE/r374-research-miscopied-transport/。可先独占创建 archive 副本、逐项验证原 bytes/SHA、再移除活动根的已验证副本；也可安全无覆盖的同文件系统 move。原 R374 一字节不改，正确20个输入不重写。归档区独占写 origin-receipt.json，明确历史 R374 来源、误放位置、归档位置、哈希、搬移时间/原因、tests_executed=false、counted_as_R377_result=false。

实施前核对全部 pins、活动25文件精确集合、归档目标不存在且无 symlink 重定向；确认研究实际运行仍未启动。若已有新真实 invocation 或不明漂移立即停止。搬移后验证活动文件恰为20，五个保留输出名均不存在；正确20 unchanged，R374全部25 unchanged，归档5与原件一致。记录 before/after inventory、校验和步骤报告，归档必须在 active stage 与结果收集范围之外。未来准备只选明确 backend.py 与枚举19 fixture，不再按宽泛父路径选取。

这是独立 artifact 整理，不修改产品/测试/adapter/runner，不运行行为验证，不复跑旧研究，不触碰正在运行的 R380、不发送信号。单次本地准备及核验上限120秒，无普通重试；R377预算、round-start、正式研究状态均不变。中断后的半搬移先按每项哈希核对并保留，不覆盖未知文件或 broad delete。

验收只证明历史证据正确隔离，不能当作新的 R377 PASS/运行回执。R377后续仍按原计划真实新执行，且须等待串行行为锁释放。当前 workspace-write/network restricted/.git只读，所有写入仅新归档/本轮报告。
