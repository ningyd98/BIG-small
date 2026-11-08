# R467 报告键检查修复

按实际Astra计划，将JSON对象成员检查改为result键，并要求唯一结果。仅后处理已有主机诊断raw，严格解码三条命令的stdout/stderr并核对SHA256。输入原件及StopIteration失败保留，未重跑诊断或工作负载。
