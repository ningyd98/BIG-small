# R187：辅助用例证据标签修正计划

实际规划者 `/root/astra_status_plan`；实际模型 `gpt-6-astra`；2026-10-14。仅规划，等待ROOT gate。

独立源码核对确认：_r182_record当前统一写baseline_semantic_hash与semantic_hash参数路径，但四个semantic-edge调用传入baseline.digest()，实际拒绝入口为_r182_decode(changed)。这是将来报告的标签错误，不是运行失败。

## 输入与原件

- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round187-p6-t1-auxiliary-case-evidence-labels-20261014/original-static-finding.json` — 16792 bytes；SHA256 `8da9d2197c86dab7cae439b52e5c29c1b8ee3b490a851750e6fcb356aeaada57`。
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round185-p6-t1-sol-compaction-transport-20261014/root-activation.json` — 83497 bytes；SHA256 `1a16f0a8188d5fdcaaf14f0fb1fe1a8eedd98cb8b5cdc23757f8debe3c73b676`。
- `/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_local_temporal_projection_closure.py` — 12164 bytes；SHA256 `80667bd840499fdb2c5163ba958a5d1bc20551fef70206df3dbe45ffd0c12e91`。
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/implementation/prepare-evidence.py` — 13233 bytes；SHA256 `77cb39339ff2f7aa5d4293174d0fbefb284e9554f16bfd0049c7856516b8e852`。
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/implementation/run-command.py` — 14806 bytes；SHA256 `6dc5ecae7d14fa8d5119b999064f604ca5f0fe5f4c0e6eed6963f28f84de054e`。
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/command-ledger.json` — 12227 bytes；SHA256 `765c2d33144b9d46e0181e1a54b5db0367c25e218d979759f12486888fc47060`。
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/root-command-ledger.json` — 12595 bytes；SHA256 `316934c707f8cc4bf248a385b90fd5e4564479bb3df341ee46b7455f3fc6a9a3`。
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/plan.json` — 136098 bytes；SHA256 `82100de3713beccb61ceeb0da87d40d3cbb6a4552890c6c72337d899fad96c5d`。

R185 root-activation.before_auxiliary.base64已解码核实12164B/80667bd…与当前完整aux一致，原件不改。两个作者脚本针对旧字段/报告名的精确文本检索无命中，但不冒称完整消费者审计。

## 唯一修正

唯一Sol在ROOT全文/输入门后，仅改当前_r182_record函数body：

- 通用字段baseline_semantic_hash改为baseline_hash，值仍为原传入参数；新增baseline_hash_kind。
- 四semantic-edge类别：kind=LOCAL_ENVELOPE_DIGEST；path=`_r182_decode(changed): LocalEnvelope.from_payload then domain.from_payload`。
- recursive/positive类别：kind=LOCAL_ROUTE_INPUT_SEMANTIC_HASH；保留原semantic_hash参数路径。
- baseline_decode_and_accessor_returned保持原值：两类调用此前都真实取得baseline及对应accessor返回。它不表示待测拒绝已发生。

由现有category.startswith('semantic-edge:')选择标签即可；不改helper签名/调用，不增加产品调用或计算，不重算baseline值，不改seed/mutation/hash/exclusive保存/JSON规则。

唯一允许差异是上述三个报告字段。辅助测试其他所有字节、nodeid/装饰器、fixture调用、mutation与断言、所有产品和两个作者脚本保持。旧before和static finding完整保留。

## 验证与边界

ROOT常规source gate用stdlib文本/hash核函数外前后字节全同、签名及调用不改，并审三类别路径。原R182 prepare_red及RED8/GREEN13在原各自槽和门下执行，无额外trial/collector/AST/import/probe/pytest/static/Git预算。可以保存限定diff/change/step等元数据，但不造新验证脚本或slot。

六R182槽和四R179槽均仍0/1HELD，parent3spent12HELD/R175三spent/原review余8不变。脚本独立全文审阅可继续；prepare_red与共享产品修复未在本计划释放。

R184仍为13+38=51 planned，不是PASS。计划只修未来证据标签，T1/T12/native/formal全false。出现其他消费者修改需求、新工具失败或扩域，停止另交Astra。
