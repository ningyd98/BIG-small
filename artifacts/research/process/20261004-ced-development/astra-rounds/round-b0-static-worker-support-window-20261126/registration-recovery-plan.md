# B0 STATIC 登记的旧 SceneSpec 散列读取恢复

gpt-6.2-astra 限定恢复。登记第一次读取序列化场景内部的 scene_hash 报 KeyError，在写入候选文件前发生，无 RESET、采图或试次。原首版脚本 SHA256 eaa83b123a046eaee62489779b5effa9178263b0c15a19bf4bc5b3cc9aaa903d。

仅修复登记预检。每条含完整场景的旧 assignment 用原 SceneSpec 对序列化场景重算 scene_hash，与基础层必需声明及可用的包装层声明逐项比较。缺失、漂移或非法格式停止登记。原始池、旧场景、开发排除、起始 seed 和碰撞顺序保持。先用原样本与篡改外层哈希副本校验，再重跑登记。后续额度保持一次 reset，120+2400 步，11 次指定曝光和两次原自动曝光。

第二次登记已到编译阶段。真实的 PhysicalScenarioConfig 是 dataclass，不能直接 model_dump。按 Astra 恢复，仅用 asdict 展平，两个原 Pose 用自己的 JSON 序列化。先在内存完成登记并核对重新编译的 XML 与第二次留下的字节完全一致，再写全新目录。第二次脚本 SHA256 f215ff6aa8624133e7a94fb00fdf06d77a6e3db4f4421d9c2fede84c9832bfd4，XML SHA256 342162ee62dd4fbaccf30ee659f3287d5d834465c7487a20101aeb2e3b1500f0。两个登记失败均为零 RESET 和曝光。
