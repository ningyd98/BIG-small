# R484 Astra最小交付计划：冻结证据空白例外

实际规划者：`gpt-6-astra`；仅规划，未执行Git交付。

**问题与原始失败：** 临时index完整git diff --cached --check返回rc2，144376-byte stdout指出12个冻结原始证据文件的尾随空白/末尾padding；无当前实现或报告违规。完整stdout副本本身包含引用原字节，也须同样冻结。共享index SHA前后相同。preflight selected_paths_match=false来自检查中断后未执行比较，应解释为NOT_RUN，不能宣称测得路径不符或已经路径通过。

**范围：** 只修交付判定与证据分类；本计划精确冻结13条例外（原12文件+R484原始diff stdout），不修改它们任何字节、不改.gitattributes/全局whitespace规则、不过滤原日志。允许更新本轮delivery-preparation/evidence-manifest/报告以包括R484与已知原检查rc2、创建独立研发分支提交并push；不改产品/模型，不改共享checkout/index、其他分支或已有历史。

**执行：** 实施前逐项复核本计划输入及13条例外path/bytes/SHA，例外仅限这些已知不可变原件；新异常路径不得用通配符纳入。保留完整原check的rc2、stdout/stderr及原因，在交付报告写full_whitespace_check=KNOWN_FROZEN_EVIDENCE_FAILURE，不能标全量PASS。对精确选定文件集合减去13条的其余文件，用默认git diff --cached --check及显式路径执行，必须rc0；例外继续逐字节SHA检查，不能只检查文件名。新的检查原始输出先存/tmp，若需要提交含原始行的新副本，则先固定其完整路径/hash和来源为追加证据清单，不更改原件或把原件内容清洗。
更新选择清单覆盖R473至R484共12个明确目录，维持已有排除__pycache__/*.pyc/delivery-receipt.local.json及完整raw/cache/venv边界。evidence manifest涵盖R484及计划/诊断/执行报告，按既有非自引用规则记录manifest自身不纳入自身hash。用NUL精确文件清单验证选中文件与相对指定父commit的临时index差异集合完全相等，文件blob也与清单内容hash吻合；把旧未执行比较保留为NOT_RUN，新比较单独记录实测PASS/FAIL。
使用独立GIT_INDEX_FILE、read-tree指定父54dbc6cfdff0e047fa3ba5a512f835eb2c3776c7、精确pathspec staging、write-tree/commit-tree建立仅本轮artifact提交；提交前复查父commit存在、共享HEAD/index hash未变、差异范围与秘密/大权重交付边界正确。只创建codex/taichu-fp8-dual-image-20261108新ref，不checkout、不重置共享index、不amend、不force push。若同名ref已存在先验证是否本轮已建立的同一提交，不能覆盖不明现有ref。
推送该研发branch并设置upstream，保存local branch commit、upstream tracking commit及实时git ls-remote对应refs/heads值，三方须完全一致；同时记录commit parent正确、共享HEAD/index仍不变。写本地delivery-receipt.local.json（按既有排除规则不纳入其所证明提交）防止自引用SHA循环。若push/审批/网络受阻，保留原失败和本地commit，如实报告未完成远端同步，不改历史补救。

**验证和验收：** 验收同时要求13条例外SHA不变、其余明确路径默认whitespace检查rc0、全部原检查rc2完整保留、选中文件集合/blob与临时index一致、仅12目录差异、父commit正确、共享checkout/index未变、local/upstream/live remote SHA一致。这证明受限artifact交付，不是全量whitespace通过、完整远端复现包或模型质量通过；实际生成兼容和0/4质量结论继续按已有报告。

**前置与边界：** 仅执行用户已授权研发交付；遵守平台对Git元数据写入的正常审批，不通过绕过权限操作。预算15分钟（仅交付，不新增推理）；若发现新增非冻结文件空白问题、hash漂移、实际路径不一致、分支冲突或新根因，保留证据暂停相关更改再交Astra，不改原件使检查通过。

## 精确冻结例外

- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/diagnostic/default-gpu.stdout` — 145 bytes，SHA256 `1d58470512e583a0acfabf6896ee5f31e5b493b8231aed54b864f64eb275b02c`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/diagnostic/official-fp8-files/README.md` — 23180 bytes，SHA256 `9de8cda4692f49d10e4658dedec6553107643f64cfcd524b9de2eccc7ed2fc33`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/diagnostic/official-fp8-files/image_processing.py` — 10095 bytes，SHA256 `a68a34f5426b1886f5904f0b75940737a67caec2006a3ddf9387a199b6b10303`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/steps/model-run-b.stderr` — 2117 bytes，SHA256 `f88f9dca2f798c8df851d8ada1ae9e9e13dec4e7fc6102c9157bb8e4475a54fd`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/steps/processor-a.stderr` — 1099 bytes，SHA256 `0619ca4c1ff8c52c6a2fd0c6fca637874621d68abbc920b34478bfd294306bca`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round476-taichu-tensor-evidence-bytes-20261108/diagnostic/processor-a.stderr` — 1099 bytes，SHA256 `0619ca4c1ff8c52c6a2fd0c6fca637874621d68abbc920b34478bfd294306bca`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round478-taichu-loader-api-scope-20261108/diagnostic/checkpoint-header.raw.json` — 141216 bytes，SHA256 `e70c6eda674727572c878dabfd1445aad487dc856bf9622d443fed9d86cf7896`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round478-taichu-loader-api-scope-20261108/diagnostic/model-run-b.stderr` — 2117 bytes，SHA256 `f88f9dca2f798c8df851d8ada1ae9e9e13dec4e7fc6102c9157bb8e4475a54fd`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round478-taichu-loader-api-scope-20261108/meta.stderr` — 2783 bytes，SHA256 `2c8c1a4c3675684efc61c0364308866ccb653aa0033207e06bbe98d33b61cb7e`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round479-taichu-meta-sdpa-propagation-20261108/diagnostic/meta.stderr` — 2783 bytes，SHA256 `2c8c1a4c3675684efc61c0364308866ccb653aa0033207e06bbe98d33b61cb7e`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round479-taichu-meta-sdpa-propagation-20261108/meta-v2.stderr` — 2398 bytes，SHA256 `e0b23762596c01e7e862d42b434e9d778078dc77689394095d3e943ced35d32f`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round480-taichu-empty-weight-skeleton-20261108/diagnostic/meta-v2.stderr` — 2398 bytes，SHA256 `e0b23762596c01e7e862d42b434e9d778078dc77689394095d3e943ced35d32f`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round484-taichu-frozen-evidence-whitespace-delivery-20261108/diagnostic/git-diff-check.stdout` — 144376 bytes，SHA256 `a93cdbfeb4d9ede733a00f46f1807fb3c5f25dcc1b27da0e680a7ff478913c67`

其余固定输入path/bytes/SHA256见plan.json input_sha256；实施前逐项复核。
