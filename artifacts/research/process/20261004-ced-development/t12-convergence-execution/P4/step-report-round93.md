# P4 R93 新真实来源执行报告

新预检、单次真实仿真采集和外部公共 reader 各执行一次，均退出 0。采集耗时 20.193516 秒；225 个当前源文件在运行与读出前后无漂移。独立 reader 使用真实新 catalog 与原 receipt，结果 VERIFIED、source_prefix_complete=true、无拒绝原因。

原事件为 RESET 1、CONTROL 120、PHYSICS 120、CAPTURE 3，共 244；两次缓存实例侧文件为 0 字节，显式实例文件 307200 字节（76800 像素），未合成缓存实例。真实来源当前年龄区间 1244654602–1977729199 ns，within_5s=true。allocated_actions=0、模型请求0、校准组0。新原件共 63 文件、16700451 字节，完整raw/DB保留本地。

原第一次实际失败的 68 文件、25001424 字节重新核对未变。累计实际尝试2：原失败1、新成功1；不删除失败、不自动重试。ROOT接受限定来源正分支，另交不同作者审查。live/native/UTC-SI/geometry/future-H_D/完整OC3与formal并未因此验收。原P4 step-report.md保持首次失败口径。
