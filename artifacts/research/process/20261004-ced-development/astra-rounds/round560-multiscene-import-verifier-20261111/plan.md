# R560 Import Verification Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans；父流程内联实施，无额外审批。

**Goal:** 修正辅助命令验证方法，完成原R559唯一导入调整及既定场景采集预检。

**Architecture:** 用冻结Ruff补丁的应用结果和可逆性判定精确修改；不同diff算法的文本不作等价标准。

**Tech Stack:** 原app Python、git apply、AST、pytest、Ruff。

**Spec:** R559冻结request/plan/diff及本轮证据；实际planner_model=gpt-6-astra。

## 原始问题与证据

父流程报告：①误用python，shell exit127；②改用绝对app解释器后，difflib输出与Ruff输出逐字比较触发AssertionError。首次完整工具transcript未提供，本轮reported-original-failures.json明确标为父流程转述，不冒充逐字原日志；取得原transcript后原样补存。

只读见证已确认：当前源码仍37586字节，SHA256=16c8e7c1a39c00c8994fcb05e2dbfaa1a4282160d8a879ee738d82a260bb3ea6；R559 gzip解压相同。Ruff重新生成输出与冻结diff逐字相同。difflib首hunk从22行、Ruff从23行开始，各自匹配导入前后相同空行，diff文本不同而目标字节相同。已在临时目录应用冻结补丁、比较目标并反向恢复原件；未改工作树源码。两个diff以逐字可还原gzip保存，SHA清单和readonly-witness.json保留验证结果。

追加同轮辅助命令失败：首次capture preflight把Molmo清单SHA ff0563…错传build_cases，N01在第一次capture前被apply_scene拒绝：scene asset family does not match capture model。capture-failure-parent-transcript.txt按父流程提供的原工具文本转录，来源标注于配套JSON，不冒充原始文件。两份冻结setup-assignments.json逐字一致且七案均使用错误SHA；scene.xml实测SHA为66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2。现有main preregister逻辑已正确使用scene.xml，不需业务修复。失败时0capture/0native/0paid，父流程确认with已清理。

三项均为辅助命令/验证器输入或判据错误；原R559导入修正方向不变。

## 唯一限定任务

**仅可修改：** scripts/probe_molmo_multiscene.py的原连续导入块，以及本轮辅助验证/采集预检命令和报告文件。不得更改测试行为、业务、生产代码、模型、运行时或预算。

- [ ] 复核plan.json输入SHA。所有Python命令使用 `/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python`，不使用python别名，不安装解释器。保留原失败、源码gzip和两份diff。
- [ ] 在源码仍冻结时，运行原Ruff `check --no-cache --diff`，保存输出并要求与R559原件相同。仅剔除输出末尾 `Would fix 1 error.` 说明行得到原补丁正文，不清理上下文空白。用 `git apply -p0 --check` 后应用正文（该新脚本未跟踪时可用 `--no-index`）；只移动scripts导入到cloud_edge组末尾，仍在sys.path设置后。
- [ ] 修改后字节必须等于冻结补丁在临时原件上产生的目标；反向补丁在临时副本恢复出原源码SHA。完整import节点AST多重集合必须相同，包含模块/名称/别名；仅将原连续导入块排序归一化后，全模块AST必须相同。不得归一化其他语句。**不要求difflib与Ruff两种等效算法输出相同。**
- [ ] 重跑既定247项CPU组合、研究脚本/测试/launcher的Ruff及git diff --check；保存新输出并记录验证器结果。只完成原R559样式修正，不修无关失败。
- [ ] 保留失败setup根及两份assignments原件不变。用绝对app解释器、正确scene.xml SHA在新独占根 `datasets/model-cache/molmo-multiscene-r558-setup-r560-20261111` 执行原七案预检：N各1帧、P各2帧，共10帧。建立新assignments并比较原七案的case/task/scene_parameters/顺序完全相同；仅资产绑定及派生scene group/hash、运行元信息变化。每案独立session，apply_scene仅初次capture前一次；P两帧同episode、不同frame_id、sim_time不推进；禁止step/settle/OfflineSceneAdapter。保存原RGB/depth/mask/metadata、大小/SHA清单及实际捕获数，0模型/生成/付费。此为修正预检命令，不是模型重试，不覆盖原失败；setup使用的渲染资源与模型CUDA预算分开说明。若再失败保留证据，不调整参数凑通过。
- [ ] 汇入R558步骤报告，按明确路径交付；独立审查照常独立进行，其新问题另交实际Astra计划。本轮不另开设计/审查循环。

## 前置与验收

原app解释器、worktree cwd及PYTHONPATH=<worktree>/src；托管写入按需scoped escalation。输入或目标出现计划外差异则停止相关修改并保存证据。

验收为：冻结Ruff输出一致、补丁目标字节正确、反向恢复原件、限定AST等价、247CPU/Ruff/diff通过，正确资产绑定的七案10帧预检完成且无模型/云调用；不以算法无关的diff文本相等替代这些检查。首次工具错误仍标为父流程报告，临时目录见证单独标注。所有原件保持不变，公开可用gzip保全空白。实际加载/生成/付费/GPU/硬件均0；R558未用额度与累计上限不变。无未决设计事项。
