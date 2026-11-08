# R490 Astra交付计划：保留冻结原始空白

实际规划者：`gpt-6-astra`；只读识别11个实际offender及2个原检查输出，未实施交付。

**问题与实际分类：** 全部16次真实生成及评分已完成，此问题仅Git交付。原临时index完整diff --check对父8b4a88bd返回rc2；Astra逐行核读原输出得到11个实际offender：CSV的CRLF、diff context空白、原始traceback末尾空行及20-byte半写JSON。候选12路径中另1条为原检查stdout，它及R490逐字节副本也保留引用的空白，故精确冻结例外共13条。历史new_files=167仅是R490加入前的计数，不作为最终计数。

**范围：** 仅R490计划/交付分类/清单/步骤报告和R486最终delivery相关派生报告；无产品/模型/实验参数修复、不新增load/generate。13条精确原字节例外不改，不转换CSV换行、不清diff/traceback空白、不补全partial JSON、不改.gitattributes/core.whitespace或全局过滤。保留原完整check rc2及所有原始证据；排除条目之外的每个待交付文件仍须正常whitespace检查。

**执行：** 复核本计划全部输入及13条例外path/bytes/SHA与Git staged blob实际内容一致。生成精确frozen-evidence-allowlist引用本计划，不用*.diff/*.csv/*.stdout宽泛规则。loading-info.partial.json明确标原始无效JSON，正常JSON结构验证只对真实完整JSON证据进行，不能为使检查通过补造内容。对未列入例外的新问题停止，不自动扩大例外。
从ignored CACHE/delivery-index-round486.json读取实际临时index路径并核验父8b4a88bde7de996a44a119115dc2f735bdad5807；仅GIT_INDEX_FILE作用域操作，不更改共享index。刷新明确R486-R490五目录的NUL路径清单，排除__pycache__/pyc、本地receipt、model raw/权重/wheel/deb/headers/venv/overlay/JIT/cache，逐文件审查实际提交blob的公开载荷边界。更新evidence/source/raw-manifest以纳入R490，采用非自引用规则，记录最终实际文件数、目录集合及fullraw仍仅本地可用。独立报告/fullweightSHA/pipchecks完成后读取真实结果并冻结，不凭进行中状态宣称通过。
对相对父commit的全部选定变化执行默认unfiltered git diff --cached --check，原rc2留存并明确full_whitespace_check=KNOWN_FROZEN_EVIDENCE_FAILURE。新检查stdout先写ignored临时路径，避免递归复制形成新未登记例外。对selected paths减去13条的精确路径集执行同一默认检查，必须rc0；保存该路径清单与hash、文件数/结果。确认unfiltered所有违规均来自精确例外且内容SHA匹配；其余源代码/报告不被豁免。
复核staged相对父的路径集合与最终选择清单完全相等，blob SHA对实际选中文件，源inputreview/原raw清单及各轮冻结证据hash未变。记录共享HEAD/index前后hash和无关service.py工作区改动，后者不触碰/不提交。使用临时index write-tree/commit-tree在既有8b4父上建立仅本五目录的提交、独立codex/taichu-no-think-best-profile-20261108研发ref，不切共享checkout、不amend/rebase/force。同名ref若存在先验证归属，禁止覆盖不明更新。
正常核验已确认GitHub origin精确公开URL及用户归属/可推送权限，push明确branch后核对本地branch、upstream tracking和实时git ls-remote对应ref三SHA一致，并核对parent=8b4。保存本地excluded receipt避免审计自引用追加commit。任何拒绝或网络失败不绕过，保留本地commit和原错误，报告尚未push或未确认。

**验证验收：** 交付通过需要13例外逐字节保留、其余所有文件默认whitespace检查rc0、完整原rc2真实可审计、源/报告/16请求计数与质量4组均0/4一致、选中文件集合/内容与stage一致、五目录范围和payload边界正确、共享index/HEAD未变、push三SHA一致。不能把有限例外流程称全量检查通过，不把FLA-OFF最快12.169秒称合格最佳（四组均无质量合格profile）。软件验证、真实运行、质量负结果和正式NOT_PERFORMED保持区分。

**前置与预算：** 只交付验证，不占用GPU或启动模型；依原90分钟deadline14:39UTC，不重置。若剩余时间不足，保留已完成本地证据及明确未完成Git步骤，不伪称远端完成。遇新增非冻结空白、源/索引漂移、载荷边界或分支冲突，保存证据暂停相关修复再交Astra。当前命令权限按环境执行，不传sandbox_permissions。

## 精确13条冻结例外

- `artifacts/research/process/20261004-ced-development/astra-rounds/round486-taichu-no-think-best-profile-20261108/request-metrics.csv` — 2947 bytes，SHA256 `7c4c69cf18cb3e7a189a8900a8343252205d81660625ac066e1f2aa2441b3107`；git实际标出的冻结原件。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round487-taichu-config-evidence-serialization-20261108/diagnostic/loading-info.partial.json` — 20 bytes，SHA256 `5e76c266a367ea44514583fdb34ed44fc15d5f113563ede9762df5c32c86a1fa`；git实际标出的冻结原件。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round487-taichu-config-evidence-serialization-20261108/experiment_r487.py.diff` — 338 bytes，SHA256 `5cc4efe48736a0ebec3a23e1b6c465538c55a6a6fe902cfa7edf57beffb9afd0`；git实际标出的冻结原件。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round487-taichu-config-evidence-serialization-20261108/run-base-r487.stdout` — 2079 bytes，SHA256 `40fdc1743d47b9daa638388c69d420dc9590f2f9238983f0c655aff380d61ca7`；git实际标出的冻结原件。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round487-taichu-config-evidence-serialization-20261108/run_profiles_r487.py.diff` — 1457 bytes，SHA256 `a16c506ffa8ac24b0cea0975545420e09653ecca388642e5d26a19d1c290e4ce`；git实际标出的冻结原件。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round488-taichu-json-native-subclasses-20261108/cpu-green.stderr` — 1754 bytes，SHA256 `fc4050070d99f123bd8f3f194d4d8da4db4af9603e6e673963852a64b3a89e53`；git实际标出的冻结原件。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round488-taichu-json-native-subclasses-20261108/diagnostic/run-base-r487.stdout` — 2079 bytes，SHA256 `40fdc1743d47b9daa638388c69d420dc9590f2f9238983f0c655aff380d61ca7`；git实际标出的冻结原件。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round488-taichu-json-native-subclasses-20261108/experiment.diff` — 228 bytes，SHA256 `c0240870ab2e772b7d5253d597a33a9db7ad124ba9d32f294f55a83ca92a51d6`；git实际标出的冻结原件。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round488-taichu-json-native-subclasses-20261108/run_profiles.diff` — 2990 bytes，SHA256 `c80190fe42e9bdd58c146c37df063adb8bbd182cf502ab08700cb483534a4686`；git实际标出的冻结原件。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round489-taichu-isolated-jit-headers-20261108/experiment.diff` — 1090 bytes，SHA256 `b661f35e756cce9da579fa9298c2d3f8f958e9c13796c7d93a8083becb63a78e`；git实际标出的冻结原件。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round489-taichu-isolated-jit-headers-20261108/run_profiles.diff` — 3079 bytes，SHA256 `015ed9d1b6b0d930fc93bd4a4f69549f5ce172f4a44486a382736d7712418a81`；git实际标出的冻结原件。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round486-taichu-no-think-best-profile-20261108/delivery-diff-check.raw.stdout` — 10373 bytes，SHA256 `81e3784494b5edf46e1cd85aba70bf4dfd664413245df37a3948a8fbcc1be6d6`；原始git检查输出及逐字节诊断副本，包含被引用空白。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round490-taichu-delivery-frozen-whitespace-20261108/diagnostic/delivery-diff-check.raw.stdout` — 10373 bytes，SHA256 `81e3784494b5edf46e1cd85aba70bf4dfd664413245df37a3948a8fbcc1be6d6`；原始git检查输出及逐字节诊断副本，包含被引用空白。

其他输入path/bytes/SHA256见plan.json；实施前逐项复核。
