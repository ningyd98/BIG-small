# R213 — 已存读取回执的精确文本核验

实际规划者：gpt-6-astra（/root/astra_status_plan），仅计划。

07b929 是 ROOT 元数据 checker 第9行复合断言失败，不是R211读取或测试失败。原checker完整子进程source未导出，转录不能冒充原字节。独立核对发现：已存f34a43回执退出0、target SHA/范围/产品false/命令一致；输出4486B，text有109个真实LF、0个literal反斜杠n，严格chr(10).join全文相等，literal反斜杠n.join不相等。精确旧转义层保留未证边界。

ROOT只准备一个新的stdlib核验文件，先全文审阅并记录其真实SHA，再单次120秒运行。每个子检查具名保存actual/expected/boolean；精确比较完整文本和UTF-8字节，不strip、不替换换行、不跳字段。完整result独占新写，stdout≤2000B摘要，实际返回原样保存；任何失败不写acceptance、不自动重试。精确argv/env、5输入、检查项与路径见JSON。

原R211 reader已spent1/0绝不重跑，原07b929和receipt永久不改。新额度仅一次ROOT元数据核验，产品/测试/静态/Git等0；不改父账本。全部实际检查通过后才native保存R211 root-acceptance并恢复writer准备，其余五节点可独立继续。此验收只证明读取回执完整，不证明T2/T12/native/formal。
