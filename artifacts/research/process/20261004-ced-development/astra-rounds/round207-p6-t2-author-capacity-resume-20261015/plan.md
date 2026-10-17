# R207 原作者容量失败后的有限恢复计划

实际作者：gpt-6-astra（/root/astra_status_plan）。未发送恢复任务，待 ROOT 审核。

平台报告原 gpt-6.1-sol 作者容量不足。原件只有收到的精确消息/状态转录，平台 raw object、退出码和独立流均不可得；不得把 ROOT 文件核对的 exit0 当平台成功。

已正常核对：部分测试184086B/fef7cf…，旧168003字节前缀完整；runner20824B/940d…未变；19个产品 baseline 匹配；T2两角色各0/1 HELD，5份准备报告和R206 before仍缺失。测试尾部尚未据此认定正确。

- [ ] ROOT 全读输入并独占保存完整 partial test、runner before及清单；核19基线和角色。
- [ ] ROOT 仅一次 followup_task 到原 /root/p6_stage_b_sol，保持实际 gpt-6.1-sol，不换作者/模型。
- [ ] 原作者从当前部分成果继续既有 R204 准备和已批准 R206 stdout-only 修改，不重放旧补丁或运行任何测试。
- [ ] ROOT 保存真实恢复结果，仍须原源码/测试/runner完整门禁；再次容量失败保全并 STOP，不循环重试。

零新增产品、测试、静态、Git 或验证管线额度。所有旧槽不重置；恢复成功也不等于 T2/T12 验收。精确 inputs/before路径和一次调度限制见 plan.json，19源 pin 与当前缺失事实见 input-observation.json。

