# 阶段1–3交付记录（2026-11-15）

本轮已完成 V3 原样冻结、SUBPIX 标记身份歧义修复，以及冻结外部模型输出条件下的离线回归。原27成功项在新真实 worker/MuJoCo 闭环中全部通过。全仓库验证和正式研究验收仍有下列明确缺口。

| 交付 | 结果 | 可核验证据 |
| --- | --- | --- |
| V3 基线 | 594项输入归档；591项仓库文件；8项Gemini未提交修改逐字节保留；原始27/40结果未改写 | ../v3-baseline/snapshot.json、verification.json |
| 标记身份修复 | 回退核对全部50个字典ID和四种旋转，保留外来与重复候选，由现有唯一标记规则拒绝歧义；13项新增回归 | ../software/marker-step-report.json；RED/GREEN日志；修复commit3ef1e028 |
| 定向软件验证 | marker九文件348通过（最终再跑348，11.72s）；离线纯软件/既有planner228通过；真实安全与网络边界11通过；原worker/手指/安全64通过。各组合有重叠，不相加 | marker-final-contract-tests.log；../software/offline-final-pure-03.log；offline-final-boundaries-02.log；offline-tool-step-report.json |
| 589历史帧配对审计 | marker及完整geometry逐帧字典零差异；529 OBSERVED、60 UNKNOWN；新增grounding拒绝0 | frozen-frame-audit-summary.json；local-raw-evidence-references.json |
| 原27成功项正式离线回归 | 27/27：fixed10、development9、旧held-out8；每例新进程、8动作、16 PRE/POST、一成功attempt及已释放lease | batch-result.json；final-offline-evidence-verification-02.json |
| 最终证据独立重算 | 141444物理样本、4806清单文件、432实际PRE/POST、540新闭环帧；各例599项来源和三入口SHA不变；0新实验模型请求、0记录到的网络尝试 | verify-final-offline-evidence-02.py/log/json；delivery-integrity-01.json |
| 独立代码审查 | 实际gpt-6-astra；原7项阻断/范围问题已关闭，原失败回执原字节保留 | independent-final-code-review.md/json |

589帧审计属于静态反事实证据，不等于589次grounding成功。27初始深度不可用帧、3帧缺少原始pre-state、非动作诊断帧和合法UNKNOWN均在审计分类中保留，未将它们改成成功。

27项回归使用原始Molmo点和Sol响应，严格绑定当前真实请求和观测；实际解码、grounding、控制、PRE/POST和硬状态安全判据重新执行。没有直接重放旧动作列表。每例4次点回放、1次云响应回放不计成新模型调用。Python进程网络守卫覆盖当前调用路径与线程，其证据不声称为任意原生代码提供操作系统防火墙。

渲染在与原冻结输入匹配的已批准EGL运行环境中执行；默认沙箱曾产生不同图像，旧失败保留，原因未得到硬件层实证。GPU厂商/设备在运行回执中为UNKNOWN，不作NVIDIA归因。没有更改MSAA、相机、噪声、手指轨迹、物理模型或成功/安全阈值；39mm张开目标、0.1mm手指容差及用户选定控制器保持原值。

最终汇总脚本第一次错误地要求事件流最后一条就是SUCCEEDED；真实worker先记录job_completed，再追加artifact_created。实际Astra另立最小计划后，仅对/tmp新编号副本改为检查唯一job最终状态、最后非空状态和成功事件，保留全events及数据库SHA；一个正对照和六个负对照通过。旧失败脚本/log在对应计划包中保留，物理、来源与清单判据未放松，27例没有因此重跑。

## 验收边界与下一轮

- 全仓pytest未完成：600秒超时，exit124，约2%处观察到5个失败标记；尚未逐节点诊断。定向测试通过不能代替全仓通过。
- 27/27仅针对原27成功项和冻结外部输出，是配对回归。原40项历史成绩仍为27/40；旧held-out曾参与诊断，8/15不能当新泛化证据。没有新的模型端到端成功率、硬件抓取或正式研究验收结论。
- 原13个失败项本轮没有修复；5例边缘深度的MSAA尖峰归因仍缺逐像素证据。下一轮先定位全仓失败/超时，再按独立根因生成Astra计划；深度失败先补逐像素证据和深度判据方案，手指轨迹改动与付费40项/新seed运行另依用户决定。
- 公开推送与新增付费Sol/Molmo实验保持延期。本地研发分支codex/v4-marker-ambiguity-20261115保留；本轮未推送。

## 交付与保留

本轮源码冻结在本地commit8ebad9f6ee7dc59cafdfb92dc8a2cb54463ba926；前置基线commit57c4dc0d855f5410fcf497edf47b43cfd24ad74b，标记修复commit3ef1e028ccd471f887eb5b8154c98c3eb9ccfb82。最终证据提交仅增加报告与最新Astra计划，不更改运行入口。

全部raw、runtime.db、589完整配对JSON与本地源码归档留在隔离工作树，受Git交付边界排除。local-raw-evidence-references.json只给路径/长度/SHA；本目录为源码、原始失败、派生报告和清单的交付，不是完整远端复现包。最终415项活动SHA256SUMS条目和594项原输入核验通过；历史superseded manifest的相对引用缺口原样保留，未宣称其自包含。

执行裁决、环境限定、原计划及所有计划外失败处置见execution-ledger.md与八个Astra轮次目录。优先保留用户要求的冻结证据与账本；未按技能的清理建议删除它们。
