# R475 Astra 补充计划：有上游SHA的依赖镜像获取

实际规划者：`gpt-6-astra`。本轮不改变R473模型/实验范围。

**问题及证据：** pip24 --dry-run 在生成report前完整下载wheel；原始stdout/stderr和context显示915,622,781-byte Torch wheel仅传5,611,520 bytes，速率不足。ROOT仅终止自有resolver PID112466，termination.json记录该行为（父任务报告rc143）；尚无B安装。TUNA HEAD证据为200/同size，只证明可获取，不代表已验证内容SHA或吞吐。

**根因：** 把dry-run误认为纯metadata解析；上游大wheel传输瓶颈使原依赖40分钟预算有耗尽风险。问题是发现/下载流程和传输源，不改变版本、FP8候选或量化要求。

**范围：** 仅在R475或R473本轮artifact脚本添加镜像解析/下载及下载前固定机制，保存原脚本hash/副本和新增报告，继续独立runtime-b。R473计划、旧失败日志及源/模型字节不改。保留torch2.10.0、torchvision0.25.0、Transformers5.22.2、CT0.20.1及已锁直接依赖；传递依赖依原声明解析。禁止系统修改、原venv写入、源码构建或大型编译。

**执行：** 先复核本计划输入SHA，记录依赖阶段最初开始时间、累计耗时和40分钟预算剩余值（不重置）。新增精确policy允许pypi.tuna.tsinghua.edu.cn、mirrors.tuna.tsinghua.edu.cn；保留pypi.org/files.pythonhosted.org用于官方JSON和已允许源。全部HTTPS/TLS验证、enp7s0、AliDNS223.5.5.5/223.6.6.6、逐跳allowlist、无代理/默认网络。镜像index改为https://pypi.tuna.tsinghua.edu.cn/simple，不把HEAD/镜像etag当上游SHA。
允许实际pip resolver进行wheel发现和下载但不安装/执行。必须在每个wheel响应body开始取字节之前设置artifact级下载门：从wheel filename解析name/version，用严格直连取得官方PyPI该版本JSON，保存原始JSON和hash，确认唯一对应filename、上游size/SHA、兼容平台；先追加并落盘不可覆盖的discovery-manifest条目，再准许镜像wheel传输。依赖候选可由resolver动态发现，不要求事先知道全闭包，但每个候选均须先pin后下载；未固定文件、非wheel及sdist一律拒绝。若无法可靠插入此门，禁止让原pip直接下载未固定body；改为逐包读取固定wheel的METADATA并离线解析闭包，不能豁免先pin规则。
下载门同时把真实wheel字节保存到独立wheelhouse-b-discovery，结束核对bytes/SHA，再允许resolver读取其metadata；保证pip临时目录清理不会丢掉已验证缓存。保存每个候选（含最终未选中者）的记录，不执行wheel代码。最终resolver报告保存为新文件，逐条对官方JSON、预先discovery pins、实际cache hash及package metadata复核，生成最终锁定manifest；从已验证cache复制/移动最终选中wheel入wheelhouse，避免二次大下载。镜像URL不能继续触发installer中仅允许files.pythonhosted.org的旧断言；根据精确allowlist验证transfer URL，同时保持独立canonical upstream URL与官方SHA。不得简单取消来源校验。
最终仅以已核验wheelhouse执行--no-index离线安装；若--no-deps必须显式安装resolver闭包全部wheel并pip check。保留原件、argv、运行报告、freeze、模块来源和新路径B的schema/FP8 loader验证，随后按R473真实双图协议继续。

**验证：** 预下载gate以真实一个wheel/现有已固定wheel记录证明pin时间早于body开始时间，实际SHA等于上游SHA；检查全部候选均有先pin记录、最终报告无缺项/重复冲突、相同版本未替换。只做本轮script语法及实际流程检查，不增加产品测试。package依赖check/import通过仅允许继续，不称模型双图通过。

**预算与边界：** 原40分钟依赖预算和R473总3小时均不重置；原下载已花时间计入，镜像失败或估计无法在剩余预算内完成即STOP_BUDGET/BLOCKED_NETWORK，不换版本/无界重试。最多原计划4并发、每网络请求60秒及3次网络瞬断重试；只终止本轮自有PID，保留partial/失败。新metadata无法提供唯一官方SHA、pin不一致、镜像hash不一致即停止；不得缓存污染或继续安装。此轮通过只说明依赖获取流程恢复、完整性和隔离安装达标；真实FP8加载、两图与质量仍按R473分别验收。新的非本轮根因另交Astra。

**固定输入：**完整path/bytes/SHA256清单见同目录plan.json的input_sha256，含AGENTS、R473计划、两个待修改artifact脚本、TUNA发现证据及本轮全部原始诊断；实施前逐项复核。
