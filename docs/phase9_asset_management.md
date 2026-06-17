# Phase 9 资产管理

资产记录在 `assets/manifest.yaml` 中，字段包括 path、SHA256、source、version、license 和 SI unit。大文件、本地缓存、视频、图片帧、ROS build 输出和 Isaac cache 都应被 gitignore。

已提交的 MJCF 是一个小型 BIG-small 参考资产，用于确定性 CI 物理验证，不是官方 Franka 模型。
