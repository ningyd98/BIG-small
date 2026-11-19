# 1803 原 worker 终止字段的派生读回

read02、read03 均退出 0，九份稳定派生字节一致；离线主机负载单列。原工具 read_archived.py 第 360 行取根级 result.json 的 .get("error_type")，将 null 标作 original_worker_error_type，造成归档未记录终止原因的误读。1803 的 worker/result.json、component/episode.json 与外层 result.json 在 terminal_reason 字段均记录 ValueError；原在线消息和栈缺失。此缺口仅存在于派生字段的语义。

复核输入 SHA，保全旧脚本、首次退出、read02/read03、旧 derived 和报告。仅在归档读回里从 manifest 验证的 worker/result.json、component/episode.json 各读取确实存在的 terminal_reason；以结构清楚标注两份来源，另对照外层 result.json。原字段缺失或三者矛盾应显式报告，不能用 .get() 弥补。1803 报出原值 ValueError，1802 使用原有 null 终态作对照。原在线异常消息和原栈分别记未保存，离线构造器诊断单列。

同一冻结输入，在新目录执行独立读回；修订的身份结果、清单及回执使用新后缀或版本，保留原输出和 SHA。读回实际 JSON 验证两案、缺字段或冲突的负例，并在排除已声明的字段修订后逐项比对前一版几何值、其余确定性结果及图像 SHA。记录脚本前后 SHA 和新旧结果。新增模型、云、物理试次为零。
