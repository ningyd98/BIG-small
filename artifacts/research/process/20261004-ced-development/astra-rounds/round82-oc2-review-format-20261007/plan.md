# Astra Round82 — OC2 纯格式恢复

状态：仅计划。R80 唯一 Ruff check 因 prefix:708:101 的101列行违反100列限制而失败；原RED4已精确4fail/0error/0skip。format-check、mypy、GREEN13均未运行。两源已逐字节核对R80冻结。

```text
E501 Line too long (101 > 100)
   --> src/cloud_edge_robot_arm/research/operational_prefix_v1.py:708:101
    |
706 |         raise ValueError("exact original returned frame required")
707 |     returned_frame = returned[0]
708 |     original_source = returned_frame.get("source_acquisition_id") or returned_frame["acquisition_id"]
    |                                                                                                     ^
709 |     if original_source != source_id:
710 |         raise ValueError("original returned frame/source acquisition relation differs")
    |

Found 1 error.
```

## 限定执行

1. ROOT核对本计划SHA、listed inputs与R80冻结两源；GPT-6.1-sol继续两文件单写者，其他OC2/RW1独立。新round82 implementation独占保存source-before，R80原E501/RED4/行为范围证明只读。
2. 只执行verification.formatter一次，对这两份文件统一Ruff格式化。允许换行/括号布局/空白/等价引号等纯格式，包含尚未format-check的测试新代码；禁止ruff check --fix、逻辑/标注/断言/fixture/import集合改动。不要先试一次检查再格式化或逐条散成新轮。
3. 保存完整前后bytes/diff，stdlib ast.parse(type_comments=True)整模块ast.dump(include_attributes=False)必须相等；tokenize所有COMMENT文本/顺序必须相等；每个函数/异步函数的参数/返回/类型注释规范AST签名必须相同，旧测试名/参数化/断言也由完整AST保留。失败即停，不删AST节点制造等价。R80受限AST证明只证明行为修改范围，R82此完整AST证明只证明本轮纯格式，二者分别记录。
4. 依次执行Ruff check新一次、原未用format --check一次、原未用四源mypy一次；每个收据保存argv/env/start/end/exit/wall/stdout/stderr，不以格式化成功替代最终静态通过。任何新非零或范围问题保留原件并下一Astra；不自行重复formatter/check。
5. 只有所有静态实际exit0，才消费原GREEN13一次，保持原case清单，JUnit/结果写round82新目录；原/tmp/bigsmall-oc2-round80-review_green必须未存在，已有或软链则停，不清理。RED4/R79targeted8/R03/63均额外0。
6. 保存source-after、完整AST/comments/signatures等价与各哈希、原剩余额度使用表、GREEN13 JUnit和CPU原件分母/partial/DB边界。报告明确R80两行为修复此时才获改后验证、R82只是格式；不同作者独审待完成。actual/formal/Git不由执行者推进。

预算：两owned文件统一formatter一次；新ruff check一次；继承format-check/mypy/GREEN13各一次。RED4、R79targeted8、R03、63额外均0。精确argv/env/先后顺序见plan.json.verification。

通过完整AST(type_comments)、comments、signatures等价仅证明本轮格式不改语义；不得替代R80行为修复的GREEN13和独审。实际运行仍0，正式研究未验收。

## 输入SHA256

