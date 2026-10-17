# R211 — writer fixture 路径读取恢复

实际规划者：gpt-6-astra（/root/astra_status_plan），仅计划。

原 a2ec9b 退出2：前两段源文本已返回，第三段猜测 tests/test_visual_verification_route.py 不存在。完整原返回和204898字节 before-test 原件保留；缺失第三段不能称已读取，无产品/测试失败。

真实文件清单 b55645 已发现 tests/test_visual_verification_repository.py；头部及声明核对确认 source/request_for/next_frame 分别位于32/73/92，第一测试从111开始。ROOT审核本计划后，同一Sol仅一次读取该文件1–110行，先核完整bytes/SHA，输出≤24000 UTF-8字节，120秒上限；精确安全source/argv/env在JSON。禁止重跑原命令或前两段。

新额度只有这一次纯元数据读取；产品/测试/静态/审查/Git新增0，T2原两槽仍HELD。实际返回先store并原样保存，独立流未提供则null。失败立即STOP，不换路径重试。ROOT核实后仅恢复原R204 writer准备。

before-test.py是不可变历史快照，不要求合法独立append后的current test仍等于它，不回滚其他正文。R211不改代码或扩大夹具范围；独立R204工作可继续。成功也不证明T2/T12/native/formal完成。
