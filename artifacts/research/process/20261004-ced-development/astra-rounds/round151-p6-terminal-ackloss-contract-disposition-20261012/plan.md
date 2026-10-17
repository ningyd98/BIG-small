# R151：终态提交后失确认的合同裁决与独审恢复

实际规划者：gpt-6-astra，2026-10-12。冻结待 ROOT 激活。完整路径、输入 SHA256、剩余读取和原同步额度见 plan.json。

## 原始发现与裁决

R150-B1 原 STOP Important 候选报告及补充说明全部保留。独立核对 stop-authority-index 的12份原件均匹配。终态COMMIT后同连接关闭或confirm/consume失效的精确触发尚未实际复现，无新fault raw、pytest或运行traceback；不得把源码推演写成已观察反例。

源码事实成立：SQL实际COMMIT在reread/private ack与broker确认之前；后续异常会撤回本次promoted公开文件，保留unconfirmed诊断并写accepted=false。已落地的SUCCEEDED job、ended attempt和released lease不会被负向cleanup覆盖。

这些事实不支持“未转REVOKED所以仍有权限”的结论：
- R113 design75–82明确区分SQL COMMITTED与broker ACTIVE；失ack保留committed行作为不授权的证据，safe cleanup为may。COMMIT是持久化变更的线性化点，不是单独的live execution authority。
- final confirm/consume并非纯transport ACK，它确实fresh-read原hard-open bound并影响私有ACTIVE；当前broker747–754同时要求精确generation/digest且拒绝TERMINAL。
- R127 Task3禁止无权覆盖已经terminal success；当前终态历史保留符合该边界，不得为了消除表面矛盾把SUCCEEDED改失败、重开attempt/lease或增设第二activation。

公开消费事实另行保留：protected service.py的run/attempt/artifact/batch路径直接呈现SQL状态与artifact_paths，没有读取rejection.json或明确“出版已确认”标识。因此不能声称公开reader已有unconfirmed veto。本次没有发现把这些字段单独当broker权限或已验收物理/正式证据的消费者。该公开呈现缺少区分是明确的B9规划输入，限制所有“完整出版/消费者闭合”主张，不静默略去。

裁决为：**本候选不足以证明受限StageA租约权威的新产品缺陷；不授权产品修复或新测试，恢复独立终审。** 这不是总体软件通过结论。已有40unique四次实际运行也未覆盖精确final-COMMIT故障，保留该覆盖边界，不据此伪造RED或追加无关全套回归。

报告分类也需在新说明中纠正：R134 S是dataclass证据序列化，C是异常安全清理，F是真实commit-close fixture；R147才是foreign fixture修正。旧报告不改写。

## 独立终审恢复

原 R150 TrackB 共24批，实际已用7，继承剩余17；不重置、不新加读取额度。ROOT激活后原独立reviewer /root/p6_a_review 从第8批继续，沿原 .venv stdlib/text、flat index.sources、每chunk≤600行规则。前两失败与三次未经计划替代读取永久保留。

新终审报告输出 /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round151-p6-terminal-ackloss-contract-disposition-20261012/review/final-review.md 与 final-review.json，不能覆盖原R150 STOP报告。完成尚未完成的raw/fixture/type-proof/foreign-delta和E1–E7/G1–G4/R134S-C-F审查，纳入本裁决和公开消费者限制。Reviewer可以提出不同、具体的新缺陷；本计划不要求其给出PASS。任何新故障先停，不在此轮修复或试跑。

## 原事实同步

可复用已经全文审阅且本轮pin的原脚本：
/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round150-p6-metadata-lifecycle-and-review-recovery-20261012/implementation/sync-facts.py
SHA256 5f57c8110c0a546474410ecaed4fab88d22d734bfe326258ea61761fbf441fe5。

原R150同步额度仍used0/remaining1，本轮不新增。ROOT先核实际2605checks全有效及输入未漂移，再按原额度单次预留执行；保存真实输出、exit、before件和sync-report。脚本保持原字节、原受控字段、exclusive before与并发比较，不改变P6验收/Git/冻结历史。状态只同步40unique四run/0remaining/终审待完成，不能以本disposition自动授予A验收。

## B9明示交接与验收边界

ROOT在本轮next-b9-inputs.md/json记录公开SQL历史状态与confirmed publication的区别，连同service/producer pins带入下一实际B9计划。未来如要承诺已确认结果，应定义真实消费者、版本化状态及故障证据，保留SQL历史、拒绝无权重写；是否需要final COMMIT-close/确认超时/原bound到期专门测试由未来精确计划预算决定，本轮不执行。

全轮零产品/测试变更，零AST/import/compile/collect/pytest/static/SQL/probe/Git/native/actual/formal。A可能的最终软件上限仅 LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO；独立终审尚待，B/C/D、P6整体和实际/正式研究均不获验收。

