# R470 真实替代采集步骤报告

监督器按实际Astra计划修复动态文件枚举竞态，原R468证据未变。新的prepare rc0；唯一替代真实采集启动并执行120物理步、367渲染pass、0完成动作，随后因 `registered marker unavailable: known_marker_not_observed` 成为COLLECTION_PARTIAL。

full child rc1、28.564秒，监督器无内部错误，owner关闭完成，child回收且无存活后代，来源保持e5795af5…不变。监督器记录并容忍限定SQLite临时路径ENOENT，完整保留采样缺口及终态静态inventory，不把现场采样宣称为原子硬界。

独立reader唯一一次rc0、6.691秒，复原123帧；首组source/horizon不完整，其它8组未运行，9组分数及joint bound全null。partial审计另暴露_Audit.domain缺失的捕获诊断，原样保留，未混入标记修复。

累计真实尝试2次（相同首组/seed，替代不增独立样本）。R468仅有下界，因此累计physics下界133、render下界408，精确累计值未知。R470原始数据90,728,782字节/647文件，本地保留，独立读取前后非DB SHA及DBstat一致；DB内容未读取。两轮均云请求0、真实硬件0。

下一步实际Astra R471仅冻结离线像素诊断，不启动第三次采集。R469 Sol仅有计划，尚未CPU preflight/API，当前会话缺少内存密钥。native UNKNOWN；正式研究NOT_ACCEPTED。
