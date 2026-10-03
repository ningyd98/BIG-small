# 第三方真实 RGB-D 数据部署实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 部署真实 RoboMIND h5_franka_1rgb 与 GraspClutter6D 的明确 smoke 范围，提供可恢复下载、安全解压、惰性读取和诚实验收。

**Architecture:** 在 cloud_edge_robot_arm.datasets.external 增加离线契约与来源适配器，复用现有 Python 项目、JSONL 索引与脚本形式。原始数据放仓库外；严格实时 RGBDObservation 不放宽，不以缺失标定构造在线观察。下载与真实数据验证和单元夹具验证分别报告。

**Tech Stack:** Python 3.12、NumPy/Pillow、h5py、huggingface_hub、httpx、py7zr；隔离 .venv-data 复用既有依赖，不安装大模型。

**Spec:** docs/superpowers/specs/2026-10-03-external-rgbd-deployment-design.md

## Global Constraints

- 总新增下载上限250GiB；RoboMIND首轮10GiB；保留至少50GiB空闲。
- 默认下载并发4、CPU解码worker2；基础读取支持num_workers=0。
- 数据根 BIGSMALL_DATA_ROOT，缺省 $HOME/datasets/BIGsmall。
- HF使用完整commit SHA；魔搭锁定可获得的revision/file SHA，不跨源混卷。
- 不接受访问条款、不记录token、不关闭TLS，不训练、不驱动硬件、不修改生产决策。
- RoboMIND至少2任务10完整轨迹；GraspClutter6D选择官方协议约10场景；不足如实报告。
- 原始时间、原始深度与官方划分保留，缺失单位/标定/状态不补造。

## Review Focus

- 字节编码HDF5/BGR语义和16位深度保真，缺失单位必须降低能力。
- 分卷不可独立用，路径穿越/链接/半解压不能标部署完成。
- 版本绑定/摘要/预算在下载前与恢复时重验，不复用错误来源。
- 同episode/scene多相机不得跨划分，ground truth不得进入普通观察。
- 缺数据、网络、权限、标定分别汇报，真实验收不能由synthetic_fixture替代。

## Task 1 契约与读者

- [x] 先写失败测试：RGB色块、压缩HDF5帧、16位深度、depth_scale、未知单位、空depth、坏帧、缺时戳/标定/姿态方向。
- [x] 实现 models.py、robomind.py、graspclutter.py：DatasetSample/CapabilityFlags、惰性读取、独立GT与状态语义。
- [x] 跑CPU测试，确认真实格式来源与限制。

## Task 2 可复现传输与解压

- [x] 先写失败测试：预算、有限重试/恢复、版本/摘要不匹配、缺卷、路径穿越、半解压。
- [x] 实现来源 manifest、transfer.py、archives.py：锁定清单、SDK按文件获取、local SHA256、安全原子发布。
- [ ] 输出plan后按容量与下载上限执行真实下载，持续监控并保存状态。

## Task 3 索引、loader与离线接入

- [x] 先写失败测试：episode/scene划分、内容重复、不同尺寸batch、CPU多worker、GT隔离、硬件链路拒绝。
- [x] 实现 index.py、loaders.py、provider.py、preview.py：JSONL成员清单、窗口/多视角loader、暂停/跳转、真实静态预览。
- [ ] 实测真实batch形状/dtype/有效率/内存/耗时；各5组预览，标定不足保留限制。

## Task 4 CLI与最终验收

- [x] 实现 scripts/rgbd_data.py 与 deployment.py，doctor/plan/download/extract/validate/index/preview/smoke/status/deploy。
- [x] 增加 configs/rgbd_datasets.yaml、.env.example、README入口、部署说明。
- [x] 执行CPU新测试、相关旧回归、Ruff/mypy和独立审查；真实scope逐项记录状态。
- [x] 交付JSON与中文Markdown报告，明确真实规模、来源、阻塞与可运行恢复命令。

不自动提交/推送；本轮工作区起点保存在 artifacts/research/process/20261003-external-rgbd/initial-repository.json。来源核查与读取适配独立并行，共享models契约先冻结。用户已要求“不要反复确认已明确的技术选择”，实施按此授权连续进行。

当前真实部署：RoboMIND `BLOCKED_BUDGET`；GraspClutter6D 下载已中断并保留约3.24GB断点，Meta TUN当前同文件请求确认经日本代理，正在测试下载任务直连。真实batch/预览/verified_scope尚未通过，相关复选项保持未完成。软件143项通过、Ruff/mypy通过、独立审查F1–F5关闭；旧路径122通过/1既有注释审计失败。

2026-10-03用户新增约束：中国大陆镜像且不走隧道。下载入口已完成物理直连/独立DNS/HTTPS域名门禁、真实缺策略阻断、固定hash镜像续传及凭证隔离；181软件测试和网络审查通过。实际探测仅HEAD无归档数据体；候选镜像不满足大陆完整源，Grasp转BLOCKED_NETWORK且不恢复国外下载。真实下载/预览/batch复选项仍未完成。
