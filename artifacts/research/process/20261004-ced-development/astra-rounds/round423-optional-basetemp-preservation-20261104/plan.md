# R423 可选 basetemp 归档补充 Implementation Plan

> **For agentic workers:** 使用 `superpowers:executing-plans`；沿用根执行者当前流程，不新增helper或审查链。

**Goal:** 如实记录56个不存在的临时目录，并校验保留16个实际存在的owned目录。

**Architecture:** 仅依照冻结72行inventory分流；存在者create-only逐字复制，不存在者只记事实。原目录及72个validation stage证据原地保留。

**Tech Stack:** `/usr/bin/python3`、lstat/readlink、SHA256、copytree(symlinks=True)；无pytest、SQL、模型或网络。

**Spec:** 本轮 `intake/observation.json` 与根AGENTS。实际planner `gpt-6-astra`，状态 **PLANNED_NOT_IMPLEMENTED**。

## Global Constraints

不改产品/测试/旧证据；不重跑任何pytest。主目录local-raw已空建可保留；只新建明确stage目标，不覆盖、删除或重试。不改main/gitlink。软件验证仍引用R422原25预期RED/47GREEN，不把归档成功当研究通过。

## Review Focus

缺失不等于历史上从未创建；symlink原样保存且不跟随；外来/特殊路径停止；源变化或部分复制不冒称完成；full raw与DB保持local-only。

## 问题与证据

首次归档在 `red-001` 的 `assert source.is_dir(); shutil.copytree(...)` 处AssertionError，tool chunk `a209b6`、exit1；发生在首次复制前。已证原脚本无条件假定每个pytest参数对应真实目录。该节点不使用tmp_path与未创建目录相容，但当前缺失本身不能证明完整历史。

Planner已核对10个冻结输入SHA及72精确source的lstat状态：**16存在、56不存在**。加上intake自身共11个计划输入pin。16棵树的内容与复制稳定性尚待实施核对，未在规划阶段复制或运行测试。

## 唯一任务：可选临时目录的如实保留

**Files:** 只读source由intake.rows精确列出；新副本为 `R422/local-raw/<stage>`，仅以下16个stage：

`red-009`, `red-010`, `green-009`, `green-010`, `green-011`, `green-012`, `green-015`, `green-016`, `green-028`, `green-029`, `green-030`, `green-031`, `green-041`, `green-042`, `green-043`, `green-044`。

新建本轮 `local-preservation-manifest.json`（local-only）与 `step-report.md`；本计划仅创建plan.md/json。接口、精确source/target/validation路径在plan.json，不做全局扫描。

- [ ] **步骤1：** 实施前逐项核对11输入pins、72 rows的stage/nodeid与R422 target-manifest一致；只lstat冻结的72个绝对source。源根必须仍为16个非symlink目录及56个不存在；目标local-raw必须是真目录且仍为空，各stage目标lexists=False。确认R422进程已reaped，无活跃写者；不访问SQL或重新运行pytest。 复制前同时冻结72个精确validation stage树的只读内容摘要，供复制后比较；不跟随其链接或访问DB接口。

- [ ] **步骤2：** 仅递归枚举16个存在source且不跟随symlink，生成内存中的before inventory：相对路径、类型、普通文件bytes/SHA256、symlink原始readlink文本、用于稳定性复核的lstat dev/ino/size/mtime_ns。source须属于当前UID且仅为目录/普通文件/symlink；root或中间路径替换、外来UID、特殊文件、逃出该owned source的链接、读取错误均停止。链接文本可以保留但不得读取目标内容或改写成相对链接。

- [ ] **步骤3：** 按冻结rows顺序仅为16个存在目录执行create-only copytree(source, local-raw/stage, symlinks=True, dirs_exist_ok=False)。56个不存在source不创建任何目标，不以mkdir、空文件或占位raw补齐。对其记录status=ABSENT_OBSERVED、copy_attempted=false、target_exists=false；NOT_CREATED仅可作为与无tmp_path消费者相容的解释，不冒充完整历史事实。

- [ ] **步骤4：** 一次核对16份副本与before inventory：路径集合/类型一致、每个普通文件bytes与SHA256一致、symlink readlink字节文本一致；再次核对16原目录的结构/身份/文件内容及56缺失路径未变，目录访问atime不作为内容漂移。复核11输入pins和72个validation stage树的before/after只读摘要（只枚举既有精确stage，不扩展扫描）不变；旧DB/raw留原处。

