# R439 T1 实施结果

2026-11-07；依据实际 Astra R439 冻结计划。输入 51 项 SHA256 全部匹配，另冻结 952 项源码、配置、资产与测试基线。

- 原始 RED：`validation/t1-red`，恰好 2 个预期 assertion 失败，接口缺失；无收集错误。
- 改动：backend 守卫容量严格限定 1024..500000；默认保持 1024，保留闭合槽。一次性 owner-thread sampler 在每物理步后、下一控制前采集，容量到限提前停止，不改变 actuator target 或推进额外物理步。内部 full-H runner 保留原控制器结果并逐步补足预登记终点，失败/超时/持物丢失保存部分 receipt。
- GREEN：`validation/t1-green`，59 PASS，pytest 2.14s，监督 3.004s，returncode 0，source drift/remaining live 均空，已回收。
- 本阶段真实 MuJoCo 初始化、physics/render 均 0；新增用例及既有守卫测试均使用明确 software engine。
- 尚未完成应用权限工厂、完整实际采集或独立重算；`NativeHorizonSession` 公共构造继续拒绝，全部 receipt 不授予 native 权限。

下一步 T2：真实 worker/SQLite 单次采集入口、当前像素与本体 grounding、唯一 recorder 与原始 OC1 deadline。