| 路径 | SHA256 | 字节 |
|---|---|---:|
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` | 1774 |
| `pyproject.toml` | `b2bf5c4042d568eaf9def415ae7b2f08f0fa541a01f970b7e68e6d950035bb6c` | 2458 |
| `src/cloud_edge_robot_arm/research/operational_prefix_v1.py` | `b01a50ab09a170579a83c87c92cb95387f88ebd9de68634fd62f2833b1cf6843` | 62768 |
| `tests/test_operational_capture_v1.py` | `d3ade71f2a005244ddc469cd793b5955a462b471b19a69bb2c0707da943a11ac` | 26229 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/plan.md` | `cb89b8b576193791a07a379c704f40f534bf57145b5fd0765f9a660c8a1235b5` | 15425 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/plan.json` | `cec68ecba1ee2e020729ffec3b28350e7f20f61ff1e694cec1be785af879b481` | 36690 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/activation.json` | `28e360cb65b21b0d2a60a141d3af9c789f800b94d46bcd5d7258a95b5af584c7` | 19533 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/root-authorization.json` | `b5d8139e6d07f983ee02da4cdf1a56b5671ff4173726107613627cf34002b13a` | 1061 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/step-report.md` | `a5a5a59f4dbef4af722967a2ee72c6156eac23f38ccfeb4306c9cfd8fc8f2534` | 2478 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/step-report.json` | `9e1b1e400327ba0923a60b83a538643952bfeb7bb55a5d5c4f0ace76fe2f21c8` | 6798 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/failure-receipt.json` | `9e1b1e400327ba0923a60b83a538643952bfeb7bb55a5d5c4f0ace76fe2f21c8` | 6798 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/source-freeze.json` | `f67ed727d8ee465f706f54a6772b23d7285f67ce8f17ecb3769a1efedceb10b2` | 325 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/restricted-ast-proof.json` | `ef26c6bb44f1716499f9cc507daa7b3ac67e8f9f34b39347e2d7eadea1f4e3a6` | 2651 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/ruff_check.stdout.txt` | `226276ff607bc08d481ffa0fc5c5efa2736aecfbe9aca5baa42a27dea4f9c18f` | 598 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/ruff_check.stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/ruff_check.command-start.json` | `1d6940d9c86cd0fe800da6c944028d11dd987280616aed511a2e4cc86897c31a` | 490 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/ruff_check.command-result.json` | `0107c68c3c69e07c004378da79773ef00679c0c44215b910c687ae40dac3979c` | 596 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/review_RED.command-result.json` | `f98881f34df2d7de057397dd2accb52540657a95e8d2695faf39b81ab8c895c2` | 937 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/review_RED.junit.xml` | `ee2b343f23b25a8236ad3acb0670d8e6da4fa70699ded0743f90bdac76d5b28f` | 9905 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/review_RED.stdout.txt` | `05e00186708674376e72f0bd470cc4db20aa4cad43cc23432e5d5504eb6ef0e1` | 9389 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/review_RED.stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/source-after/src/cloud_edge_robot_arm/research/operational_prefix_v1.py` | `b01a50ab09a170579a83c87c92cb95387f88ebd9de68634fd62f2833b1cf6843` | 62768 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/source-after/tests/test_operational_capture_v1.py` | `d3ade71f2a005244ddc469cd793b5955a462b471b19a69bb2c0707da943a11ac` | 26229 |
| `src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py` | `918e029a6a1f0d2a7a455820c721118abdb50b7c5eda6e8ee15f54bed543e67c` | 11537 |
| `src/cloud_edge_robot_arm/research/operational_capture_v1.py` | `06373a9c702420ab38c5afa20f888efb35cd6ea109cf094c662fa04511e60b3c` | 14778 |
| `scripts/run_operational_prefix_v1.py` | `fe8e8c9e021ec437b601895de724f1d10f17eb221fea6b8302c304a65fbcffa9` | 1885 |
| `src/cloud_edge_robot_arm/simulation_runtime/worker.py` | `31cea6501ee9286ee933335f013422314985726036c8029844929cc96be2fdb4` | 80239 |
| `tests/test_operational_prefix_v1.py` | `1ccb56de190f5cea0280882690bead41ed15aaff0fdfa2b74b32ca9c5cd1b426` | 11934 |
| `tests/test_operational_prefix_cli_v1.py` | `f3cc2a0d2de8fb18dbcfa3c9b9969d92f657fd03b448b7cda7c58d5926480cfc` | 6546 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round80-oc2-review-repair-20261007/implementation/unrun-verifications.json` | `f604a1ab0989e2b8f8049ee9b75a2d0d3ebeea8b6540979941dcf119f7e0967b` | 348 |
