# R241：native 源末行表示的精确重建门修正

实际作者：gpt-6-astra（/root/astra_status_plan）。只冻结计划，未修源、未执行新门。

ROOT 5fc602 实际 exit1，首个 native 重建末尾全字节比较失败；失败发生在完整before归档和角色预约之前。原checker、完整回执和四份native原串保持。两角色实际仍HELD0/1，七项门输出实际不存在。

两条链已分别做纯文本核对：observer单hunk、runner七hunk全部唯一匹配。原算法重建observer为17093/8d672f…、runner47446/cfc4b7…；冻结源分别17092/7b3080…、47445/9bcd169…。每个实际源全部字节都是重建的完整前缀，差异严格只有最后一个LF：原算法留下两个末尾LF，实际一个。无中间落盘快照，不能声称是哪次native内部做了规范化，更不泛化工具行为。

ROOT仅创建R241新checker，来自原13787字节checker，精确替换reconstruct函数；其余字节完全一致。替换源码完整载于plan.json。先核固定全量重建SHA/长度、目标路径、hunk数、恰好两个终止LF，再仅删除该一个末尾LF，并强制与固定最终SHA和当前全字节一致。禁止rstrip、泛化忽略空白、仅语义比较或跳过native检查。两冻结源和所有旧原件不改。

ROOT全文审核新checker/limited diff/输入后，仅一个独立120秒元数据槽执行完整新门；原408/current27/211/history321/24DB72sidecar及角色/CAS检查全部保留。stdout≤6000字节，独立流和actual完整保存，失败STOP不重试。它只完成原R239源码门与既有预约，不启动诊断、不把预约记成实际执行，也不增加或重置诊断/测试额度。成功后仍由ROOT另发literal给唯一Sol。

18完整输入SHA、两链精确关系、完整替换源码、argv/env、输出与角色边界见plan.json；input-observation.json保留全部实际文本/schema核对。产品、T2/T12与诊断结果均未宣称通过。
