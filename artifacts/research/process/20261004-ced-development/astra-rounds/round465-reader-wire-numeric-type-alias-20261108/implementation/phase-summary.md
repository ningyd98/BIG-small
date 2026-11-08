# R461 P0 / R465 联合开发验证阶段总结

P0 软件修复与验证完成，独立实际 gpt-6-astra 审查无 Critical / Important / Minor 问题。产品范围仅 reader 与新测试文件，原角色/成本/原件/物理门槛保留。

统一读取冻结有效 generation，Sol 官方 base/path 同时匹配原 endpoint SHA256；nominal 与 typed SUPERVISOR 均采用明确的纯离线身份。R464 恢复生产 model、messages、有效字段序列化顺序；R465 在三个原比较处区分 JSON true、1、1.0，保留 Mapping 输入与 Qwen think/旧参数。

| 实际阶段 | 结果 |
|---|---|
| R461 reader-red | 6 个预期失败，原件保留 |
| R461 reader-green | 4 failed、2 passed，原失败保留 |
| R464 五项条件验证 | NOT_RUN_SUPERSEDED_BEFORE_LAUNCH，由 R465 联合验证 |
| R465 reader-red | 唯一目标出现预期 DID NOT RAISE ValueError；后续分支当时未到达 |
| R465 reader-green | 6 passed，完整 nominal/B0/CED/类型/route/Qwen 路径已执行 |
| R465 adjacent-green | 134 passed |
| R465 ruff / format / mypy | 全部 rc0；mypy 仅既有未使用 ROS 配置段 note |
| 最终独立审查 | 软件交付 Ready，无问题 |

六个 R465 stage 均 FINISHED、已回收，source drift/errors/cancellations/remaining live 均空。GREEN 至静态阶段源码固定。按 Linux waited-child 口径记录的最大 RSS 为 260440064 字节；单 stage 与 basetemp 合计最大 regular-file 逻辑字节为 160682833，另保守预留 64 KiB 报告。该 RSS 不是并发进程树合计峰值，资源核对是退出后证据核对，原 R413 监督器未被改写。

## ROOT 对审查范围的裁定

1. 仅接受本轮 CPU 软件证据。fresh API、full-H、native 和正式资格仍按原条件计划推进；误作实际资格的代价是将合成/软件证据当作真实授权。
2. 本轮 runner 仅为已完成的串行一次性验证使用，后续复用另做计划与来源/资源验证，不新增通用重试或并行框架；误作通用运行器复用的代价是重复运行或证据失效。

## 交付与真实验收边界

产品源码、计划、步骤报告和选定诊断证据按明确路径交付；完整本地合成 basetemp raw、历史真实 raw、运行数据库、缓存、凭据、模型和 SDK 不在本次远端包内。该清单不是完整真实运行复现包。原失败、冻结副本与旧轮次规格/结果均保留。

真实工作负载 API/engine/physics/render/service 操作为 0；P1/P2/P3/full NOT_RUN、native UNKNOWN、formal NOT_ACCEPTED。下一真实阶段必须从当前真实源码重新 prepare/freeze 来源及协议绑定，不能复用旧代 hash 后改标签。可见标记、顶视相机、OpenCV、既定控制器和边缘模型选型后置条件均保持。
