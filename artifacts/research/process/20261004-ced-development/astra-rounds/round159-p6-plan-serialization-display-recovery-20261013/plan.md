# R159：计划序列化前可选展示器恢复

> 实际 Astra：gpt-6-astra，`/root/astra_status_plan`。等待 ROOT 核对激活。

原可选 JS 摘要把 R158 `commands` 对象误当数组调用 `.map`，真实返回 `TypeError: p.commands.map is not a function`。原完整提交代码和可得 wrapper 返回已保留；没有 shell 退出码、独立 stdout/stderr、产品命令或文件写入。R158 计划尚未冻结。

现已将既有 R158 候选对象完整原样序列化为 `r158-candidate.json`。其 commands 实际为 15 个 ID 键的对象，既有源码输入清单和调用点清单不变。三项完整字节 pin 及原失败 pin 见 plan.json。

ROOT 激活后只允许 Astra 一次直接 JSON.stringify + 结构化 apply_patch，将候选合同保存为既定 R158 plan.json，并生成内容一致的可读 plan.md。放弃原展示器，零重试；不增加 helper 执行层、源码扩读、产品/测试/静态/Git 额度。允许一次标准库 bytes/hash/JSON 核对输出和原输入，简短报告真实路径、大小、SHA，再保存本轮 local step-report。

前置：ROOT 核对输入一致，R158 两目标文件尚不存在。此前先保存到另一个目录的 R159 草案未激活，保留原字节，明确由本 canonical 路径替代。所有失败历史保留。

本轮验收仅计划元数据安全保存；R158 实施仍须 ROOT 独立核对激活。新失败或漂移即停，不代表 B9 软件、native、真实、formal 或交付通过。
