# R388 最终状态断言步骤报告

原tool chunk b6101f的stdin line13把porcelain v1预期为小写m，实际只返回两个原gitlink的大写M；错误事实转述见failure-intake.json，原stderr仅会话留存。两次正常push均已成功，13579b8工作区checkpoint与67d0243首次收据已经在远端；失败发生在三SHA已相等之后，不是push或产品失败。原生final-status的无损副本见original-status.porcelain-z，补充v2两行S.M.原样保留。

实施前由实际gpt-6-astra制定R388，复核全部输入SHA256、原index SHA与计划适用性。仅新增本轮行政文件：独立新验证器按NUL及原始bytes精确匹配大写M和两个完整路径，另查tree/index mode/OID/stage、nested HEAD、非gitlink差异、空stage、0/0及本地/上游/live远端完整SHA。读取设置GIT_OPTIONAL_LOCKS=0，前后index hash必须一致；禁止宽泛放行或隐藏dirty。原冻结证据、源码、测试与嵌套内容均不改。

旧status原字节解析与验证器语法已核对，67项CPU与完整fsck原通过证据hash保持，没有重跑。经精确路径/凭据/尺寸/空白/index字节核对后，仅一次小型行政记录commit/push。最终门在本次push之后运行；其实际终态、原生输出hash及最后SHA独占写入本机.git/r383-github-delivery-20261102/final-receipt.json，并在用户答复报告。不再提交最终收据自身SHA。
