# R494 — 复用既有隔离 CUDA/FLA 启动环境

实际规划模型：gpt-6-astra；仅规划。完整输入路径、字节数、SHA256 与精确环境值见同目录 plan.json。

R491 codec preflight 的 rc0 只证明配置证据序列化成功；stderr 的 Python.h 缺失与 FLA CPU fallback 是硬件前置负结果。R489 已保存 CUDA89/FLA 真实通过与隔离头文件，当前假设是 launcher 漏传 CPATH/JIT 环境，且 FLA 在导入时缓存探测结果。旧日志、脚本和报告原字节保留。

1. 实施前复核计划全部输入 SHA/bytes、原 header-manifest 与 R491/R493 门槛。新增唯一 launcher 在任何 FLA 导入前精确采用 R489 readiness.CPATH，以及 execute_readiness.py 已登记的 jit-round489/{triton,inductor,tmp}；清除子进程 PYTHONPATH/PYTHONHOME，PYTHONNOUSERSITE=1，使用既有 JSON overlay Python、离线环境和 cache cwd。同一环境传给 R493 CPU 测试及既定 GPU runner；保留原 71+2 分发版本与实际来源。
2. 原 codec 输出硬编码，允许新 codec_preflight_r494.py 仅改结果目的地为 codec-config-dry-run-r494 / codec-preflight-r494，保留所有实际输入引用；新 stdout/stderr 独占创建。新增 readiness-target-r494 沿用 R489 driver、FLA 和 4096 元素数值前置逻辑，调整当前输入与唯一输出，不覆盖旧探测。保存最小 diff、argv、非敏感环境、cache 前后清单和耗时。无模型加载/生成或额外模型 warmup。
3. 正常审批后取得共享 GPU 锁、空闲≥14000MiB、无其他 compute，一次 30 秒复查；真实 target 必须 cuda/89，FLA 三种设备字段均 cuda、IS_NVIDIA 为真，SM/共享内存与实际 driver 一致，数值 EXACT_PASS，stderr 无 fatal/Python.h/CPU fallback/ABI 错误。codec 软件通过与硬件通过分列；全部成立方可继续原 R491/R493，旧 rc0 不追认为硬件通过。

只新增本轮 artifact/helper/launcher，不安装任何依赖或头文件，不改系统、旧环境、算法、模型、权重、提示或输入。新前置每个子进程≤120秒且受剩余预算限制；CPU 截止 **15:14:20 UTC**，整体 **16:19:20 UTC** 不变。资源/环境/hash/ABI/JIT/审批负门槛或超时如实停止相关运行，不切慢实现、不无限修复；只清理自有进程并释放锁。本轮不增加模型配额，不代表 JSON、定位或正式研究验收；步骤报告保留失败及分层结论，交付沿用 R491。