- [ ] **步骤5：** 排他新建local-preservation-manifest.json，含72条status、16份before/copy/after内容清单及核对结论、56条无副本、原失败chunk、起止时间/exit与local-only标记。失败或超时也保留已复制部分及原始错误并写事实，不删除/覆盖/自动重试；不得把partial标为成功。

- [ ] **步骤6：** 根执行者排他新建R423 step-report.md，仅总结行政修正和原件不变；汇入R422尚待交付的phase-summary并与R422同做一次fresh实际Astra最终review。Git仅沿用R422精确allowlist加本轮plan.md、plan.json、intake/observation.json、step-report.md；清单、DB、full raw、副本和Git回执均local-only。

## 边界与验收

一次行政采集/复制/核对，最多16次目录复制；总cap300秒，owned进程收尾最多30秒，零重试；没有墙钟完成承诺。56行主状态用`ABSENT_OBSERVED`，不造空目录；`NOT_CREATED`只可注明为与fixture使用相容的解释。16份普通文件逐字SHA相同、树类型与symlink文本相同，原件内容/身份稳定。原样绝对链接可能仍指向源目录，副本不能宣称自包含可移植包。

任何pin/源状态漂移、目标占用、外来UID、特殊文件、链接越出owned source、源变化、读写错误或超时均保留事实并停止，不能删除部分副本重试。原72 stage的raw/DB仍原地保留；单次fresh Astra与R422联合最终审查即可。

Git新文档仅本轮plan.md、plan.json、intake/observation.json、step-report.md；其余沿用R422精确allowlist。副本和preservation清单local-only，不推DB/full raw，不扩大目录选取。根执行者按既定普通提交/推送与三端SHA核对交付；本planner无Git操作。

## 输入pins

| 输入 | bytes | SHA256 |
|---|---:|---|
| `AGENTS.md` | 1774 | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round422-runtime-spy-recapture-test-contracts-20261104/plan.md` | 21890 | `5d90518f99e6c5a7b10cc237c95c59273a7025ac9f1cc1b3033f46406f7657d9` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round422-runtime-spy-recapture-test-contracts-20261104/plan.json` | 141153 | `b4db3e8df5d9f182dcffca12880e11c09b15ac6d6f6ce5ec44c0ba53a6995103` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round422-runtime-spy-recapture-test-contracts-20261104/preflight/target-manifest.json` | 34916 | `31425e30c525174e0ed057a2edb397550113beff5ff17383ce5576f1d12fac22` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round422-runtime-spy-recapture-test-contracts-20261104/validation-summary.json` | 237590 | `2ef523e172e0d05bec68007fb0ca8c8e487d9c216863cdf302987d3bcfac0a61` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round422-runtime-spy-recapture-test-contracts-20261104/final-integrity.json` | 24854 | `f62d0d60055b2b946e5fc08e6b6db08e09a87c377dd9e01d5e394a6cd2c703b1` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round422-runtime-spy-recapture-test-contracts-20261104/validation/red-001/result.json` | 395 | `abe19b24bf0540bd73dba9a1ee45d7a070d0a31ef1720398a49e86c3b35d5c1f` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round422-runtime-spy-recapture-test-contracts-20261104/validation/red-001/spec.json` | 6288 | `300e5de0696a822c3bae51b805ac4122c9f666ad17c2c76424d0714ee1396978` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round422-runtime-spy-recapture-test-contracts-20261104/validation/red-001/pytest-events.jsonl` | 1739 | `598452d62af003adb794656fe62727ca4645f7a9eaf1d6ed2ad6003fd927c01d` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round422-runtime-spy-recapture-test-contracts-20261104/validation/green-047/result.json` | 396 | `34f2a90d7116b49f83f163b88e9399264cbd66843c80c7869b7056c514277d3a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round423-optional-basetemp-preservation-20261104/intake/observation.json` | 27543 | `fe2baa3828bc75faacc7e61455e561d2e5cd7bbc2a8e7ffdabf140fdc814bb03` |

自审：72=16+56；原件保护、缺失诚实性、独占目标、链接边界、失败停线、local-only交付均有对应步骤。当前仅建议形成，归档尚未实施。
