# R177 — 原生补丁传输格式恢复

实际规划者：gpt-6-astra（/root/astra_status_plan），2026-10-14。冻结后等待 ROOT 激活；本轮只规划。

## 原问题与独立结论

唯一作者调用 tools.apply_patch 时实际报错：Failed to find context '-15,11 +15,11 @@'。没有结构化工具返回、数值进程exit或独立stdout/stderr，原记录这些字段为null；不能称pytest失败。作者当时partial write未知；ROOT及本轮随后实读证明当前两脚本仍精确等于失败前草稿，原未知记录不改写。

原提交确实保留 `@@ -15,11 +15,11 @@`，并未去掉@@。错误是将统一diff的数字行号头放入原生apply_patch；数字后缀被当成文本上下文定位，首hunk因此拒绝。原JS、补丁、diff、工具错误、prepared-source五原件完整保留。

312项只读检查全部匹配。准备后文本的数据重建与实际统一diff相同；CHANGES字符串未变，真实R174六raw辅助定位准确、候选pin固定、既有线程字段核对及原保护/账本/捕获要求未削弱。只接受既有R176修正，不增内容。

## 唯一恢复动作

ROOT核计划和输入后，sole gpt-6.1-sol作者将原补丁每个完整数字hunk头替换为单独一行 `@@`，其他上下文/加减行、两文件顺序与hunk顺序逐字保持。保存native-patch.txt，ROOT全文审阅确认只有头格式变化。随后仅允许一次新的原生apply_patch调用，两个Update目标固定。

prepare-metadata.py成功后必须为61758B，SHA256 23d4ffae9df8d3a136220fad817d159db2b15481767e937d9613f5b2ccd055fb；run-recovery7.py必须为26815B，SHA256 aaec096c4047d2ee5ed4db6faef5db018c5fe244f3320a0c17f8b794ca940399。完整before/after SHA和输入见JSON。不能另改语义、改helper或回退/重做历史。若新补丁失败立刻停，无备用写法或第二次尝试。

## 门控和边界

ROOT核对原78输入、211保护、当前helper与两脚本before；修后只读验证exact after及保护连续性，保存真实工具返回和步骤报告。ROOT独立root-settlement.py不是修复目标。

新增验证运行次数0。原R175三个槽两角色均0/1，仍按原完整gate顺序各一次120s/600s/120s；R1583spent/12HELD及所有旧账本不重置。R176真实stdout/stderr捕获合同继续有效。不得执行AST、compile、import、pytest、SQL、probe、Git或网络来试补丁。

本轮最多恢复两个脚本的正确落盘，不授予任何软件/真实/正式验收。原R174七PASS、R158五PASS两FAIL、全部旧失败证据保持。

