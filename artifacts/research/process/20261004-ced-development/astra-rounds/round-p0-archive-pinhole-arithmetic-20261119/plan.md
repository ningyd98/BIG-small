# 归档反投影的标量算术修订

1803 before 的独立反投影在原脚本第 287–289 行首次退出 1，像素 (173,120) 的世界坐标残差约为 (2.048e−9, −2.138e−10, 0) m。1803 post-cloud 与 1802 post-cloud 也有同级残差。冻结版本 5103e7f4 的 RGBDObservation.depth_values 用 struct.unpack 解码小端 float32，取得 Python float；world_point 用此标量乘除内参。诊断脚本直接传入 np.frombuffer 的 float32 标量，在乘除时提前舍入。三帧各以同一原始深度转 Python float 后与归档可见表面残差均为零。此差异已定位于读回计算。

Sol 先核对 plan.json 的原脚本、冻结生产源、证据摘要与两例 manifest SHA，保存首次失败脚本原字节（若尚无可取回副本，先原样拷入本轮）。仅在 read_archived.py 的 pixel_sample 从原 float32 缓冲取得标量时转为 Python float，再交给独立相机坐标公式。保留小端解码、公式、世界坐标变换、原 atol=1e-12 / rtol=0、规划与标记独立检查。历史 raw、产品与首次输出只读。

用冻结 5103e7f4 来源与新输出目录回放原命令。分别列出 1803、1802 的 before/post-cloud 实际原像素、两条计算残差、原通过/拒绝身份判据。已记录的三帧须在原精度内复现；随后按父轮继续 1801 耗时及 1804 顶面分析，核原计数和阈值。保留首次退出与新退出、脚本前后 SHA，检查新增内容的 Ruff。若随后出现独立新失败，保留新回执交 Astra；不得通过改变验证阈值使回放通过。本轮零模型、零新增物理试次。
