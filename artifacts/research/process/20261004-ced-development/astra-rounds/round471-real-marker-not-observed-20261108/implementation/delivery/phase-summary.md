# 当前源码真实运行阶段总结（2026-11-08）

本阶段实际启动了两次 teacher MuJoCo 采集，均未完成首组。产品源码、配置及资产保持 P0 交付 ae3b88370276ebe0b2782720588c0b52d6c8e1d8 的字节，423项 source generation 为 e5795af5d1a7b90a7dcb442da0f37c0ec9fe4fad04d13e3696c4a5cf609fdd55。

| 阶段 | 实际结果 | 证据和边界 |
| --- | --- | --- |
| R466/R467 | 主机GPU读检成功；报告键检查单独修复 | RTX4070TiSUPER空闲15431MiB、compute空、Qwen停止；原受限rc9及报告StopIteration均保留 |
| R468 | 首次采集因监督器walk→stat竞态中断，rc-15 | 4.088秒；14份冻结帧证明physics≥13、render≥41，精确总数未知；原claim/raw不变 |
| R470 | 修复监督器后的唯一依赖替代采集，COLLECTION_PARTIAL，rc1 | 28.564秒；120physics、367render、0完成动作；原始失败known_marker_not_observed；owner/child关闭完整 |
| 两次独立reader | 均rc0；qualified结果不可用 | R468缺完整inventory，R470复原123帧；9组分母保留、8组未运行、joint bound和group scores均null |
| R471 | 唯一离线像素诊断rc0 | 原4帧生产检测均UNKNOWN，XML位图吻合ID7、合成参考可解码；原图拒绝候选8×7px，具体采样/栅格化根因未定 |
| R469 Sol | 仅冻结计划，尚未实现runner/CPU preflight/API | 当前ROOT无会话内存密钥；历史v1 replay不能替代fresh v2链。4次请求额度未使用 |

R468与R470为同一首组/seed的依赖替代，累计实际尝试2次，不算两个独立校准样本。累计physics下界133、render下界408，因R468没有终态receipt而不能给出精确累计数。云请求和真实硬件运行均0。没有启动第三次采集。

R470监督器保留并记录12个限定SQLite瞬时ENOENT，采样最大间隔0.500085秒，终态采用完整静态inventory及明确排除的最终receipt。现场字节/RSS采样不宣称连续原子硬约束。R470 full样本treeRSS峰277766144字节、waited-child maxrss276463616字节；两种测量口径分别保留。

全量R468 raw（9826539字节/73文件）和R470 raw（90728782字节/647文件）均仅本地，读取前后非DB SHA及DBstat一致，DB内容未读取。交付只包含计划、监督/诊断脚本、协议、日志、派生reader报告、哈希/资源记录和少量诊断图，不是完整远端raw复现包。

P0的软件验证保持为既有交付记录；本轮无产品功能修改，未重跑软件测试。reader在partial审计中另捕获 `_Audit.domain` 缺失，作为独立待处理问题保留，未混入标记诊断。后续修复或扩展诊断先由实际Astra冻结；任何源码/资产新版本均需重新冻结P1来源。native UNKNOWN，正式研究NOT_ACCEPTED。

交付前发现并发文档提交270060bb（proposal/RoboRSI路线6个文档文件）。src/scripts/config/assets/tests对运行baseline ae3b883无diff，既有来源pin不变。保留该提交并在其上追加交付。R472下一层静态方案计划已冻结但未执行；后续先复核新HEAD适用性，不改写旧轮baseline。
