# 归档反投影的标量精度复验

核对窄轮方案、12 项输入和冻结产品 `5103e7f4`。首次读回退出 1，1803 before 中间算术用 NumPy float32，产生约 2 nm 世界坐标残差。首次失败的脚本原字节 SHA256 为 `736b8595ad850098fdfe312faf16f76b1074d517074017cba6cb2998e7bc6487`。 [首次退出](../round-p0-archived-three-20261119/first-archive-readback.log) · [原脚本](read_archived.first-failure.py.txt)

仅读回脚本的 `pixel_sample` 将从原小端 float32 缓冲取得的标量转为 Python float，原 `rtol=0`、`atol=1e-12 m` 保持。新脚本 SHA256 为 `63a327d47d451a3a49ecfbfee38a7185a1ac5db69dd422d4a070d069f50a4ae2`，Ruff 退出 0。1803 和 1802 的 before/post-cloud 各两次采样复算，四个世界坐标残差均为零。两次完整三项读回均退出 0，九份确定性派生文件逐字节一致，当次主机负载回执分别保存于各次输出。新增模型调用和物理试次均为 0。 [逐帧精度回执](arithmetic-readback.json) · [三项报告](../round-p0-archived-three-20261119/step-report-v2.md)
