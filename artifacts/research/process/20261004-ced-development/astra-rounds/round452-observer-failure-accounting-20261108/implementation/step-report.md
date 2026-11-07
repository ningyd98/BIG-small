# R452 实施结果

F2/F5 的唯一 RED 为预期 3 FAIL；唯一 GREEN 为 3 PASS。真实 worker/SQLite 失败链路与真实 recorder/backend operation wrapper 已用 SOFTWARE_ONLY 引擎和相机验证：RESET 写入、observer、audit 失败均在 guard/sampler/首步前被拒绝；正常 RESET 可到 guard 入口。原错误和 PARTIAL、physics0 保留。

CAPTURE 返回的实际 pass 列表先于写盘/OC1处理计入，一次性计数；2+3+失败写入的3累计8，重复END拒绝且不重复计数。中途 camera 无完整返回时 exact=null、已知下界保留；独立 reader 拒绝其完整资格。body/final/raw 保存一致计数精度与来源。全部监督进程回收，无源漂移或残留。

此处 actual 初始化、physics、render、模型和硬件调用均为0。静态与受影响回归按 R453 计划统一执行，首组 actual 尚未开始，native UNKNOWN。
