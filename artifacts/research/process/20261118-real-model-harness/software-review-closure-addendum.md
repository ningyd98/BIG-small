# Phase 12 来源预检最终复核

**剩余 1 项 Important 已关闭。** 前次七项与后续两项在本次限定软件范围内均已关闭，H0/H1、Phase 12 软件生命周期补充与 UTC 软件验证部分可提交。此前复核保留了原失败和第一次修复的实际状态。[前次逐项复核](software-review-closure.md) · [本轮来源指纹](phase12/strict-source-final-verification.json)

本次检出基线为 `318a546dd3a945bddc076cc06bc3528966a4051a`。重新计算当前脚本、实际导入 adapter 和 F20 registry 的三个源码哈希，均与验证记录一致。脚本 SHA256 为 `4ce936802553a5c3f85450581c95eef71932a5b9d0b6fac37990da59b67eead1`。

从冻结旧行 `phase12-00523` 各改一项，独立调用正常入口 `run_supplement`。四个原反例分别为 profile 改成 full、删除 profile、原因为否定语句、错误码位于未登记的阶段。另测错误码后缀与重复阶段。六例均在创建输出前抛出 ValueError，adapter 构造哨兵调用次数为零。实现使用 F20 registry 核对后端、控制模式和场景，要求 validation profile，并逐项匹配 main、recovery、duplicate 三个阻塞原因。

独立重跑来源、身份及计数边界测试 **24 项全部通过**，耗时 0.15 秒。修复前日志中对应四项均为 DID NOT RAISE。旧 raw SHA256 为 `1bc6f6975cef1a23e58e6805ce725b1b96ed1cdebdaceebfa4ba248a6300419a`；读取 18 条 validation 原行后，与已有补充摘要中的原始 ID 逐项、按顺序匹配。核验只读取旧证据，没有新增生命周期试次。

本结论限于上述软件审查。先前已复核的 UTC 600 秒门沿用原联合回执；本次未运行模型、API、GPU、渲染或硬件。native 视觉接线、物理和正式研究验收仍各按其原条件进行。
