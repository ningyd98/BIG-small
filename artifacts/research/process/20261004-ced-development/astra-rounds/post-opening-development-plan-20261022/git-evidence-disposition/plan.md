# 原始diff证据的交付检查处置

**Actual model: gpt-6-astra。** 仅计划，未改已有文件、未执行Git或测试。

## 失败与核对

原回执chunk370550中全范围 `git diff --cached --check` 实际exit2，后续stat/status未执行。本次只读核对23处均为`200a`，是unified diff的空白context前缀；原diff SHA256为`024dd115024979e71f60c5878916760e3e5ce046ae9d18203024ad23a52b02e5`，与失败记录一致。

原始unified diff中的空白上下文行必须保留单个空格前缀；该diff作为新文本文件暂存后，git --check把其内部格式空格视为新增文本行的trailing whitespace。23项均为200a，属于证据格式处置，不是正文尾空格修复。

## 限定处置

1. ROOT保留原全范围exit2回执及原main-plan.diff全部字节；先核对本表SHA与23个hex200a事实，不trim、重生成或更换证据文件。
2. 在新版本delivery manifest中列全本轮显式交付文件及hash，追加本处置记录/原失败/实际限定检查回执；旧manifest原字节保留。文档交付不包含不相关工作区改动。
3. 按最终清单构造一次精确路径git diff --cached --check -- <逐项普通新文档路径>，仅排除本表唯一原始main-plan.diff；不得使用目录宽泛排除、*.diff通配豁免或Git配置调整。执行前保存选中全路径与唯一排除路径。
4. 保存该一次限定检查的真实argv、退出码、stdout/stderr及范围；若通过，只称“普通规划文档限定检查通过；原始diff格式例外已核实”，不将原全范围exit2改称PASS。若出现其他警告/失败，STOP并实际Astra新计划。
5. ROOT可依用户既有授权显式路径提交推送完整规划交付（含原diff和本处置），核本地/上游/远端SHA；这不是产品验收、不新增旧R296运行额度。提交前如新增/修改受检普通文档而使该检查不再适用，先停止并记录，不用过时结果覆盖新文件。

## 验收边界

- 原diff和失败回执hash不变，23项格式身份可复核。
- 最终受检普通文档清单明确，唯一排除路径与hash固定；限定结果与原失败并列保存。
- 新版manifest显式追加，本处置及证据一并交付；无产品验收提升。

唯一例外仅适用 `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/post-opening-development-plan-20261022/document-edit-recovery/main-plan.diff` 的上述SHA；原diff仍随交付保留。不得改Git配置、旧记录或产品，不新增任何旧运行额度。

## 输入SHA256

- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/post-opening-development-plan-20261022/git-whitespace-original-failure.json`：`1dfb4c75459f7eb6e5bef87a27d416138d9a5b893e48b87baac921a59c1933ca`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/post-opening-development-plan-20261022/document-edit-recovery/main-plan.diff`：`024dd115024979e71f60c5878916760e3e5ce046ae9d18203024ad23a52b02e5`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/post-opening-development-plan-20261022/delivery-manifest.json`：`cdac860ce6824638f00e87b95b44d244f4dfd9a93cba9061cd56f280a61b56d3`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/post-opening-development-plan-20261022/plan.json`：`07be64bffa8436d29835add88ba900858b2d98d29468a9da89d8fd888b7c69d6`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/post-opening-development-plan-20261022/scope-clarification.json`：`8c0acfbd48f146a39f87f95c341e0cd30d6bc0a0953415b1f3d96a5219066007`
