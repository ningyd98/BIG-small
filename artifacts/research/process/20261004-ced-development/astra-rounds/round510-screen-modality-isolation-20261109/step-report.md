# R510步骤报告

生产AST回归RED后，按mode筛选lookup，延迟按mode分列，输出score-03独占新文件；原score-01/02保留。62项检查PASS。Lens/Molmo真实旧结果除scorer SHA与预登记latency结构外逐值精确一致；原延迟数值不变。Rynn100调用封存后评分：box/point联合均7/12，拒答0/4和1/4；单/双图JSON联合4/12和5/12。独立读取原i32实例图验证其命中计数、coverage。1702个已冻结raw/运行/协议文件前后hash保持。此轮仅离线，不增GPU调用；无正式或实机验收。
