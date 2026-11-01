# R384 交付短测前置目录与回执字段修正计划

实际规划者 **gpt-6-astra /root/astra_delivery_plan**。使用 writing-plans 形成限定行政实施计划；执行者按 executing-plans 实施，无须再向用户确认已有整理/交付授权。本席只写本两计划，不实施、不测试。

## 原始失败与确认

input-audit SHA256 `0b5c7f7f150b778f76f234c75b7e461f7fbd711b9e19fd09e3bfefaffe7c8c55`，17原始输入pins全部实核匹配；逐项结果与完整pins见plan.json。

已直接解析R383原JUnit全部58项：33 PASS、25 FAIL、0 error/skip。**全部25**（13 projection、12 promotion）末端均为`tests/test_operational_runtime_closure.py:2289`，原断言消息均为`resources-a.is_absolute=True/is_dir=False`；25个nodeid逐项列入JSON。源码要求资源sink存在、绝对且自身/祖先均非symlink。R383只创建stage根，未创建环境指定资源目录；本席R383计划也遗漏显式mkdir前置。该失败是执行准备缺失，不构成产品根因。

原`prerequisite.json`为`accepted_prerequisite=true`；原verifier的验收和summary两处读取不存在的`accepted`，产生null，属于第二项行政字段错误。原child exit1、14.1145秒、FINISHED、reaped=true，source_drift/errors/remaining_live均空；第二组未启动。原R383计划、脚本、失败和33 PASS全部冻结，不补造旧目录、不改写旧结果。

## 限定实施

- [ ] 在R384新建行政`verify_checkpoint.py`及spec/preflight/回执/step-report，允许从冻结R383脚本派生；只增加目录前置、R384路径/标签和正确字段读取。原R377 bounded_stage.py原样复用，产品与tests一字节不改。
- [ ] 复核本轮18项pins及R383计划中的47项pins、有效src/tests未变、无并发写源/测试、现有解释器path/realpath/SHA/版本及权限。保持输入plugin/seed/legacy原件可读；不导入产品做预跑。
- [ ] 两组完整argv/env见JSON。由固定R383 plan.software_verification.stages派生，**仅将绝对R383轮目录前缀换为R384**；BIGSMALL_R158_COMMAND分别改为`r384_temporal_cpu`、`r384_fixture_diagnostic_cpu`。R380 legacy goldens、R373/R235 plugins等输入路径不重映射、不mkdir；节点、markers、插件、资源语义保持。
- [ ] 每个新stage根起初必须不存在；不得复用/删除未知目录。创建并逐项验证下述绝对目录及所有祖先无symlink，且位于对应R384新stage下：stage根、`r223/resources`、`r223/cases`、`runtime`、`runtime/artifacts`、`resources`、**`resources-a`**、`cases`、`pycache`、`ruff-cache`、`mypy-cache`、`persistent-basetemp`。它们涵盖所有环境输出目录及events/DB/prerequisite输出文件父目录。写实际目录检查回执；任何缺失、非目录、symlink或越界均禁止launch。不得仅验证路径字符串或删掉资源env来避开断言。
- [ ] 确认invocation/result/prerequisite/JUnit/events/stdout/stderr尚不存在，basetemp为本轮新建空目录；SIMULATION_RUNTIME_DB缺省、清洁allowlist无凭据、真实运动false。两组准备完毕后、首次driver前一次性设新360秒总deadline，后续不重置。
- [ ] 串行单次执行相同两组：temporal五文件58项，child180秒；fixture+diagnostic两合同及两个原shared smoke选择器9项，child60秒。每组15秒cleanup，完整额度不足则NOT_RUN_BUDGET；第一组accepted后才启动第二组。R383额度不退款，不算原失败重试；这是新Astra轮新预算，无普通重试。

## 验收及失败边界

新verifier两处都读取`prerequisite.get("accepted_prerequisite")`，必须`is True`，缺失/null/false即失败；不能fallback为通过。仍分别核对driver退出、child退出与FINISHED、精确JUnit选择/58和9数量、0fail/error/skip、source_drift/errors/remaining_live为空、reaped、无超时/取消及异常信号；driver exit0不等于test通过。原件和代码前后pins不变。

新R384报告保留原25 FAIL/33 PASS并解释行政修正，若新67项通过则仅记有界CPU软件回归通过。不得声称修复产品、commit_close、全T3、UTC、browser或正式研究验收。R383打包及独立安全交付可继续，交付范围不扩大。

新失败或范围扩大立即保存原输出并暂停相关动作，下一实际Astra计划后再处理；不现场修产品、放宽断言、重跑或延时。无需长测试、模型/硬件/真实仿真。完整输入SHA、逐个原失败与精确执行模板以plan.json为准。
