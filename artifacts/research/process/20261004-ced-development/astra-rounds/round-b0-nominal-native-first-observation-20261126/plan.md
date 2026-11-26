# B0 名义纯色首帧的原生采集与几何读回

gpt-6.2-astra 计划，源基线 `6102b510224c22cdf1ce9ed78d5f2bdde6e35583`。v10 的登记实体标记和 owner 与 B0 的 `scene.xml` 纯色箱不同。真实 B0 selection 的编译场景带有自身宽高、FOV 和 120 步 settle。本轮先测能直接与真实原字节比对的名义探针首帧，范围是冻结的默认 `S01_NORMAL_STATIC`、seed 0。

1. 核对原名义探针 47 件清单、第一帧、真实 request/response 字节和坐标映射，从旧模型真实回复取两枚像素。历史名义真实探针的四个未用槽不启动。
2. 一次原项目共享 EGL 锁下的 `MuJoCoCaptureSession` 原生 RESET 和 `capture_with_instances`，保存方式沿用 `save_captured_frame`。原默认 320×240、原校准、原源、禁止额外积分、动作、模型及外发。记录 RESET 内部 RGB-D 渲染和三通道显式采集的前后状态摘要与计数，禁止探拍和重试。
3. 只在解码 RGB、深度、掩码、实例、相机及时钟状态相同的前提下，把历史原像素迁移到新帧。若有差异，保存新帧差异，历史几何仍从历史同帧估计。第一读回使用生产坐标映射、局部支持环、`resolve_top_grasp` 和 `OpenCVTargetTracker._inspect_frozen_geometry`；第二遍只做原像素、原始 float32 深度的独立反投影，重建支持中位数、3×3 顶面、几何中心和抓取 TCP。实例名称仅用于离线核对。分开保留旧/新真实帧 ID 与曝光 UTC。
4. 错接相机或非正深度必拒，置换像素由来源绑定及对应支持验出。冻结输出与来源。单帧有效仅是给定历史同帧像素时的实际量测。没有新模型初始语义定位、全时域几何/速度界、selection owner、原生 PRE 证书及正式协同证据。
