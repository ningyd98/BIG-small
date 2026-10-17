# OC2 Task2/3 独立预审（R75冻结）

状态：**PRELIMINARY_REQUEST_CHANGES_NOT_FINAL**。spec compliance与code quality均为 **PRELIMINARY_REQUEST_CHANGES**。这是完整限定增量的只读预审，不能作为最终软件PASS或actual授权。

审查者 /root/sol_rw1_review 与实施者 /root/sol_t12_p1 不同，可由已有RW1 actor及handoff作者记录核对。ROOT历史调度摘要记载requested_model=gpt-6.1-sol、effort=high；本次followup_task沿用现有配置；未独立核验服务内部模型身份。 未发现独立序列化reviewer spawn收据，不把实施者dispatch冒充审查者收据。

## 两项实际发现

1. **OC2-PR-01 / P1：startup报告写入可替换primary。** [冻结prefix](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round75-oc2-residual-type-20261007/implementation/source-after/src/cloud_edge_robot_arm/research/operational_prefix_v1.py:570)，SHA256 8ae58cf74fc7278462ac2b0d5a64b87b60b35e53d8879e6c48e97c9e01c76cd3。_prepare_source_v1 的except先记原异常，随后无保护地写startup-failures.json。静态反例：原preregistration guard产生ValueError，报告写入再产生OSError；裸raise尚未执行，外层runner收到OSError，由preserve标PRIMARY。原ValueError仅留旧无role行，worker终态可能由原FAILED变BLOCKED_BY_ENV。违反 [Round60](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round60-operational-oc2/plan.md:92) 的startup原件/不掩盖要求及 [Round67](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round67-oc2-green-partials/plan.md:25) 的primary-first、secondary关联、原异常重抛要求。现有preregistration写失败case允许startup-failures写成功，reset-secondary cases不覆盖此双失败。**未注入或执行。**

2. **OC2-PR-02 / P2：历史reader漏验返回frame→source acquisition因果join。** [冻结prefix](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round75-oc2-residual-type-20261007/implementation/source-after/src/cloud_edge_robot_arm/research/operational_prefix_v1.py:1056)，同上hash。writer在 [冻结capture](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/source-after/src/cloud_edge_robot_arm/research/operational_capture_v1.py:187) 以实际返回observation匹配frame，记录returned_acquisition_id=frame.acquisition_id与source_acquisition_id=frame.source_acquisition_id or frame.acquisition_id。派生frame允许两值不同；应核对返回frame存在、其原source关系和event/interval。reader只查source ID/token/D/S/age，从未读取returned ID；schema仅要求键存在。静态反例：把合法current.returned_acquisition_id改为不存在字符串，只按 [现有tamper测试](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/source-after/tests/test_operational_capture_v1.py:413) 重算该文件receipt.original_files的SHA/bytes；其余event/frame/source原件不动，现有条件仍可到达VERIFIED/source_prefix_complete=True。违反 [Round60](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round60-operational-oc2/plan.md:101) 的完整event/frame joins与cached identity缺失拒绝要求。**未改原件、未运行tamper；不假定两ID恒等，不主张reader赋予live/native权限。**

## 完整限定范围与证据

审读Task1→Task2/3新增/变更函数、round67三文件行为diff、handoff格式diff、R74四文件diff和R75单注解diff。结论基于R75 frozen prefix、R74 frozen capture/worker/CLI test、GREEN63的其余五冻结文件；未用动态RW1两个source作结论。prefix增12函数、改5原函数/方法，无删除；schema增加slab validator、原函数无改动；Task1 capture stub被完整recorder替换。来源及证据完整pin见 [JSON报告](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/oc2-independent-review/preliminary-review.json)。

已核对exact app/repository/worker/owner/backend/capture/executor/PID/thread/lease/fencing及once语义、single observer、D/S与旧MONOTONIC/UTC原件、RESET1/SETTLE120/explicit capture1/cached分母、真实partial、immutable sidecar、freeze/export一次及失败缓存、cleanup primary、精确终态、publication guard和receipt/catalog顺序、历史reader raw/hash/episode/physics/recipe/event/frame joins、CLI默认无执行。除上述两项及已知类型阻断，限定阅读范围未再报告新问题；不等于最终验收。

独立stdlib审计：

- 历史GREEN63 JUnit为63个唯一node，failure/error/skip均0，保存node清单一致；SHA256 8313fc28e1f4715bee46061d7b330f5fe1e1453d3c1e3e08738a915a7c539dbf。未重跑。
- 九份GREEN63、四份R74、一份R75源码hash/bytes一致；GREEN→R74 before、R74→R75 before链一致。R74四整模块按登记type/cast/import差异局部还原后AST相等，R75唯一recorder AnnAssign还原后整模块AST相等。未全局排序或移除assert。
- 1481项本地CPU原件、116项审查副本及对应原件、12项历史证据hash/bytes一致。完整raw/DB远端包未交付，selected copies不冒充该包。
- taxonomy12路径观察resolve为9个独立失败目录，3个current别名不额外计独立运行。RESET失败1 event/2 boundaries/无acquisition；后续partial244 events/488 boundaries/acquisition1–3；失败D无伪造MARK/END/bracket；source complete均false。reset/capture/export/catalog为BLOCKED_BY_ENV，cancel为CANCELLED，policy/capture-swap为FAILED；两secondary case保留原RuntimeError及关联secondary。原57/4失败、RED和1322项旧分母保留。

## 未完成与可验收边界

R75 mypy仍exit1：prefix:455 _config为SimulatorConfig|None，调用model_dump；既有return-no-any错误已消失。Astra79类型修复和最终冻结待完成；targeted6与R03各一份剩余授权验证未消费。历史63GREEN不等于修复后最终验证。两项新发现由ROOT交实际Astra；审查者不自行修复。

本次仅stdlib读源码/hash/AST/JUnit/JSON原件；pytest/ruff/mypy/runtime/actual/network/Git均0，不派子代理，不修改产品或旧证据，只写此md/json。静态反例未运行。最终软件审查需新冻结源及授权验证；actual仍ROOT专属且需独立gates，本报告不授权。formal=false、native/consumer unavailable、calibration0、H_D/geometry/motion UNKNOWN和OC3未验边界不提升。
